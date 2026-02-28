"""
Authentication operations for managing user authentication, including token generation, validation, and user information retrieval.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Optional

import jwt
import secrets
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from config import config
from database import get_db_session
from db_models import Group, Tenant, User, UserApiKey
from models.access.auth_models import Role, Token, TokenData


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_private_key(pem: str):
    return serialization.load_pem_private_key(pem.encode("utf-8"), password=None)


def _load_public_key(pem: str):
    return serialization.load_pem_public_key(pem.encode("utf-8"))


@lru_cache(maxsize=1)
def _jwt_key_objects() -> tuple[Any, Any]:
    algorithm = config.JWT_ALGORITHM
    if algorithm not in {"RS256", "ES256"}:
        raise ValueError(f"Unsupported JWT algorithm: {algorithm}")
    if not config.JWT_PRIVATE_KEY or not config.JWT_PUBLIC_KEY:
        raise ValueError("JWT_PRIVATE_KEY and JWT_PUBLIC_KEY are required for asymmetric JWT signing/verification")

    try:
        private_key = _load_private_key(config.JWT_PRIVATE_KEY)
        public_key = _load_public_key(config.JWT_PUBLIC_KEY)
    except Exception as exc:
        raise ValueError("Invalid JWT_PRIVATE_KEY/JWT_PUBLIC_KEY format") from exc

    if algorithm == "RS256":
        if not isinstance(private_key, rsa.RSAPrivateKey) or not isinstance(public_key, rsa.RSAPublicKey):
            raise ValueError("JWT key type mismatch: RS256 requires RSA private/public PEM keys")
    else:
        if not isinstance(private_key, ec.EllipticCurvePrivateKey) or not isinstance(public_key, ec.EllipticCurvePublicKey):
            raise ValueError("JWT key type mismatch: ES256 requires EC private/public PEM keys")
        if getattr(private_key.curve, "name", "") != "secp256r1" or getattr(public_key.curve, "name", "") != "secp256r1":
            raise ValueError("ES256 requires P-256 (secp256r1) key material")

    return private_key, public_key


def _jwt_signing_key():
    return _jwt_key_objects()[0]


def _jwt_verification_key():
    return _jwt_key_objects()[1]


def _normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def create_access_token(service, user: User) -> Token:
    expires_seconds = int(config.JWT_EXPIRATION_MINUTES) * 60
    now = _utcnow()
    exp_ts = int((now + timedelta(seconds=expires_seconds)).timestamp())

    user_id = getattr(user, "id", None)
    if not user_id:
        raise ValueError("User ID is required to create access token")

    with get_db_session() as db:
        db_user = (
            db.query(User)
            .options(
                joinedload(User.groups).joinedload(Group.permissions),
                joinedload(User.permissions),
            )
            .filter_by(id=user_id)
            .first()
        )
        if not db_user:
            raise ValueError("User not found")

        permissions = service._collect_permissions(db_user)
        group_ids = [g.id for g in (db_user.groups or [])]

        to_encode = {
            "sub": str(db_user.id),
            "username": db_user.username,
            "tenant_id": str(getattr(db_user, "tenant_id", "") or ""),
            "org_id": getattr(db_user, "org_id", None),
            "role": getattr(db_user, "role", None),
            "is_superuser": bool(getattr(db_user, "is_superuser", False)),
            "permissions": sorted({str(p) for p in permissions}),
            "group_ids": [str(gid) for gid in group_ids],
            "iat": int(now.timestamp()),
            "exp": exp_ts,
        }

    encoded_jwt = jwt.encode(to_encode, _jwt_signing_key(), algorithm=config.JWT_ALGORITHM)
    return Token(access_token=encoded_jwt, token_type="bearer", expires_in=expires_seconds)


def create_mfa_setup_token(user: User, minutes: int = 10) -> Token:
    now = _utcnow()
    expires_seconds = int(minutes) * 60
    exp_ts = int((now + timedelta(seconds=expires_seconds)).timestamp())

    to_encode = {
        "sub": str(user.id),
        "username": user.username,
        "tenant_id": str(getattr(user, "tenant_id", "") or ""),
        "mfa_setup": True,
        "iat": int(now.timestamp()),
        "exp": exp_ts,
    }
    encoded_jwt = jwt.encode(to_encode, _jwt_signing_key(), algorithm=config.JWT_ALGORITHM)
    return Token(access_token=encoded_jwt, token_type="bearer", expires_in=expires_seconds)


def decode_token(service, token: str) -> Optional[TokenData]:
    try:
        payload = jwt.decode(token, _jwt_verification_key(), algorithms=[config.JWT_ALGORITHM])
    except jwt.PyJWTError:
        service.logger.debug("JWT decode failed")
        return None

    user_id = payload.get("sub")
    username = payload.get("username")
    if not user_id or not username:
        return None

    role_raw = payload.get("role")
    try:
        role = Role(role_raw) if role_raw is not None else Role.USER
    except ValueError:
        role = Role.USER

    permissions = payload.get("permissions", [])
    group_ids = payload.get("group_ids", [])

    if not isinstance(permissions, list):
        permissions = []
    if not isinstance(group_ids, list):
        group_ids = []

    td = TokenData(
        user_id=str(user_id),
        username=str(username),
        tenant_id=payload.get("tenant_id"),
        org_id=payload.get("org_id", config.DEFAULT_ORG_ID),
        role=role,
        is_superuser=bool(payload.get("is_superuser", False)),
        permissions=permissions,
        group_ids=group_ids,
        iat=payload.get("iat"),
    )
    setattr(td, "is_mfa_setup", bool(payload.get("mfa_setup", False)))
    return td


def authenticate_user(service, username: str, password: str) -> Optional[User]:
    service._lazy_init()
    username_norm = _normalize_username(username)
    now = _utcnow()

    with get_db_session() as db:
        user = db.query(User).filter(func.lower(User.username) == username_norm).first()
        if not user or not user.is_active:
            return None
        if not service.verify_password(password, user.hashed_password):
            return None

        if user.username == config.DEFAULT_ADMIN_USERNAME and password == config.DEFAULT_ADMIN_PASSWORD:
            user.needs_password_change = True

        # When the user has reached this code path they are authenticating with
        # a password.  Expiration/rotation policies should be applied regardless
        # of the recorded auth_provider flag; the earlier implementation skipped
        # the check for accounts that had been marked as external, which meant
        # that someone could bypass rotation simply by flipping the provider.
        interval_days = int(getattr(config, "PASSWORD_RESET_INTERVAL_DAYS", 0) or 0)
        changed_at = getattr(user, "password_changed_at", None)
        if changed_at is None:
            user.password_changed_at = now
            changed_at = now

        if interval_days > 0 and changed_at is not None:
            if getattr(changed_at, "tzinfo", None) is None:
                changed_at = changed_at.replace(tzinfo=timezone.utc)
            expiry_cutoff = now - timedelta(days=interval_days)
            if changed_at <= expiry_cutoff:
                user.needs_password_change = True

        user.last_login = now
        db.flush()

        hydrated = (
            db.query(User)
            .options(
                joinedload(User.tenant),
                joinedload(User.groups).joinedload(Group.permissions),
                joinedload(User.permissions),
            )
            .filter_by(id=user.id)
            .first()
        )
        db.commit()

        if hydrated:
            db.expunge(hydrated)
        return hydrated


def update_password(service, user_id: str, password_update, tenant_id: str) -> bool:
    new_password = getattr(password_update, "new_password", "") or ""
    current_password = getattr(password_update, "current_password", "") or ""

    if len(new_password) < 12:
        raise ValueError("Password must be at least 12 characters long")

    with get_db_session() as db:
        user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
        if not user:
            return False
        if not service.verify_password(current_password, user.hashed_password):
            return False
        if service.verify_password(new_password, user.hashed_password):
            raise ValueError("New password must be different from current password")

        now = _utcnow()
        user.hashed_password = service.hash_password(new_password)
        user.needs_password_change = False
        user.password_changed_at = now
        user.session_invalid_before = None
        db.commit()
        return True


def validate_otlp_token(service, token: str, *, suppress_errors: bool = True) -> Optional[str]:
    if not token:
        return None

    token_str = str(token).strip()
    if not token_str:
        return None
    if len(token_str) > 4096:
        return None

    default_token = getattr(config, "DEFAULT_OTLP_TOKEN", None)
    if default_token and secrets.compare_digest(token_str, str(default_token)):
        return config.DEFAULT_ORG_ID

    token_hash = service._hash_otlp_token(token_str)

    try:
        with get_db_session() as db:
            api_key = (
                db.query(UserApiKey)
                .join(User, User.id == UserApiKey.user_id)
                .join(Tenant, Tenant.id == User.tenant_id)
                .filter(
                    UserApiKey.otlp_token_hash == token_hash,
                    User.is_active.is_(True),
                    Tenant.is_active.is_(True),
                )
                .first()
            )
            if not api_key:
                return None
            return api_key.key
    except SQLAlchemyError as exc:
        if not suppress_errors:
            raise
        service.logger.warning("OTLP token validation failed due to database error")
        service.logger.debug("OTLP validation error detail: %s", exc)
        return None
    except Exception as exc:
        if not suppress_errors:
            raise
        service.logger.warning("OTLP token validation failed due to internal error")
        service.logger.debug("OTLP validation error detail: %s", exc)
        return None