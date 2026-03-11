"""
Analyze and manage delegation of permissions and roles within the authentication system.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import Iterable, Optional, Set, TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from db_models import Group, User
from models.access.auth_models import Role

if TYPE_CHECKING:
    from services.database_auth_service import DatabaseAuthService

ADMIN_PERMISSION_PATTERNS: frozenset[str] = frozenset({"manage:"})
ADMIN_ONLY_PERMISSION_EXACT: frozenset[str] = frozenset({"update:user_permissions", "update:group_permissions"})


def role_to_text(value: object) -> str:
    if isinstance(value, Role):
        return value.value
    normalized = str(value or "").strip().lower()
    if normalized.startswith("role."):
        normalized = normalized.split(".", 1)[1]
    return normalized


def role_rank(value: object, role_rank_map: dict[str, int]) -> int:
    return role_rank_map.get(role_to_text(value), 0)


def is_admin_actor(*, actor_role: Optional[str], actor_is_superuser: bool) -> bool:
    return bool(actor_is_superuser or role_to_text(actor_role) == Role.ADMIN.value)


def is_admin_user(user: Optional[User]) -> bool:
    if not user:
        return False
    return bool(
        getattr(user, "is_superuser", False)
        or role_to_text(getattr(user, "role", None)) == Role.ADMIN.value
    )


def permission_is_admin_only(name: str) -> bool:
    perm = str(name or "").strip()
    if not perm:
        return False
    if perm in ADMIN_ONLY_PERMISSION_EXACT:
        return True
    if any(perm.startswith(prefix) for prefix in ADMIN_PERMISSION_PATTERNS):
        return True
    return perm.startswith("update:") and perm.endswith("permissions")


def normalize_permissions(values: Optional[Iterable[str]]) -> Set[str]:
    return {str(value).strip() for value in (values or []) if str(value).strip()}


def require_actor(actor_user_id: Optional[str], *, purpose: str) -> str:
    if actor_user_id:
        return actor_user_id
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Actor context is required for {purpose}",
    )


def resolve_actor_permissions(
    service: DatabaseAuthService,
    *,
    db: Session,
    actor_user_id: Optional[str],
    tenant_id: str,
    actor_permissions: Optional[list[str]],
) -> Set[str]:
    provided = normalize_permissions(actor_permissions)
    if provided:
        return provided
    if not actor_user_id:
        return set()

    actor = (
        db.query(User)
        .options(
            joinedload(User.groups).joinedload(Group.permissions),
            joinedload(User.permissions),
        )
        .filter_by(id=actor_user_id, tenant_id=tenant_id)
        .first()
    )
    if not actor:
        return set()
    return set(service._collect_permissions(actor))
