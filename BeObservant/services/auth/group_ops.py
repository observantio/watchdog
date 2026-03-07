"""
Group operations for managing user groups, including creating, updating, deleting groups, and managing group memberships and permissions.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Optional, List, Set, Tuple, Iterable

import httpx
from fastapi import HTTPException, status
from sqlalchemy import and_, func
from sqlalchemy.orm import joinedload

from config import config
from database import get_db_session
from db_models import GrafanaDashboard, GrafanaDatasource, GrafanaFolder, Group, Permission, User
from models.access.group_models import GroupCreate, GroupUpdate, Group as GroupSchema
from models.access.auth_models import Role

MUTABLE_GROUP_FIELDS = {"name", "description", "is_active"}
ADMIN_PERMISSION_PATTERNS = ("manage:",)
ADMIN_ONLY_PERMISSION_EXACT = {"update:user_permissions", "update:group_permissions"}

ROLE_RANK = {
    Role.VIEWER.value: 0,
    Role.USER.value: 1,
    Role.ADMIN.value: 2,
}

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _role_to_text(value) -> str:
    if isinstance(value, Role):
        return value.value
    normalized = str(value or "").strip().lower()
    if normalized.startswith("role."):
        normalized = normalized.split(".", 1)[1]
    return normalized


def _role_rank(value) -> int:
    return ROLE_RANK.get(_role_to_text(value), 0)


def _is_admin_actor(*, actor_role: Optional[str], actor_is_superuser: bool) -> bool:
    return bool(actor_is_superuser or _role_to_text(actor_role) == Role.ADMIN.value)


def _permission_is_admin_only(name: str) -> bool:
    perm = str(name or "").strip()
    if not perm:
        return False
    if perm in ADMIN_ONLY_PERMISSION_EXACT:
        return True
    if any(perm.startswith(prefix) for prefix in ADMIN_PERMISSION_PATTERNS):
        return True
    return perm.startswith("update:") and perm.endswith("permissions")


def _normalize_permissions(values: Optional[Iterable[str]]) -> Set[str]:
    return {str(v).strip() for v in (values or []) if str(v).strip()}


def _require_actor(actor_user_id: Optional[str], *, purpose: str) -> str:
    if actor_user_id:
        return actor_user_id
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Actor context is required for {purpose}",
    )


def _get_group(db, *, group_id: str, tenant_id: str, load_members: bool = False) -> Optional[Group]:
    opts = [joinedload(Group.permissions)]
    if load_members:
        opts.append(joinedload(Group.members))
    return (
        db.query(Group)
        .options(*opts)
        .filter_by(id=group_id, tenant_id=tenant_id)
        .first()
    )


def _can_access_group(
    group: Group,
    *,
    actor_user_id: Optional[str],
    actor_role: Optional[str],
    actor_is_superuser: bool,
) -> bool:
    if _is_admin_actor(actor_role=actor_role, actor_is_superuser=actor_is_superuser):
        return True
    actor_id = str(actor_user_id or "").strip()
    if not actor_id:
        return False
    return any(str(getattr(member, "id", "")).strip() == actor_id for member in (group.members or []))


def _resolve_actor_permissions(service, *, db, actor_user_id: str, tenant_id: str, actor_permissions: Optional[List[str]]) -> Set[str]:
    provided = _normalize_permissions(actor_permissions)
    if provided:
        return provided

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


def _get_actor_context(
    service,
    *,
    db,
    actor_user_id: str,
    tenant_id: str,
    actor_role: Optional[str],
    actor_permissions: Optional[List[str]],
    actor_is_superuser: bool,
) -> Tuple[User, str, bool, Set[str]]:
    actor = db.query(User).filter_by(id=actor_user_id, tenant_id=tenant_id).first()
    if not actor:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Actor not found")

    role_text = _role_to_text(actor_role or getattr(actor, "role", None))
    is_superuser = bool(actor_is_superuser or getattr(actor, "is_superuser", False))
    perm_set = _resolve_actor_permissions(
        service,
        db=db,
        actor_user_id=actor_user_id,
        tenant_id=tenant_id,
        actor_permissions=actor_permissions,
    )
    return actor, role_text, is_superuser, perm_set


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
            detail="You can't set group permissions higher than your own",
        )

    if actor_is_admin:
        return

    privileged = sorted(p for p in requested_permissions if _permission_is_admin_only(p))
    if privileged:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can't set group permissions higher than your own",
        )


def create_group(service, group_create: GroupCreate, tenant_id: str, creator_id: Optional[str] = None) -> GroupSchema:
    name = (group_create.name or "").strip()
    if not name:
        raise ValueError("Group name is required")

    with get_db_session() as db:
        exists = (
            db.query(Group.id)
            .filter(func.lower(Group.name) == name.lower(), Group.tenant_id == tenant_id)
            .first()
        )
        if exists:
            raise ValueError(f"Group name '{name}' already exists in this tenant")

        group = Group(
            tenant_id=tenant_id,
            name=name,
            description=group_create.description,
            is_active=True,
        )
        db.add(group)
        db.flush()

        if creator_id:
            creator = db.query(User).filter_by(id=creator_id, tenant_id=tenant_id).first()
            if creator and all(str(member.id) != str(creator.id) for member in (group.members or [])):
                group.members.append(creator)

        if creator_id:
            service._log_audit(db, tenant_id, creator_id, "create_group", "groups", group.id, {"name": group.name})

        db.commit()

        group = _get_group(db, group_id=group.id, tenant_id=tenant_id)
        return service._to_group_schema(group)


def list_groups(
    service,
    tenant_id: str,
    actor_user_id: Optional[str] = None,
    actor_role: Optional[str] = None,
    actor_is_superuser: bool = False,
) -> List[GroupSchema]:
    with get_db_session() as db:
        query = (
            db.query(Group)
            .options(joinedload(Group.permissions), joinedload(Group.members))
            .filter_by(tenant_id=tenant_id)
        )
        if not _is_admin_actor(actor_role=actor_role, actor_is_superuser=actor_is_superuser):
            actor_id = str(actor_user_id or "").strip()
            if not actor_id:
                return []
            query = query.filter(Group.members.any(User.id == actor_id))
        groups = query.all()
        return [service._to_group_schema(g) for g in groups]


def get_group(
    service,
    group_id: str,
    tenant_id: str,
    actor_user_id: Optional[str] = None,
    actor_role: Optional[str] = None,
    actor_is_superuser: bool = False,
) -> Optional[GroupSchema]:
    with get_db_session() as db:
        group = _get_group(db, group_id=group_id, tenant_id=tenant_id, load_members=True)
        if group and not _can_access_group(
            group,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            actor_is_superuser=actor_is_superuser,
        ):
            return None
        return service._to_group_schema(group) if group else None


def delete_group(
    service,
    group_id: str,
    tenant_id: str,
    deleter_id: Optional[str] = None,
    actor_role: Optional[str] = None,
    actor_is_superuser: bool = False,
) -> bool:
    with get_db_session() as db:
        group = _get_group(db, group_id=group_id, tenant_id=tenant_id, load_members=True)
        if not group:
            return False
        if not _can_access_group(
            group,
            actor_user_id=deleter_id,
            actor_role=actor_role,
            actor_is_superuser=actor_is_superuser,
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to manage this group")

        if deleter_id:
            service._log_audit(db, tenant_id, deleter_id, "delete_group", "groups", group_id, {"name": group.name})

        db.delete(group)
        db.commit()
        return True


def update_group(
    service,
    group_id: str,
    group_update: GroupUpdate,
    tenant_id: str,
    updater_id: Optional[str] = None,
    actor_role: Optional[str] = None,
    actor_is_superuser: bool = False,
) -> Optional[GroupSchema]:
    with get_db_session() as db:
        group = _get_group(db, group_id=group_id, tenant_id=tenant_id, load_members=True)
        if not group:
            return None
        if not _can_access_group(
            group,
            actor_user_id=updater_id,
            actor_role=actor_role,
            actor_is_superuser=actor_is_superuser,
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to manage this group")

        update_data = {
            k: v
            for k, v in group_update.model_dump(exclude_unset=True).items()
            if k in MUTABLE_GROUP_FIELDS
        }

        if "name" in update_data:
            candidate = (update_data["name"] or "").strip()
            if not candidate:
                raise ValueError("Group name cannot be empty")

            conflict = (
                db.query(Group.id)
                .filter(
                    func.lower(Group.name) == candidate.lower(),
                    Group.tenant_id == tenant_id,
                    Group.id != group_id,
                )
                .first()
            )
            if conflict:
                raise ValueError(f"Group name '{candidate}' already exists in this tenant")

            update_data["name"] = candidate

        for field, value in update_data.items():
            setattr(group, field, value)

        group.updated_at = _utcnow()

        if updater_id:
            service._log_audit(db, tenant_id, updater_id, "update_group", "groups", group_id, update_data)

        db.commit()

        group = _get_group(db, group_id=group_id, tenant_id=tenant_id)
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
    actor_user_id = _require_actor(actor_user_id, purpose="group permission updates")

    with get_db_session() as db:
        group = _get_group(db, group_id=group_id, tenant_id=tenant_id, load_members=True)
        if not group:
            return False

        _, role_text, is_superuser, perm_set = _get_actor_context(
            service,
            db=db,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            actor_role=actor_role,
            actor_permissions=actor_permissions,
            actor_is_superuser=actor_is_superuser,
        )

        if (
            not _is_admin_actor(actor_role=role_text, actor_is_superuser=is_superuser)
            and "update:group_permissions" not in perm_set
            and "manage:groups" not in perm_set
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing permission to modify group permissions",
            )

        if not _can_access_group(
            group,
            actor_user_id=actor_user_id,
            actor_role=role_text,
            actor_is_superuser=is_superuser,
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to manage this group")

        requested = _normalize_permissions(permission_names)
        existing_permissions = {
            str(getattr(p, "name", "")).strip()
            for p in (group.permissions or [])
            if str(getattr(p, "name", "")).strip()
        }

        requested_for_actor_scope = requested
        if not is_superuser:
            existing_out_of_scope = existing_permissions - perm_set
            requested_out_of_scope = requested - perm_set
            if requested_out_of_scope != existing_out_of_scope:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can't set group permissions higher than your own",
                )
            requested_for_actor_scope = requested & perm_set

        _enforce_permission_delegation(
            requested_permissions=requested_for_actor_scope,
            actor_permissions=perm_set,
            actor_role=role_text,
            actor_is_superuser=is_superuser,
        )

        if not _is_admin_actor(actor_role=role_text, actor_is_superuser=is_superuser):
            has_admin_member = any(
                _role_to_text(getattr(member, "role", None)) == Role.ADMIN.value
                for member in (group.members or [])
            )
            if has_admin_member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only administrators can modify permissions for groups containing admins",
                )

        if requested:
            known_names = {
                name
                for (name,) in db.query(Permission.name).filter(Permission.name.in_(requested)).all()
            }
            unknown = requested - known_names
            if unknown:
                raise ValueError(f"Unknown permissions: {sorted(unknown)}")

            group.permissions = db.query(Permission).filter(Permission.name.in_(known_names)).all()
        else:
            group.permissions = []

        service._log_audit(
            db,
            tenant_id,
            actor_user_id,
            "update_group_permissions",
            "groups",
            group_id,
            {"permissions": sorted({p.name for p in group.permissions})},
        )

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
    actor_user_id = _require_actor(actor_user_id, purpose="group membership updates")

    with get_db_session() as db:
        group = _get_group(db, group_id=group_id, tenant_id=tenant_id, load_members=True)
        if not group:
            return False

        _, role_text, is_superuser, perm_set = _get_actor_context(
            service,
            db=db,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            actor_role=actor_role,
            actor_permissions=actor_permissions,
            actor_is_superuser=actor_is_superuser,
        )

        if (
            not _is_admin_actor(actor_role=role_text, actor_is_superuser=is_superuser)
            and "update:group_members" not in perm_set
            and "manage:groups" not in perm_set
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing permission to modify group memberships",
            )

        if not _can_access_group(
            group,
            actor_user_id=actor_user_id,
            actor_role=role_text,
            actor_is_superuser=is_superuser,
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to manage this group")

        existing_member_ids = {str(u.id) for u in (group.members or [])}

        members: List[User] = []
        requested_ids = [str(u).strip() for u in (user_ids or []) if str(u).strip()]
        if requested_ids:
            members = (
                db.query(User)
                .filter(and_(User.id.in_(requested_ids), User.tenant_id == tenant_id))
                .all()
            )
            found_ids = {str(u.id) for u in members}
            missing = set(requested_ids) - found_ids
            if missing:
                raise ValueError(f"Users not found in tenant: {sorted(missing)}")

        if not _is_admin_actor(actor_role=role_text, actor_is_superuser=is_superuser):
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

            if any(_role_rank(getattr(u, "role", None)) > _role_rank(role_text) for u in members):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot modify group membership for users with higher role",
                )

        requested_member_ids = {str(u.id) for u in members}
        removed_member_ids = sorted(existing_member_ids - requested_member_ids)

        group.members = members

        if removed_member_ids:
            _prune_removed_member_grafana_group_shares(
                db,
                tenant_id=tenant_id,
                group_id=group_id,
                removed_user_ids=removed_member_ids,
            )

        if not members:
            service._log_audit(
                db,
                tenant_id,
                actor_user_id,
                "delete_group",
                "groups",
                group_id,
                {"reason": "auto_delete_empty_group", "name": group.name},
            )
            db.delete(group)
            db.commit()
            return True

        service._log_audit(
            db,
            tenant_id,
            actor_user_id,
            "update_group_members",
            "groups",
            group_id,
            {"user_ids": requested_ids},
        )

        db.commit()
        return True


def _prune_removed_member_grafana_group_shares(
    db,
    *,
    tenant_id: str,
    group_id: str,
    removed_user_ids: List[str],
) -> None:
    target_group_id = str(group_id)
    removed_ids = [str(uid) for uid in (removed_user_ids or []) if str(uid).strip()]
    if not removed_ids:
        return

    def _prune(model) -> None:
        rows = (
            db.query(model)
            .options(joinedload(model.shared_groups))
            .filter(
                model.tenant_id == tenant_id,
                model.created_by.in_(removed_ids),
                model.visibility == "group",
                model.shared_groups.any(Group.id == target_group_id),
            )
            .all()
        )
        for row in rows:
            row.shared_groups = [g for g in (row.shared_groups or []) if str(getattr(g, "id", "")) != target_group_id]
            if not row.shared_groups:
                row.visibility = "private"

    _prune(GrafanaDashboard)
    _prune(GrafanaDatasource)
    _prune(GrafanaFolder)
    removed_usernames = [
        str(username).strip()
        for (username,) in (
            db.query(User.username)
            .filter(User.tenant_id == tenant_id, User.id.in_(removed_ids))
            .all()
        )
        if str(username).strip()
    ]
    _prune_removed_member_benotified_group_shares(
        tenant_id=tenant_id,
        group_id=target_group_id,
        removed_user_ids=removed_ids,
        removed_usernames=removed_usernames,
    )


def _prune_removed_member_benotified_group_shares(
    *,
    tenant_id: str,
    group_id: str,
    removed_user_ids: List[str],
    removed_usernames: Optional[List[str]] = None,
) -> None:
    base_url = str(getattr(config, "BENOTIFIED_URL", "") or "").strip().rstrip("/")
    service_token = config.get_secret("BENOTIFIED_SERVICE_TOKEN")
    if not base_url or not service_token:
        logger.warning("Skipping BeNotified group-share prune; BeNotified URL or service token is missing")
        return

    payload = {
        "tenantId": tenant_id,
        "groupId": group_id,
        "removedUserIds": [str(uid).strip() for uid in (removed_user_ids or []) if str(uid).strip()],
        "removedUsernames": [str(name).strip() for name in (removed_usernames or []) if str(name).strip()],
    }
    if not payload["removedUserIds"]:
        return

    target = f"{base_url}/internal/v1/api/alertmanager/access/group-shares/prune"
    try:
        with httpx.Client(timeout=float(config.BENOTIFIED_TIMEOUT_SECONDS)) as client:
            response = client.post(
                target,
                headers={"X-Service-Token": service_token},
                json=payload,
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to propagate group-share revocation to BeNotified",
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to propagate group-share revocation to BeNotified",
        ) from exc
