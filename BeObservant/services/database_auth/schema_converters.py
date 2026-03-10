"""
Database authentication service schema converters for converting between database models and Pydantic schemas used in the API layer. This module provides functions to convert user, group, and API key database models into their corresponding Pydantic schemas defined in the models.access package, allowing for a clear separation between the database layer and the API layer while ensuring that data is properly transformed and validated when being sent to or received from the API. The converters handle the necessary transformations of fields, including permissions aggregation for users and formatting of related data such as group memberships and API key information.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from db_models import Group, Permission, User, UserApiKey
from models.access.api_key_models import ApiKey
from models.access.auth_models import Permission as PermissionEnum
from models.access.group_models import Group as GroupSchema, PermissionInfo
from models.access.user_models import User as UserSchema
from models.access.user_models import UserResponse

if TYPE_CHECKING:
    from services.database_auth_service import DatabaseAuthService

def to_user_schema(service: DatabaseAuthService, user: User) -> UserSchema:
    groups = user.groups or []
    raw_api_keys = getattr(user, "api_keys", None) or []
    api_keys = [service._to_api_key_schema(k) for k in raw_api_keys]

    kwargs = {
        "id": user.id,
        "tenant_id": user.tenant_id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "org_id": user.org_id,
        "role": user.role,
        "group_ids": [g.id for g in groups],
        "is_active": user.is_active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "last_login": user.last_login,
        "needs_password_change": getattr(user, "needs_password_change", False),
        "password_changed_at": getattr(user, "password_changed_at", None),
        "session_invalid_before": getattr(user, "session_invalid_before", None),
        "api_keys": api_keys,
        "mfa_enabled": getattr(user, "mfa_enabled", False),
        "must_setup_mfa": getattr(user, "must_setup_mfa", False),
        "auth_provider": getattr(user, "auth_provider", "local"),
    }

    grafana_uid = getattr(user, "grafana_user_id", None)
    if grafana_uid is not None:
        kwargs["grafana_user_id"] = grafana_uid

    return UserSchema.model_validate(kwargs)

def build_user_response(
    service: DatabaseAuthService,
    user: UserSchema,
    fallback_permissions: Optional[List[str]] = None,
) -> UserResponse:
    permissions = service.get_user_permissions(user) or (fallback_permissions or [])
    coerced_permissions = [_coerce_permission(p) for p in permissions if p is not None]

    return UserResponse(
        **user.model_dump(exclude={"hashed_password"}),
        permissions=coerced_permissions,
        direct_permissions=service.get_user_direct_permissions(user),
    )


def to_api_key_schema(key: UserApiKey) -> ApiKey:
    owner_username = None
    owner = getattr(key, "user", None)
    if owner is not None:
        owner_username = getattr(owner, "username", None)

    return ApiKey(
        id=key.id,
        name=key.name,
        key=key.key,
        otlp_token=getattr(key, "otlp_token", None),
        owner_user_id=getattr(key, "user_id", None),
        owner_username=owner_username,
        is_default=key.is_default,
        is_enabled=key.is_enabled,
        created_at=key.created_at,
        updated_at=key.updated_at,
    )


def to_group_schema(group: Group) -> GroupSchema:
    perms = group.permissions or []
    return GroupSchema(
        id=group.id,
        tenant_id=group.tenant_id,
        name=group.name,
        description=group.description,
        created_at=group.created_at,
        updated_at=group.updated_at,
        permissions=[_to_permission_info(p) for p in perms],
    )


def _to_permission_info(p: Permission) -> PermissionInfo:
    return PermissionInfo(
        id=p.id,
        name=p.name,
        display_name=p.display_name,
        description=p.description,
        resource_type=p.resource_type,
        action=p.action,
    )


def _coerce_permission(p: object) -> PermissionEnum:
    if isinstance(p, PermissionEnum):
        return p
    return PermissionEnum(str(p))
