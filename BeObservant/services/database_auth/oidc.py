"""
Database authentication service utilities for handling OpenID Connect (OIDC) user synchronization and provisioning.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from contextlib import nullcontext
import secrets
from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import config
from database import get_db_session
from db_models import Tenant, User
from models.access.auth_models import Role
from custom_types.json import JSONDict

if TYPE_CHECKING:
    from services.database_auth_service import DatabaseAuthService


def _claim_str(claims: JSONDict, key: str) -> str:
    value = claims.get(key)
    return value.strip() if isinstance(value, str) else ""


def extract_permissions_from_oidc_claims(claims: JSONDict) -> List[str]:
    extracted = _normalize_claim_list(claims.get("permissions"))
    extracted |= _normalize_claim_list(claims.get("scp"))
    return sorted(p for p in extracted if ":" in p)


def _normalize_claim_list(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    out: set[str] = set()
    for item in value:
        s = str(item).strip()
        if s:
            out.add(s)
    return out


def _claim_truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _can_auto_link_by_email(claims: JSONDict) -> bool:
    enabled = _claim_truthy(getattr(config, "OIDC_AUTO_LINK_BY_EMAIL", False))
    if not enabled:
        return False
    require_verified = _claim_truthy(getattr(config, "OIDC_REQUIRE_VERIFIED_EMAIL_FOR_LINK", True))
    return _claim_truthy(claims.get("email_verified")) if require_verified else True


def _normalize_email(claims: JSONDict) -> str:
    return _claim_str(claims, "email").lower()


def _normalize_subject(claims: JSONDict) -> str:
    return _claim_str(claims, "sub")


def _preferred_username(claims: JSONDict, email: str) -> str:
    raw = _claim_str(claims, "preferred_username").lower()
    if raw:
        return raw
    return email.split("@", 1)[0].strip().lower()


def _full_name(claims: JSONDict) -> Optional[str]:
    name = _claim_str(claims, "name")
    return name or None


def _get_user_by_subject(db: Session, subject: str) -> Optional[User]:
    if not subject:
        return None
    return db.query(User).filter(User.external_subject == subject).first()


def _get_user_by_email(db: Session, email: str) -> Optional[User]:
    if not email:
        return None
    return db.query(User).filter(func.lower(User.email) == email).first()


def _subject_is_owned_by_other(db: Session, subject: str, user_id: str) -> bool:
    if not subject:
        return False
    return (
        db.query(User)
        .filter(User.external_subject == subject, User.id != user_id)
        .first()
        is not None
    )


def _resolve_existing_user(
    service: DatabaseAuthService,
    db: Session,
    *,
    email: str,
    subject: str,
    claims: JSONDict,
) -> Optional[User]:
    by_subject = _get_user_by_subject(db, subject)
    if by_subject:
        return by_subject

    candidate = _get_user_by_email(db, email)
    if not candidate:
        return None

    if candidate.auth_provider == config.AUTH_PROVIDER:
        existing_subject = str(getattr(candidate, "external_subject", "") or "").strip()
        if existing_subject and subject and existing_subject != subject:
            service.logger.warning(
                "OIDC subject mismatch for existing external account %s; refusing login",
                candidate.id,
            )
            return None
        return candidate

    if not _can_auto_link_by_email(claims):
        service.logger.warning(
            "OIDC email %s matches existing account with auth_provider=%s; refusing link",
            email,
            candidate.auth_provider,
        )
        return None

    if subject and _subject_is_owned_by_other(db, subject, candidate.id):
        service.logger.warning(
            "OIDC subject %s is already linked to another account; refusing link for email %s",
            subject,
            email,
        )
        return None

    return candidate


def sync_user_from_oidc_claims(service: DatabaseAuthService, claims: JSONDict) -> Optional[User]:
    service._lazy_init()

    email = _normalize_email(claims)
    subject = _normalize_subject(claims)
    if not email:
        service.logger.warning("OIDC token missing email claim")
        return None

    preferred_username = _preferred_username(claims, email)
    full_name = _full_name(claims)

    with get_db_session() as db:
        user = _resolve_existing_user(service, db, email=email, subject=subject, claims=claims)

        if user is None:
            if not config.OIDC_AUTO_PROVISION_USERS:
                return None
            user = provision_oidc_user(service, db, email, preferred_username, full_name, subject)
        else:
            if not user.is_active:
                service.logger.warning("OIDC login attempted for inactive user %s", user.id)
                return None
            update_oidc_user(db, user, email, full_name, subject)

        user.last_login = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        return user


def _ensure_default_tenant(db: Session) -> Tenant:
    tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
    if tenant:
        return tenant

    tenant = Tenant(
        name=config.DEFAULT_ADMIN_TENANT,
        display_name="Default Organization",
        is_active=True,
    )
    db.add(tenant)
    nested = db.begin_nested() if hasattr(db, "begin_nested") else nullcontext()
    try:
        with nested:
            db.flush()
            return tenant
    except IntegrityError:
        if not hasattr(db, "begin_nested"):
            db.rollback()
        existing = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        if existing:
            return existing
        raise


def _base_username(preferred_username: str, email: str) -> str:
    base = (preferred_username or "").strip().lower()
    return base or email.split("@", 1)[0].strip().lower()


def _username_exists(db: Session, username: str) -> bool:
    return db.query(User).filter(func.lower(User.username) == username.lower()).first() is not None


def _pick_unique_username(db: Session, base: str) -> str:
    candidate = base
    suffix = 1
    while _username_exists(db, candidate):
        candidate = f"{base}{suffix}"
        suffix += 1
    return candidate


def provision_oidc_user(
    service: DatabaseAuthService,
    db: Session,
    email: str,
    preferred_username: str,
    full_name: Optional[str],
    subject: str,
) -> User:
    default_tenant = _ensure_default_tenant(db)

    base = _base_username(preferred_username, email)
    must_setup_mfa = _claim_truthy(getattr(config, "REQUIRE_MFA_FOR_NEW_USERS", False))

    for _ in range(3):
        username = _pick_unique_username(db, base)
        user = User(
            tenant_id=default_tenant.id,
            username=username,
            email=email,
            full_name=full_name,
            org_id=config.DEFAULT_ORG_ID,
            role=Role.PROVISIONING,
            is_active=True,
            is_superuser=False,
            hashed_password=service.hash_password(secrets.token_urlsafe(24)),
            # Force first-time local password bootstrap after OIDC onboarding.
            needs_password_change=True,
            password_changed_at=datetime.now(timezone.utc),
            must_setup_mfa=must_setup_mfa,
            auth_provider=config.AUTH_PROVIDER,
            external_subject=subject or None,
        )
        db.add(user)
        try:
            db.flush()
            service._ensure_default_api_key(db, user)
            return user
        except IntegrityError:
            db.rollback()
            continue

    raise ValueError("Failed to provision user due to repeated uniqueness conflicts")


def update_oidc_user(
    db: Session,
    user: User,
    email: str,
    full_name: Optional[str],
    subject: str,
) -> None:
    user.auth_provider = config.AUTH_PROVIDER

    if subject and user.external_subject != subject:
        conflict = db.query(User).filter(
            User.external_subject == subject,
            User.id != user.id,
        ).first()
        if not conflict:
            user.external_subject = subject

    if email and user.email.lower() != email:
        conflict = db.query(User).filter(
            func.lower(User.email) == email,
            User.id != user.id,
        ).first()
        if not conflict:
            user.email = email

    if full_name is not None and user.full_name != full_name:
        user.full_name = full_name
