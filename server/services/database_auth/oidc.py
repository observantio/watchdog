"""
Database authentication service utilities for handling OpenID Connect (OIDC) user synchronization and provisioning, including functions to extract permissions from OIDC claims, synchronize user information from OIDC claims with the local database, provision new users based on OIDC claims when auto-provisioning is enabled, and update existing user records with information from OIDC claims during login. This module provides a common interface for integrating OIDC authentication with the database authentication service, allowing for seamless synchronization of user data and permissions based on the claims provided by the OIDC provider while ensuring that user accounts are properly managed in the local database.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from config import config
from database import get_db_session
from db_models import Tenant, User
from models.access.auth_models import Role


def extract_permissions_from_oidc_claims(service, claims: Dict[str, Any]) -> List[str]:
    extracted = set()
    direct = claims.get("permissions")
    if isinstance(direct, list):
        extracted.update(str(item).strip() for item in direct if str(item).strip())
    scp = claims.get("scp")
    if isinstance(scp, list):
        extracted.update(str(item).strip() for item in scp if str(item).strip())
    return [v for v in extracted if ":" in v]


def sync_user_from_oidc_claims(service, claims: Dict[str, Any]) -> Optional[User]:
    email = (claims.get("email") or "").strip().lower()
    subject = (claims.get("sub") or "").strip()
    if not email:
        service.logger.warning("OIDC token missing email claim")
        return None

    preferred_username = (claims.get("preferred_username") or email.split("@", 1)[0]).strip().lower()
    full_name = (claims.get("name") or "").strip() or None

    with get_db_session() as db:
        user_by_subject = (
            db.query(User).filter(User.external_subject == subject).first()
            if subject else None
        )

        if user_by_subject:
            user = user_by_subject
        else:
            candidate = db.query(User).filter(func.lower(User.email) == email).first()
            if candidate and candidate.auth_provider != config.AUTH_PROVIDER:
                service.logger.warning(
                    "OIDC email %s matches existing account with auth_provider=%s; refusing link",
                    email,
                    candidate.auth_provider,
                )
                return None
            user = candidate

        if not user:
            if not config.OIDC_AUTO_PROVISION_USERS:
                return None
            user = provision_oidc_user(service, db, email, preferred_username, full_name, subject)
        else:
            if not user.is_active:
                service.logger.warning("OIDC login attempted for inactive user %s", user.id)
                return None
            update_oidc_user(service, db, user, email, full_name, subject)

        user.last_login = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        return user


def provision_oidc_user(
    service,
    db,
    email: str,
    preferred_username: str,
    full_name: Optional[str],
    subject: str,
) -> User:
    default_tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
    if not default_tenant:
        default_tenant = Tenant(
            name=config.DEFAULT_ADMIN_TENANT,
            display_name="Default Organization",
            is_active=True,
        )
        db.add(default_tenant)
        db.flush()

    base = preferred_username or email.split("@", 1)[0]
    candidate, suffix = base, 1
    while db.query(User).filter(func.lower(User.username) == candidate.lower()).first():
        candidate = f"{base}{suffix}"
        suffix += 1

    user = User(
        tenant_id=default_tenant.id,
        username=candidate,
        email=email,
        full_name=full_name,
        org_id=config.DEFAULT_ORG_ID,
        role=Role.USER,
        is_active=True,
        is_superuser=False,
        hashed_password=service.hash_password(secrets.token_urlsafe(24)),
        needs_password_change=False,
        must_setup_mfa=getattr(config, "REQUIRE_MFA_FOR_NEW_USERS", False),
        auth_provider=config.AUTH_PROVIDER,
        external_subject=subject or None,
    )
    db.add(user)
    db.flush()
    service._ensure_default_api_key(db, user)
    return user


def update_oidc_user(
    service,
    db,
    user: User,
    email: str,
    full_name: Optional[str],
    subject: str,
) -> None:
    user.auth_provider = config.AUTH_PROVIDER
    if subject:
        user.external_subject = subject
    if email and user.email.lower() != email:
        conflict = db.query(User).filter(
            func.lower(User.email) == email,
            User.id != user.id,
        ).first()
        if not conflict:
            user.email = email
    if full_name is not None and user.full_name != full_name:
        user.full_name = full_name or None