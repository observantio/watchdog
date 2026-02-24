"""
Database authentication service bootstrap utilities for ensuring that the default tenant, admin user, and permissions are created when the service starts up, allowing for a ready-to-use authentication setup with a default admin account and necessary permissions in place. This module provides functions to check for the existence of the default tenant and admin user, create them if they do not exist, and ensure that the required permissions are defined in the database, facilitating a smooth initial setup process for the database authentication service.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError, NoSuchTableError
from sqlalchemy import inspect, text

from config import config
from database import get_db_session
from db_models import Permission, Tenant, User, UserApiKey
from models.access.auth_models import Role


def ensure_permissions(service, db):
    from services.auth.permission_defs import PERMISSION_DEFS

    for name, display_name, description, resource_type, action in PERMISSION_DEFS:
        if not db.query(Permission).filter_by(name=name).first():
            db.add(Permission(
                name=name,
                display_name=display_name,
                description=description,
                resource_type=resource_type,
                action=action,
            ))
    db.flush()


def ensure_default_api_key(service, db, user: User):
    if not user:
        return

    is_system_user = (
        (getattr(user, "username", "") or "").strip().lower()
        == (config.DEFAULT_ADMIN_USERNAME or "").strip().lower()
    )

    existing = db.query(UserApiKey).filter_by(user_id=user.id, is_default=True).first()
    if existing:
        if existing.name == "Default" and is_system_user:
            desired_token = service._resolve_default_otlp_token()
            now = datetime.now(timezone.utc)
            if existing.key != (user.org_id or config.DEFAULT_ORG_ID):
                existing.key = user.org_id or config.DEFAULT_ORG_ID
                existing.updated_at = now
            if not existing.is_enabled:
                existing.is_enabled = True
                existing.updated_at = now
            if not existing.otlp_token or (
                config.DEFAULT_OTLP_TOKEN and existing.otlp_token != config.DEFAULT_OTLP_TOKEN
            ):
                existing.otlp_token = desired_token
                existing.updated_at = now
        elif not existing.otlp_token:
            existing.otlp_token = service._generate_otlp_token()
            existing.updated_at = datetime.now(timezone.utc)
        return

    db.add(UserApiKey(
        tenant_id=user.tenant_id,
        user_id=user.id,
        name="Default",
        key=user.org_id or config.DEFAULT_ORG_ID,
        otlp_token=service._resolve_default_otlp_token() if is_system_user else service._generate_otlp_token(),
        is_default=True,
        is_enabled=True,
    ))


def ensure_default_setup(service):
    try:
        with get_db_session() as db:
            _ensure_user_security_columns(service, db)
            _backfill_password_changed_at(service, db)
            default_tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
            ensure_permissions(service, db)

            if not config.DEFAULT_ADMIN_BOOTSTRAP_ENABLED:
                if not default_tenant:
                    service.logger.warning(
                        "DEFAULT_ADMIN_BOOTSTRAP_ENABLED is false and default tenant is missing. "
                        "Run explicit bootstrap before serving production traffic."
                    )
                return

            if not config.DEFAULT_ADMIN_PASSWORD or len(config.DEFAULT_ADMIN_PASSWORD) < 16:
                raise ValueError(
                    "DEFAULT_ADMIN_PASSWORD must be at least 16 characters"
                )

            if not default_tenant:
                default_tenant = Tenant(
                    name=config.DEFAULT_ADMIN_TENANT,
                    display_name="Default Organization",
                    is_active=True,
                )
                db.add(default_tenant)
                db.flush()
                service.logger.info("Created default tenant")

            admin_username = (config.DEFAULT_ADMIN_USERNAME or "").strip().lower()
            admin_user = db.query(User).filter(
                User.tenant_id == default_tenant.id,
                func.lower(User.username) == admin_username,
            ).first()

            if not admin_user:
                admin_user = User(
                    tenant_id=default_tenant.id,
                    username=admin_username,
                    email=config.DEFAULT_ADMIN_EMAIL,
                    full_name="System Administrator",
                    org_id=config.DEFAULT_ORG_ID,
                    role=Role.ADMIN,
                    is_active=True,
                    is_superuser=True,
                    hashed_password=service.hash_password(config.DEFAULT_ADMIN_PASSWORD),
                    password_changed_at=datetime.now(timezone.utc),
                    must_setup_mfa=True,
                )
                db.add(admin_user)
                db.flush()
                admin_user.permissions.extend(db.query(Permission).all())
                service.logger.info("Created default admin user: %s", config.DEFAULT_ADMIN_USERNAME)

            ensure_default_api_key(service, db, admin_user)
            db.commit()
    except SQLAlchemyError as exc:
        service.logger.error("Database error during default setup: %s", exc)
        raise
    except Exception as exc:
        service.logger.error("Error during default setup: %s", exc)
        raise


def _ensure_user_security_columns(service, db) -> None:
    # Keep schema compatible for existing deployments where users table predates these fields.
    insp = inspect(db.bind)
    try:
        cols = {c.get("name") for c in insp.get_columns("users")}
    except NoSuchTableError:
        return

    # Use SQL that works on PostgreSQL and modern SQLite.
    if "password_changed_at" not in cols:
        db.execute(text("ALTER TABLE users ADD COLUMN password_changed_at TIMESTAMP"))
    if "session_invalid_before" not in cols:
        db.execute(text("ALTER TABLE users ADD COLUMN session_invalid_before TIMESTAMP"))
    db.flush()


def _backfill_password_changed_at(service, db) -> None:
    # Backfill legacy local users so periodic expiry works deterministically.
    db.execute(
        text(
            """
            UPDATE users
            SET password_changed_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)
            WHERE auth_provider = 'local'
              AND password_changed_at IS NULL
            """
        )
    )
    db.flush()
