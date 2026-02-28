"""
User operations for managing user accounts, including creating, updating, deleting users, and managing user permissions and group memberships.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from datetime import datetime, timezone
import secrets
from typing import Optional, List, Set

from fastapi import HTTPException, status
from sqlalchemy import and_, func
from sqlalchemy.orm import joinedload

from config import config
from database import get_db_session
from db_models import User, Group, Permission
from models.access.user_models import UserCreate, UserUpdate, User as UserSchema
from models.access.auth_models import Role

_MUTABLE_USER_FIELDS = {
    "full_name", "email", "is_active", "role", "org_id",
    "must_setup_mfa", "needs_password_change",
}
_SENSITIVE_USER_FIELDS = {"role", "org_id", "group_ids"}
_ROLE_RANK = {
    Role.VIEWER.value: 0,
    Role.USER.value: 1,
    Role.ADMIN.value: 2,
}
_ADMIN_PERMISSION_PATTERNS = ("manage:",)
_ADMIN_ONLY_PERMISSION_EXACT = {"update:user_permissions", "update:group_permissions"}


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
    actor_user_id: Optional[str],
    tenant_id: str,
    actor_permissions: Optional[List[str]],
) -> Set[str]:
    provided = _normalize_permissions(actor_permissions)
    if provided:
        return provided
    if not actor_user_id:
        return set()
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


def get_user_by_id(service, user_id: str, tenant_id: Optional[str] = None) -> Optional[UserSchema]:
    service._lazy_init()
    with get_db_session() as db:
        query = db.query(User).options(
            joinedload(User.groups),
            joinedload(User.permissions),
            joinedload(User.api_keys),
        ).filter_by(id=user_id)
        if tenant_id is not None:
            query = query.filter_by(tenant_id=tenant_id)
        user = query.first()
        if not user:
            return None
        return service._to_user_schema(user)


def get_user_by_username(service, username: str) -> Optional[UserSchema]:
    username = (username or "").strip().lower()
    with get_db_session() as db:
        user = (
            db.query(User)
            .options(joinedload(User.api_keys))
            .filter(func.lower(User.username) == username)
            .first()
        )
        if not user:
            return None
        return service._to_user_schema(user)


def create_user(
    service,
    user_create: UserCreate,
    tenant_id: str,
    creator_id: Optional[str] = None,
    actor_role: Optional[str] = None,
    actor_permissions: Optional[List[str]] = None,
    actor_is_superuser: bool = False,
) -> UserSchema:
    with get_db_session() as db:
        requested_role = _role_to_text(getattr(user_create, "role", None) or Role.USER.value)
        actor_role_text = _role_to_text(actor_role)

        if creator_id:
            creator = db.query(User).filter_by(id=creator_id, tenant_id=tenant_id).first()
            if not creator:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Creator account is not valid for this tenant",
                )
            if not actor_role_text:
                actor_role_text = _role_to_text(getattr(creator, "role", None))
            actor_is_superuser = bool(actor_is_superuser or getattr(creator, "is_superuser", False))
        else:
            requested_role = Role.USER.value
            actor_role_text = Role.USER.value

        actor_is_admin = _is_admin_actor(actor_role=actor_role_text, actor_is_superuser=actor_is_superuser)

        if not actor_is_admin:
            if _role_rank(requested_role) > _role_rank(actor_role_text):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot assign a role higher than your own",
                )
            if requested_role == Role.ADMIN.value:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only administrators can assign admin role",
                )
            if (getattr(user_create, "group_ids", None) or []):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only administrators can assign initial group memberships",
                )
            requested_org = str(getattr(user_create, "org_id", "") or "").strip()
            if requested_org and requested_org != config.DEFAULT_ORG_ID:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only administrators can assign tenant scope during user creation",
                )

        normalized_username = (user_create.username or "").strip().lower()
        if db.query(User).filter(func.lower(User.username) == normalized_username).first():
            raise ValueError("Username already exists")

        normalized_email = (user_create.email or "").strip().lower()
        if db.query(User).filter(func.lower(User.email) == normalized_email).first():
            raise ValueError("Email already exists")

        is_external = service.is_external_auth_enabled()
        external_subject = None
        auth_provider = "local"

        if is_external:
            external_subject = service.provision_external_user(
                email=normalized_email,
                username=normalized_username,
                full_name=user_create.full_name,
            )
            if config.KEYCLOAK_USER_PROVISIONING_ENABLED and not external_subject:
                raise ValueError("External identity provisioning failed; user was not created")
            auth_provider = config.AUTH_PROVIDER

        raw_password = user_create.password
        if is_external and not raw_password:
            raw_password = secrets.token_urlsafe(24)
        if not raw_password:
            raise ValueError("Password is required when local authentication is enabled")

        org_value = config.DEFAULT_ORG_ID
        if actor_is_admin:
            requested_org = str(getattr(user_create, "org_id", "") or "").strip()
            if requested_org:
                org_value = requested_org

        user = User(
            tenant_id=tenant_id,
            username=normalized_username,
            email=normalized_email,
            full_name=user_create.full_name,
            org_id=org_value,
            role=requested_role,
            is_active=user_create.is_active,
            hashed_password=service.hash_password(raw_password),
            needs_password_change=(not is_external),
            password_changed_at=datetime.now(timezone.utc),
            auth_provider=auth_provider,
            external_subject=external_subject,
            must_setup_mfa=getattr(user_create, "must_setup_mfa", False),
        )

        if user_create.group_ids:
            groups = db.query(Group).filter(
                and_(
                    Group.id.in_(user_create.group_ids),
                    Group.tenant_id == tenant_id,
                )
            ).all()
            user.groups.extend(groups)

        db.add(user)
        db.flush()
        service._ensure_default_api_key(db, user)

        if creator_id:
            service._log_audit(db, tenant_id, creator_id, "create_user", "users", user.id, {
                "username": user.username,
                "role": user.role,
            })

        db.commit()
        return service._to_user_schema(user)


def list_users(
    service, tenant_id: str, *, limit: Optional[int] = None, offset: int = 0
) -> List[UserSchema]:
    try:
        requested_limit = int(limit) if limit is not None else int(getattr(config, "DEFAULT_QUERY_LIMIT", 100))
        max_limit = int(getattr(config, "MAX_QUERY_LIMIT", 5000))
        limit = max(1, min(requested_limit, max_limit))
        offset = max(0, int(offset))
    except (TypeError, ValueError):
        raise ValueError("limit and offset must be integers")

    with get_db_session() as db:
        users = (
            db.query(User)
            .options(joinedload(User.groups), joinedload(User.api_keys))
            .filter_by(tenant_id=tenant_id)
            .limit(limit)
            .offset(offset)
            .all()
        )
        return [service._to_user_schema(u) for u in users]


def update_user(
    service, user_id: str, user_update: UserUpdate, tenant_id: str, updater_id: Optional[str] = None
) -> Optional[UserSchema]:
    with get_db_session() as db:
        user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
        if not user:
            return None

        update_data = {
            k: v for k, v in user_update.model_dump(exclude_unset=True).items()
            if k in _MUTABLE_USER_FIELDS or k == "group_ids"
        }

        if updater_id and user_id == updater_id and update_data.get("is_active") is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot disable your own account",
            )

        updater_user = None
        if updater_id:
            updater_user = db.query(User).filter_by(id=updater_id, tenant_id=tenant_id).first()
        updater_is_superuser = bool(getattr(updater_user, "is_superuser", False))
        updater_role_text = _role_to_text(getattr(updater_user, "role", ""))

        if user.role == Role.ADMIN and updater_user and updater_role_text != Role.ADMIN.value and not updater_is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can modify admin accounts",
            )

        if updater_user and not updater_is_superuser:
            if _SENSITIVE_USER_FIELDS & set(update_data.keys()) and updater_role_text != Role.ADMIN.value:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only administrators can modify role, tenant scope, or group memberships",
                )

            requested_role = update_data.get("role")
            if requested_role is not None and _role_rank(requested_role) > _role_rank(updater_role_text):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot assign a role higher than your own",
                )

        if getattr(user, "auth_provider", "local") != "local" and "email" in update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is managed by the external identity provider",
            )

        for field, value in update_data.items():
            if field == "group_ids" and value is not None:
                groups = db.query(Group).filter(
                    and_(
                        Group.id.in_(value),
                        Group.tenant_id == tenant_id,
                    )
                ).all()
                user.groups = groups
            else:
                setattr(user, field, value)

        user.updated_at = datetime.now(timezone.utc)

        if "org_id" in update_data:
            service._ensure_default_api_key(db, user)

        if updater_id:
            service._log_audit(db, tenant_id, updater_id, "update_user", "users", user_id, update_data)

        db.commit()
        return service._to_user_schema(user)


def set_grafana_user_id(service, user_id: str, grafana_user_id: int, tenant_id: str) -> bool:
    with get_db_session() as db:
        user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
        if not user:
            return False
        user.grafana_user_id = grafana_user_id
        db.commit()
        return True


def delete_user(service, user_id: str, tenant_id: str, deleter_id: Optional[str] = None) -> bool:
    if deleter_id and user_id == deleter_id:
        raise ValueError("Users cannot delete their own account")

    with get_db_session() as db:
        user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
        if not user:
            return False
        if user.role == Role.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin accounts cannot be deleted",
            )

        if deleter_id:
            deleter = db.query(User).filter_by(id=deleter_id, tenant_id=tenant_id).first()
            if not deleter:
                return False
            if deleter.role != Role.ADMIN and not deleter.is_superuser:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only administrators can delete users",
                )

        if deleter_id:
            service._log_audit(db, tenant_id, deleter_id, "delete_user", "users", user_id, {
                "username": user.username,
            })

        db.delete(user)
        db.commit()
        return True


def update_user_permissions(
    service,
    user_id: str,
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
                detail="Actor context is required for permission updates",
            )

        user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
        if not user:
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

        if not _is_admin_actor(actor_role=actor_role_text, actor_is_superuser=actor_is_superuser):
            if _role_to_text(getattr(user, "role", None)) == Role.ADMIN.value:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only administrators can modify admin permissions",
                )
            if _role_rank(getattr(user, "role", None)) > _role_rank(actor_role_text):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot modify permissions of users with higher role",
                )

        normalized_requested = _normalize_permissions(permission_names)
        _enforce_permission_delegation(
            requested_permissions=normalized_requested,
            actor_permissions=actor_perm_set,
            actor_role=actor_role_text,
            actor_is_superuser=actor_is_superuser,
        )

        known_names = {
            name for (name,) in db.query(Permission.name).filter(Permission.name.in_(permission_names)).all()
        }
        unknown = normalized_requested - known_names
        if unknown:
            raise ValueError(f"Unknown permissions: {sorted(unknown)}")

        permissions = db.query(Permission).filter(Permission.name.in_(known_names)).all()
        user.permissions = permissions

        service._log_audit(
            db,
            tenant_id,
            actor_user_id,
            "update_user_permissions",
            "users",
            user_id,
            {"permissions": sorted(known_names)},
        )
        db.commit()
        return True
