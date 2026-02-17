"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


"""Authentication/token/password operations for DatabaseAuthService."""

from datetime import datetime, timezone, timedelta
from typing import Optional, List
from functools import lru_cache

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from sqlalchemy.orm import joinedload
from sqlalchemy import func

from config import config
from database import get_db_session
from db_models import User, Group, UserApiKey, Tenant
from models.access.auth_models import Role, Token, TokenData

# expose a reference to the create_mfa_setup_token operation for service layer
create_mfa_setup_token_op = create_mfa_setup_token if 'create_mfa_setup_token' in globals() else None


def _load_private_key(pem: str):
    return serialization.load_pem_private_key(pem.encode("utf-8"), password=None)


def _load_public_key(pem: str):
    return serialization.load_pem_public_key(pem.encode("utf-8"))


@lru_cache(maxsize=1)
def _validate_jwt_key_material() -> None:
    algorithm = config.JWT_ALGORITHM
    try:
        private_key = _load_private_key(config.JWT_PRIVATE_KEY or "")
        public_key = _load_public_key(config.JWT_PUBLIC_KEY or "")
    except Exception as exc:
        raise ValueError("Invalid JWT_PRIVATE_KEY/JWT_PUBLIC_KEY format") from exc

    if algorithm == "RS256":
        if not isinstance(private_key, rsa.RSAPrivateKey) or not isinstance(public_key, rsa.RSAPublicKey):
            raise ValueError("JWT key type mismatch: RS256 requires RSA private/public PEM keys")
    elif algorithm == "ES256":
        if not isinstance(private_key, ec.EllipticCurvePrivateKey) or not isinstance(public_key, ec.EllipticCurvePublicKey):
            raise ValueError("JWT key type mismatch: ES256 requires EC private/public PEM keys")
        if getattr(private_key.curve, "name", "") != "secp256r1" or getattr(public_key.curve, "name", "") != "secp256r1":
            raise ValueError("ES256 requires P-256 (secp256r1) key material")
    else:
        raise ValueError(f"Unsupported JWT algorithm: {algorithm}")


def _jwt_signing_key() -> str:
    if config.JWT_ALGORITHM not in {"RS256", "ES256"}:
        raise ValueError(f"Unsupported JWT algorithm: {config.JWT_ALGORITHM}")
    if not config.JWT_PRIVATE_KEY:
        raise ValueError("JWT_PRIVATE_KEY is required for asymmetric JWT signing")
    _validate_jwt_key_material()
    return config.JWT_PRIVATE_KEY


def _jwt_verification_key() -> str:
    if config.JWT_ALGORITHM not in {"RS256", "ES256"}:
        raise ValueError(f"Unsupported JWT algorithm: {config.JWT_ALGORITHM}")
    if not config.JWT_PUBLIC_KEY:
        raise ValueError("JWT_PUBLIC_KEY is required for asymmetric JWT verification")
    _validate_jwt_key_material()
    return config.JWT_PUBLIC_KEY


def create_access_token(service, user: User) -> Token:
    expires_delta = timedelta(minutes=config.JWT_EXPIRATION_MINUTES)
    expire = datetime.now(timezone.utc) + expires_delta

    user_id = getattr(user, "id", None)
    if not user_id:
        raise ValueError("User ID is required to create access token")

    with get_db_session() as db:
        db_user = db.query(User).options(
            joinedload(User.groups).joinedload(Group.permissions),
            joinedload(User.permissions)
        ).filter_by(id=user_id).first()

        if not db_user:
            raise ValueError("User not found")

        permissions = service._collect_permissions(db_user)
        group_ids = [g.id for g in db_user.groups] if db_user.groups else []

        to_encode = {
            "sub": db_user.id,
            "username": db_user.username,
            "tenant_id": db_user.tenant_id,
            "org_id": db_user.org_id,
            "role": db_user.role,
            "is_superuser": db_user.is_superuser,
            "permissions": list(permissions),
            "group_ids": group_ids,
            "exp": expire
        }

    encoded_jwt = jwt.encode(to_encode, _jwt_signing_key(), algorithm=config.JWT_ALGORITHM)

    return Token(
        access_token=encoded_jwt,
        token_type="bearer",
        expires_in=config.JWT_EXPIRATION_MINUTES * 60
    )


def create_mfa_setup_token(service, user: User, minutes: int = 10) -> Token:
    """Create a short-lived token usable only for MFA setup endpoints.

    The token includes the claim `mfa_setup: True` so the middleware can
    allow MFA enroll/verify calls without granting full app permissions.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    to_encode = {
        "sub": user.id,
        "username": user.username,
        "tenant_id": user.tenant_id,
        "mfa_setup": True,
        "exp": expire,
    }
    encoded_jwt = jwt.encode(to_encode, _jwt_signing_key(), algorithm=config.JWT_ALGORITHM)
    return Token(access_token=encoded_jwt, token_type="bearer", expires_in=minutes * 60)


def decode_token(service, token: str) -> Optional[TokenData]:
    try:
        payload = jwt.decode(token, _jwt_verification_key(), algorithms=[config.JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        username: str = payload.get("username")
        tenant_id: str = payload.get("tenant_id")
        org_id: str = payload.get("org_id", config.DEFAULT_ORG_ID)
        role: str = payload.get("role")
        is_superuser: bool = payload.get("is_superuser", False)
        permissions: List[str] = payload.get("permissions", [])
        group_ids: List[str] = payload.get("group_ids", [])
        is_mfa_setup: bool = payload.get("mfa_setup", False)

        if user_id is None or username is None:
            return None

        td = TokenData(
            user_id=user_id,
            username=username,
            tenant_id=tenant_id,
            org_id=org_id,
            role=Role(role) if role is not None else Role.USER,
            is_superuser=is_superuser,
            permissions=permissions,
            group_ids=group_ids
        )
        # Attach mfa_setup marker when present in JWT payload so callers may
        # treat it specially (limited setup token).
        setattr(td, 'is_mfa_setup', is_mfa_setup)
        return td
    except jwt.PyJWTError:
        service.logger.warning("JWT decode failed")
        return None


def authenticate_user(service, username: str, password: str) -> Optional[User]:
    service._lazy_init()
    username = (username or '').strip().lower()
    with get_db_session() as db:
        user = db.query(User).filter(func.lower(User.username) == username).first()

        if not user:
            return None

        if not service.verify_password(password, user.hashed_password):
            return None

        if not user.is_active:
            return None

        if user.username == config.DEFAULT_ADMIN_USERNAME and service.verify_password(config.DEFAULT_ADMIN_PASSWORD, user.hashed_password):
            user.needs_password_change = True

        user.last_login = datetime.now(timezone.utc)
        db.commit()

        user = db.query(User).options(
            joinedload(User.tenant),
            joinedload(User.groups).joinedload(Group.permissions),
            joinedload(User.permissions)
        ).filter_by(id=user.id).first()

        if user:
            db.expunge(user)

        return user


def update_password(service, user_id: str, password_update, tenant_id: str) -> bool:
    with get_db_session() as db:
        user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()

        if not user:
            return False

        if not service.verify_password(password_update.current_password, user.hashed_password):
            return False

        if service.verify_password(password_update.new_password, user.hashed_password):
            raise ValueError("New password must be different from current password")

        if len(password_update.new_password) < 8:
            raise ValueError("Password must be at least 8 characters long")

        user.hashed_password = service.hash_password(password_update.new_password)
        user.needs_password_change = False
        db.commit()
        return True


def validate_otlp_token(service, token: str) -> Optional[str]:
    if not token:
        return None
    with get_db_session() as db:
        api_key = (
            db.query(UserApiKey)
            .join(User, User.id == UserApiKey.user_id)
            .join(Tenant, Tenant.id == User.tenant_id)
            .filter(
                UserApiKey.otlp_token == token,
                UserApiKey.is_enabled.is_(True),
                User.is_active.is_(True),
                Tenant.is_active.is_(True),
            )
            .first()
        )
        if not api_key:
            return None
        return api_key.key
