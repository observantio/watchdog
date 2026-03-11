"""
Database authentication service bootstrap utilities for ensuring that the default tenant, admin user, and permissions are created when the service starts up, allowing for a ready-to-use authentication setup with a default admin account and necessary permissions in place. This module provides functions to check for the existence of the default tenant and admin user, create them if they do not exist, and ensure that the required permissions are defined in the database, facilitating a smooth initial setup process for the database authentication service.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional, Set, TYPE_CHECKING

from sqlalchemy.orm import Session

from sqlalchemy import func, inspect, text
from sqlalchemy.exc import SQLAlchemyError, NoSuchTableError

from config import config
from database import get_db_session
from db_models import Permission, Tenant, User, UserApiKey
from models.access.auth_models import Role

if TYPE_CHECKING:
    from services.database_auth_service import DatabaseAuthService

BOOTSTRAP_PG_LOCK_KEY = 947201

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _norm_lower(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _dialect(db: Session) -> str:
    bind = db.bind
    if bind is None:
        return ""
    return str(getattr(bind.dialect, "name", "")).lower()


def _pg_advisory_lock(db: Session, key: int) -> None:
    if _dialect(db) != "postgresql":
        return
    db.execute(text("SELECT pg_advisory_lock(:k)"), {"k": key})


def _pg_advisory_unlock(db: Session, key: int) -> None:
    if _dialect(db) != "postgresql":
        return
    db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})


def _table_columns(db: Session, table_name: str) -> Set[str]:
    bind = db.bind
    if bind is None:
        return set()
    insp = inspect(bind)
    try:
        return {c.get("name") for c in insp.get_columns(table_name)}
    except NoSuchTableError:
        return set()


def _ensure_column(db: Session, table: str, col: str, ddl: str) -> bool:
    cols = _table_columns(db, table)
    if not cols or col in cols:
        return False
    db.execute(text(ddl))
    return True


def _ensure_indexes(db: Session, statements: Iterable[str]) -> None:
    for stmt in statements:
        try:
            db.execute(text(stmt))
        except Exception as exc:
            raise ValueError(f"Failed to enforce API key constraint ({stmt}): {exc}") from exc


def ensure_permissions(db: Session) -> None:
    from services.auth.permission_defs import PERMISSION_DEFS

    wanted = [p[0] for p in PERMISSION_DEFS]
    if not wanted:
        return

    existing = {
        n for (n,) in db.query(Permission.name).filter(Permission.name.in_(wanted)).all()
    }

    for name, display_name, description, resource_type, action in PERMISSION_DEFS:
        if name in existing:
            continue
        db.add(
            Permission(
                name=name,
                display_name=display_name,
                description=description,
                resource_type=resource_type,
                action=action,
            )
        )
    db.flush()


def _disable_other_enabled_keys(db: Session, user_id: object, keep_id: object) -> None:
    now = _now_utc()
    db.execute(
        text(
            """
            UPDATE user_api_keys
            SET is_enabled = false, updated_at = :now
            WHERE user_id = :uid
              AND is_enabled = true
              AND id <> :keep
            """
        ),
        {"uid": str(user_id), "keep": str(keep_id), "now": now},
    )


def ensure_default_api_key(service: DatabaseAuthService, db: Session, user: User) -> None:
    if not user:
        return

    now = _now_utc()
    is_system_user = _norm_lower(getattr(user, "username", "")) == _norm_lower(
        config.DEFAULT_ADMIN_USERNAME
    )

    existing = (
        db.query(UserApiKey)
        .filter_by(user_id=user.id, is_default=True)
        .with_for_update()
        .first()
    )

    if existing:
        _disable_other_enabled_keys(db, existing.user_id, existing.id)
        if not existing.is_enabled:
            existing.is_enabled = True
            existing.updated_at = now

        if existing.name == "Default" and is_system_user:
            desired_raw = service._resolve_default_otlp_token()
            desired_hash = service._hash_otlp_token(desired_raw)
            if (
                not getattr(existing, "otlp_token_hash", None)
                or (config.DEFAULT_OTLP_TOKEN and existing.otlp_token_hash != desired_hash)
            ):
                existing.otlp_token_hash = desired_hash
                existing.otlp_token = None
                existing.updated_at = now
            return

        if not getattr(existing, "otlp_token_hash", None):
            source = existing.otlp_token or service._generate_otlp_token()
            existing.otlp_token_hash = service._hash_otlp_token(source)
            existing.otlp_token = None
            existing.updated_at = now
        return

    raw_token = (
        service._resolve_default_otlp_token()
        if is_system_user
        else service._generate_otlp_token()
    )
    new_key = UserApiKey(
        tenant_id=user.tenant_id,
        user_id=user.id,
        name="Default",
        key=user.org_id or config.DEFAULT_ORG_ID,
        otlp_token=None,
        otlp_token_hash=service._hash_otlp_token(raw_token),
        is_default=True,
        is_enabled=True,
    )
    db.add(new_key)
    db.flush()
    _disable_other_enabled_keys(db, user.id, new_key.id)


def ensure_default_setup(service: DatabaseAuthService) -> None:
    try:
        with get_db_session() as db:
            _pg_advisory_lock(db, BOOTSTRAP_PG_LOCK_KEY)
            try:
                _ensure_user_security_columns(db)
                _ensure_grafana_folder_columns(db)
                _ensure_api_key_constraints(db)
                _backfill_password_changed_at(db)

                ensure_permissions(db)

                default_tenant = (
                    db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
                )

                if not config.DEFAULT_ADMIN_BOOTSTRAP_ENABLED:
                    if not default_tenant:
                        service.logger.warning(
                            "DEFAULT_ADMIN_BOOTSTRAP_ENABLED is false and default tenant is missing. "
                            "Run explicit bootstrap before serving production traffic."
                        )
                    return

                if not config.DEFAULT_ADMIN_PASSWORD or len(config.DEFAULT_ADMIN_PASSWORD) < 16:
                    raise ValueError("DEFAULT_ADMIN_PASSWORD must be at least 16 characters")

                if not default_tenant:
                    default_tenant = Tenant(
                        name=config.DEFAULT_ADMIN_TENANT,
                        display_name="Default Organization",
                        is_active=True,
                    )
                    db.add(default_tenant)
                    db.flush()
                    service.logger.info("Created default tenant")

                admin_username = _norm_lower(config.DEFAULT_ADMIN_USERNAME)
                admin_user = (
                    db.query(User)
                    .filter(
                        User.tenant_id == default_tenant.id,
                        func.lower(User.username) == admin_username,
                    )
                    .with_for_update()
                    .first()
                )

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
                        password_changed_at=_now_utc(),
                        must_setup_mfa=True,
                    )
                    db.add(admin_user)
                    db.flush()
                    admin_user.permissions.extend(db.query(Permission).all())
                    service.logger.info(
                        "Created default admin user: %s", config.DEFAULT_ADMIN_USERNAME
                    )

                ensure_default_api_key(service, db, admin_user)
                db.commit()
            finally:
                _pg_advisory_unlock(db, BOOTSTRAP_PG_LOCK_KEY)

    except SQLAlchemyError as exc:
        service.logger.error("Database error during default setup: %s", exc)
        raise
    except Exception as exc:
        service.logger.error("Error during default setup: %s", exc)
        raise


def _ensure_user_security_columns(db: Session) -> None:
    changed = False
    changed |= _ensure_column(
        db,
        "users",
        "password_changed_at",
        "ALTER TABLE users ADD COLUMN password_changed_at TIMESTAMP",
    )
    changed |= _ensure_column(
        db,
        "users",
        "session_invalid_before",
        "ALTER TABLE users ADD COLUMN session_invalid_before TIMESTAMP",
    )
    if changed:
        db.flush()


def _ensure_grafana_folder_columns(db: Session) -> None:
    changed = False
    changed |= _ensure_column(
        db,
        "grafana_folders",
        "allow_dashboard_writes",
        "ALTER TABLE grafana_folders ADD COLUMN allow_dashboard_writes BOOLEAN NOT NULL DEFAULT FALSE",
    )
    changed |= _ensure_column(
        db,
        "grafana_folders",
        "hidden_by",
        "ALTER TABLE grafana_folders ADD COLUMN hidden_by JSON",
    )
    if changed:
        db.flush()


def _backfill_password_changed_at(db: Session) -> None:
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


def _ensure_api_key_constraints(db: Session) -> None:
    cols = _table_columns(db, "user_api_keys")
    if not cols:
        return

    changed = False
    if "otlp_token_hash" not in cols:
        db.execute(text("ALTER TABLE user_api_keys ADD COLUMN otlp_token_hash VARCHAR(64)"))
        changed = True

    dialect = _dialect(db)

    if dialect == "postgresql":
        statements = [
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_api_keys_otlp_token_hash ON user_api_keys (otlp_token_hash)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_api_keys_user_default_true ON user_api_keys (user_id) WHERE is_default = true",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_api_keys_user_enabled_true ON user_api_keys (user_id) WHERE is_enabled = true",
        ]
    elif dialect == "sqlite":
        statements = [
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_api_keys_otlp_token_hash ON user_api_keys (otlp_token_hash)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_api_keys_user_default_true ON user_api_keys (user_id) WHERE is_default = 1",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_api_keys_user_enabled_true ON user_api_keys (user_id) WHERE is_enabled = 1",
        ]
    else:
        statements = []

    if statements:
        _ensure_indexes(db, statements)
        changed = True

    if changed:
        db.flush()
