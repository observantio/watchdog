"""
Group operations for managing user groups, including creating, updating, deleting groups, and managing group memberships and permissions.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from datetime import datetime, timezone
from typing import Optional, List, Set

from fastapi import HTTPException, status
from sqlalchemy import and_, func
from sqlalchemy.orm import joinedload

from database import get_db_session
from db_models import Group, Permission, User
from models.access.group_models import GroupCreate, GroupUpdate, Group as GroupSchema
from models.access.auth_models import Role

_MUTABLE_GROUP_FIELDS = {"name", "description", "is_active"}
_ADMIN_PERMISSION_PATTERNS = ("manage:",)
_ADMIN_ONLY_PERMISSION_EXACT = {"update:user_permissions", "update:group_permissions"}

_ROLE_RANK = {
    Role.VIEWER.value: 0,
    Role.USER.value: 1,
    Role.ADMIN.value: 2,
}


def _role_to_text(value) -> str:
    if isinstance(value, Role):
        return value.value
    normalized = str(value or "").strip().lower()
    if normalized.startswith("role."):
        normalized = normalized.split(".", 1)[1]
    return normalized


def _role_rank(value) -> int:
    return _ROLE_RANK.get(_role_to_text(value), 0)


def _is_admin_actor(*, actor_role: Optional[str], actor_is_superuser: bool) -> bool:
    return bool(actor_is_superuser or _role_to_text(actor_role) == Role.ADMIN.value)


def _permission_is_admin_only(name: str) -> bool:
    perm = str(name or "").strip()
    if not perm:
        return False
    if perm in _ADMIN_ONLY_PERMISSION_EXACT:
        return True
    if any(perm.startswith(prefix) for prefix in _ADMIN_PERMISSION_PATTERNS):
        return True
    return perm.startswith("update:") and perm.endswith("permissions")


def _normalize_permissions(values: Optional[List[str]]) -> Set[str]:
    return {str(v).strip() for v in (values or []) if str(v).strip()}


def _resolve_actor_permissions(
    service,
    *,
    db,
    actor_user_id: str,
    tenant_id: str,
    actor_permissions: Optional[List[str]],
) -> Set[str]:
    provided = _normalize_permissions(actor_permissions)
    if provided:
        return provided
    actor = (
        db.query(User)
        .options(joinedload(User.groups).joinedload(Group.permissions), joinedload(User.permissions))
        .filter_by(id=actor_user_id, tenant_id=tenant_id)
        .first()
    )
    if not actor:
        return set()
    return set(service._collect_permissions(actor))


def _enforce_permission_delegation(
    *,
    requested_permissions: Set[str],
    actor_permissions: Set[str],
    actor_role: Optional[str],
    actor_is_superuser: bool,
) -> None:
    if actor_is_superuser:
        return
    actor_is_admin = _is_admin_actor(actor_role=actor_role, actor_is_superuser=False)
    if not requested_permissions.issubset(actor_permissions):
        forbidden = sorted(requested_permissions - actor_permissions)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot grant permissions outside your own scope: {forbidden}",
        )
    if actor_is_admin:
        return
    privileged = sorted(p for p in requested_permissions if _permission_is_admin_only(p))
    if privileged:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only administrators can grant privileged permissions: {privileged}",
        )

def create_group(service, group_create: GroupCreate, tenant_id: str, creator_id: Optional[str] = None) -> GroupSchema:
    with get_db_session() as db:
        if db.query(Group).filter(
            func.lower(Group.name) == group_create.name.strip().lower(),
            Group.tenant_id == tenant_id,
        ).first():
            raise ValueError(f"Group name '{group_create.name}' already exists in this tenant")

        group = Group(
            tenant_id=tenant_id,
            name=group_create.name.strip(),
            description=group_create.description,
            is_active=True,
        )
        db.add(group)
        db.flush()

        if creator_id:
            service._log_audit(db, tenant_id, creator_id, "create_group", "groups", group.id, {
                "name": group.name,
            })

        db.commit()
        group = db.query(Group).options(joinedload(Group.permissions)).filter_by(id=group.id).first()
        return service._to_group_schema(group)


def list_groups(service, tenant_id: str) -> List[GroupSchema]:
    with get_db_session() as db:
        groups = (
            db.query(Group)
            .options(joinedload(Group.permissions))
            .filter_by(tenant_id=tenant_id)
            .all()
        )
        return [service._to_group_schema(g) for g in groups]


def get_group(service, group_id: str, tenant_id: str) -> Optional[GroupSchema]:
    with get_db_session() as db:
        group = (
            db.query(Group)
            .options(joinedload(Group.permissions))
            .filter_by(id=group_id, tenant_id=tenant_id)
            .first()
        )
        if not group:
            return None
        return service._to_group_schema(group)


def delete_group(service, group_id: str, tenant_id: str, deleter_id: Optional[str] = None) -> bool:
    with get_db_session() as db:
        group = db.query(Group).filter_by(id=group_id, tenant_id=tenant_id).first()
        if not group:
            return False

        if deleter_id:
            service._log_audit(db, tenant_id, deleter_id, "delete_group", "groups", group_id, {
                "name": group.name,
            })

        db.delete(group)
        db.commit()
        return True


def update_group(
    service, group_id: str, group_update: GroupUpdate, tenant_id: str, updater_id: Optional[str] = None
) -> Optional[GroupSchema]:
    with get_db_session() as db:
        group = db.query(Group).filter_by(id=group_id, tenant_id=tenant_id).first()
        if not group:
            return None

        update_data = {
            k: v for k, v in group_update.model_dump(exclude_unset=True).items()
            if k in _MUTABLE_GROUP_FIELDS
        }

        if "name" in update_data:
            name_candidate = update_data["name"].strip().lower()
            conflict = db.query(Group).filter(
                func.lower(Group.name) == name_candidate,
                Group.tenant_id == tenant_id,
                Group.id != group_id,
            ).first()
            if conflict:
                raise ValueError(f"Group name '{update_data['name']}' already exists in this tenant")
            update_data["name"] = update_data["name"].strip()

        for field, value in update_data.items():
            setattr(group, field, value)

        group.updated_at = datetime.now(timezone.utc)

        if updater_id:
            service._log_audit(db, tenant_id, updater_id, "update_group", "groups", group_id, update_data)

        db.commit()
        group = db.query(Group).options(joinedload(Group.permissions)).filter_by(id=group_id).first()
        return service._to_group_schema(group)


def update_group_permissions(
    service,
    group_id: str,
    permission_names: List[str],
    tenant_id: str,
    actor_user_id: Optional[str] = None,
    actor_role: Optional[str] = None,
    actor_permissions: Optional[List[str]] = None,
    actor_is_superuser: bool = False,
) -> bool:
    with get_db_session() as db:
        if not actor_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Actor context is required for group permission updates",
            )
        group = db.query(Group).filter_by(id=group_id, tenant_id=tenant_id).first()
        if not group:
            return False

        actor = db.query(User).filter_by(id=actor_user_id, tenant_id=tenant_id).first()
        if not actor:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Actor not found")
        actor_role_text = _role_to_text(actor_role or getattr(actor, "role", None))
        actor_is_superuser = bool(actor_is_superuser or getattr(actor, "is_superuser", False))
        actor_perm_set = _resolve_actor_permissions(
            service,
            db=db,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            actor_permissions=actor_permissions,
        )
        if (
            not _is_admin_actor(actor_role=actor_role_text, actor_is_superuser=actor_is_superuser)
            and "update:group_members" not in actor_perm_set
            and "manage:groups" not in actor_perm_set
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing permission to modify group memberships",
            )

        normalized_requested = _normalize_permissions(permission_names)
        _enforce_permission_delegation(
            requested_permissions=normalized_requested,
            actor_permissions=actor_perm_set,
            actor_role=actor_role_text,
            actor_is_superuser=actor_is_superuser,
        )

        if not _is_admin_actor(actor_role=actor_role_text, actor_is_superuser=actor_is_superuser):
            has_admin_member = any(
                _role_to_text(getattr(member, "role", None)) == Role.ADMIN.value
                for member in (group.members or [])
            )
            if has_admin_member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only administrators can modify permissions for groups containing admins",
                )

        known_names = {
            name for (name,) in db.query(Permission.name).filter(Permission.name.in_(permission_names)).all()
        }
        unknown = normalized_requested - known_names
        if unknown:
            raise ValueError(f"Unknown permissions: {sorted(unknown)}")

        permissions = db.query(Permission).filter(Permission.name.in_(known_names)).all()
        group.permissions = permissions

        service._log_audit(db, tenant_id, actor_user_id, "update_group_permissions", "groups", group_id, {
            "permissions": list(known_names),
        })

        db.commit()
        return True


def update_group_members(
    service,
    group_id: str,
    user_ids: List[str],
    tenant_id: str,
    actor_user_id: Optional[str] = None,
    actor_role: Optional[str] = None,
    actor_permissions: Optional[List[str]] = None,
    actor_is_superuser: bool = False,
) -> bool:
    with get_db_session() as db:
        if not actor_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Actor context is required for group membership updates",
            )

        group = db.query(Group).filter_by(id=group_id, tenant_id=tenant_id).first()
        if not group:
            return False

        actor = db.query(User).filter_by(id=actor_user_id, tenant_id=tenant_id).first()
        if not actor:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Actor not found")
        actor_role_text = _role_to_text(actor_role or getattr(actor, "role", None))
        actor_is_superuser = bool(actor_is_superuser or getattr(actor, "is_superuser", False))
        actor_perm_set = _resolve_actor_permissions(
            service,
            db=db,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            actor_permissions=actor_permissions,
        )

        members = []
        if user_ids:
            members = db.query(User).filter(
                and_(
                    User.id.in_(user_ids),
                    User.tenant_id == tenant_id,
                )
            ).all()
            found_ids = {str(u.id) for u in members}
            missing = set(user_ids) - found_ids
            if missing:
                raise ValueError(f"Users not found in tenant: {sorted(missing)}")

        if not _is_admin_actor(actor_role=actor_role_text, actor_is_superuser=actor_is_superuser):
            existing_admin_ids = {
                str(u.id)
                for u in (group.members or [])
                if _role_to_text(getattr(u, "role", None)) == Role.ADMIN.value
            }
            requested_admin_ids = {
                str(u.id)
                for u in members
                if _role_to_text(getattr(u, "role", None)) == Role.ADMIN.value
            }
            if existing_admin_ids or requested_admin_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only administrators can modify group memberships for admin users",
                )
            if any(_role_rank(getattr(u, "role", None)) > _role_rank(actor_role_text) for u in members):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot modify group membership for users with higher role",
                )

        group.members = members

        service._log_audit(db, tenant_id, actor_user_id, "update_group_members", "groups", group_id, {
            "user_ids": user_ids,
        })

        db.commit()
        return True
