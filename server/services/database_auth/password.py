"""
Database authentication service utilities for handling password hashing and verification operations, providing functions to securely hash user passwords using bcrypt and verify plaintext passwords against stored hashed passwords during authentication. This module abstracts away the details of password hashing and verification, allowing for consistent and secure handling of user passwords within the database authentication service while also supporting optional synchronization of password operations with external authentication providers when configured.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from datetime import datetime, timezone
import secrets
import string

import bcrypt
from fastapi import HTTPException, status

from config import config
from database import get_db_session
from db_models import User

def hash_password(service, password: str) -> str:
    def _hash() -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    sem = getattr(service, "_password_op_semaphore", None)
    if sem:
        with sem:
            return _hash()
    return _hash()


def verify_password(service, plain_password: str, hashed_password: str) -> bool:
    def _verify() -> bool:
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        except (TypeError, ValueError):
            return False

    sem = getattr(service, "_password_op_semaphore", None)
    if sem:
        with sem:
            return _verify()
    return _verify()


def _generate_temp_password(length: int) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def reset_user_password_temp(service, actor_user_id: str, target_user_id: str, tenant_id: str) -> dict:
    with get_db_session() as db:
        actor = db.query(User).filter_by(id=actor_user_id, tenant_id=tenant_id).first()
        if not actor:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Actor not permitted")

        target = db.query(User).filter_by(id=target_user_id, tenant_id=tenant_id).first()
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        actor_role = getattr(actor, "role", "")
        actor_is_admin = bool(
            getattr(actor, "is_superuser", False)
            or actor_role == "admin"
            or str(actor_role).lower() == "role.admin"
        )
        actor_perms = {getattr(p, "name", "") for p in (getattr(actor, "permissions", None) or [])}
        actor_can_manage = "manage:users" in actor_perms
        if not (actor_is_admin or actor_can_manage):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted to reset passwords")

        target_role = getattr(target, "role", "")
        if target_role == "admin" or str(target_role).lower() == "role.admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin account passwords cannot be reset")

        if str(getattr(target, "auth_provider", "local")) != "local":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Password reset is managed by the external identity provider",
            )

        length = max(12, int(getattr(config, "TEMP_PASSWORD_LENGTH", 20) or 20))
        temporary_password = _generate_temp_password(length)
        now = datetime.now(timezone.utc)
        target.hashed_password = hash_password(service, temporary_password)
        target.needs_password_change = True
        target.password_changed_at = now
        target.session_invalid_before = now
        service._log_audit(
            db,
            tenant_id,
            actor_user_id,
            "password.reset_temp",
            "users",
            target_user_id,
            {
                "target_user_id": target_user_id,
                "target_username": target.username,
                "target_auth_provider": target.auth_provider,
            },
        )
        db.flush()
        return {
            "temporary_password": temporary_password,
            "target_email": target.email,
            "target_username": target.username,
        }
