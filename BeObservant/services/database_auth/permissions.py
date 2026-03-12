"""
Database authentication service utilities for handling user permissions, including functions to retrieve a user's effective permissions based on their role, group memberships, and direct permissions, as well as a function to list all defined permissions in the system. This module provides a common interface for managing and retrieving user permissions within the database authentication service, allowing for consistent permission handling across different parts of the service while ensuring that permissions are properly aggregated from various sources such as roles, groups, and direct assignments.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import List, Optional, Set, TYPE_CHECKING

from sqlalchemy.orm import selectinload

from database import get_db_session
from db_models import Group, Permission, User
from models.access.auth_models import ROLE_PERMISSIONS, Role
from models.access.user_models import User as UserSchema
from services.database_auth.shared import safe_role

if TYPE_CHECKING:
    from services.database_auth_service import DatabaseAuthService


def get_user_permissions(service: DatabaseAuthService, user: User | UserSchema) -> List[str]:
    user_id = getattr(user, "id", None)
    if not user_id:
        return []

    with get_db_session() as db:
        db_user = (
            db.query(User)
            .options(
                selectinload(User.groups).selectinload(Group.permissions),
                selectinload(User.permissions),
            )
            .filter(User.id == user_id)
            .first()
        )
        return collect_permissions(db_user) if db_user else []


def get_user_direct_permissions(user: User | UserSchema) -> List[str]:
    user_id = getattr(user, "id", None)
    if not user_id:
        return []

    with get_db_session() as db:
        db_user = (
            db.query(User)
            .options(selectinload(User.permissions))
            .filter(User.id == user_id)
            .first()
        )
        if not db_user:
            return []
        return sorted({p.name for p in (db_user.permissions or []) if getattr(p, "name", None)})


def collect_permissions(user: User | None) -> List[str]:
    perms: Set[str] = set()

    role = safe_role(getattr(user, "role", None))
    for p in ROLE_PERMISSIONS.get(role, []):
        v = getattr(p, "value", None)
        if v:
            perms.add(v)

    for group in (getattr(user, "groups", None) or []):
        if not getattr(group, "is_active", False):
            continue
        for p in (getattr(group, "permissions", None) or []):
            name = getattr(p, "name", None)
            if name:
                perms.add(name)

    for p in (getattr(user, "permissions", None) or []):
        name = getattr(p, "name", None)
        if name:
            perms.add(name)

    return sorted(perms)


def list_all_permissions() -> List[dict[str, object]]:
    with get_db_session() as db:
        perms = (
            db.query(Permission)
            .order_by(Permission.resource_type, Permission.action)
            .all()
        )
        return [
            {
                "id": p.id,
                "name": p.name,
                "display_name": p.display_name,
                "description": p.description,
                "resource_type": p.resource_type,
                "action": p.action,
            }
            for p in perms
        ]


def _safe_role(raw_role: Optional[str]) -> Role:
    return safe_role(raw_role)
