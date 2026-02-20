"""
Database authentication service utilities for handling user permissions, including functions to retrieve a user's effective permissions based on their role, group memberships, and direct permissions, as well as a function to list all defined permissions in the system. This module provides a common interface for managing and retrieving user permissions within the database authentication service, allowing for consistent permission handling across different parts of the service while ensuring that permissions are properly aggregated from various sources such as roles, groups, and direct assignments.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
from typing import Any, Dict, List

from sqlalchemy.orm import joinedload

from models.access.auth_models import ROLE_PERMISSIONS, Role
from database import get_db_session
from db_models import User, Group, Permission


def get_user_permissions(service, user: User) -> List[str]:
    user_id = getattr(user, "id", None)
    if not user_id:
        return []
    with get_db_session() as db:
        db_user = db.query(User).options(
            joinedload(User.groups).joinedload(Group.permissions),
            joinedload(User.permissions),
        ).filter_by(id=user_id).first()
        return collect_permissions(service, db_user) if db_user else []


def get_user_direct_permissions(service, user: User) -> List[str]:
    user_id = getattr(user, "id", None)
    if not user_id:
        return []
    with get_db_session() as db:
        db_user = db.query(User).options(joinedload(User.permissions)).filter_by(id=user_id).first()
        return [p.name for p in (db_user.permissions or [])] if db_user else []


def collect_permissions(service, user: User) -> List[str]:
    role_perms = {p.value for p in ROLE_PERMISSIONS.get(Role(user.role), [])}
    group_perms = {
        p.name
        for group in user.groups
        if group.is_active
        for p in group.permissions
    }
    direct_perms = {p.name for p in user.permissions}
    return list(role_perms | group_perms | direct_perms)


def list_all_permissions(service) -> List[Dict[str, Any]]:
    with get_db_session() as db:
        return [
            {
                "id": p.id,
                "name": p.name,
                "display_name": p.display_name,
                "description": p.description,
                "resource_type": p.resource_type,
                "action": p.action,
            }
            for p in db.query(Permission).order_by(Permission.resource_type, Permission.action).all()
        ]
