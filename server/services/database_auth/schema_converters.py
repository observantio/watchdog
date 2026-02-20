"""
Database authentication service schema converters for converting between database models and Pydantic schemas used in the API layer. This module provides functions to convert user, group, and API key database models into their corresponding Pydantic schemas defined in the models.access package, allowing for a clear separation between the database layer and the API layer while ensuring that data is properly transformed and validated when being sent to or received from the API. The converters handle the necessary transformations of fields, including permissions aggregation for users and formatting of related data such as group memberships and API key information.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
from typing import Optional, Dict, Any, List

from models.access.user_models import User as UserSchema
from models.access.api_key_models import ApiKey
from models.access.group_models import Group as GroupSchema, PermissionInfo
from models.access.user_models import UserResponse
from models.access.auth_models import Permission as PermissionEnum


def to_user_schema(service, user) -> UserSchema:
    kwargs = dict(
        id=user.id,
        tenant_id=user.tenant_id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        org_id=user.org_id,
        role=user.role,
        group_ids=[g.id for g in (user.groups or [])],
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login=user.last_login,
        needs_password_change=getattr(user, "needs_password_change", False),
        api_keys=service.list_api_keys(user.id),
        mfa_enabled=getattr(user, "mfa_enabled", False),
        must_setup_mfa=getattr(user, "must_setup_mfa", False),
    )
    grafana_uid = getattr(user, "grafana_user_id", None)
    if grafana_uid is not None:
        kwargs["grafana_user_id"] = grafana_uid
    return UserSchema(**kwargs)


def build_user_response(service, user: UserSchema, fallback_permissions: Optional[List[str]] = None) -> UserResponse:
    permissions = service.get_user_permissions(user) or (fallback_permissions or [])
    # coerce string permissions into Permission enum values for the UserResponse model
    coerced_permissions = [PermissionEnum(p) if isinstance(p, str) else p for p in (permissions or [])]
    return UserResponse(
        **user.model_dump(exclude={"hashed_password"}),
        permissions=coerced_permissions,
        direct_permissions=service.get_user_direct_permissions(user),
    )


def to_api_key_schema(service, key) -> ApiKey:
    return ApiKey(
        id=key.id,
        name=key.name,
        key=key.key,
        otlp_token=getattr(key, "otlp_token", None),
        owner_user_id=getattr(key, "user_id", None),
        owner_username=getattr(getattr(key, 'user', None), 'username', None),
        is_default=key.is_default,
        is_enabled=key.is_enabled,
        created_at=key.created_at,
        updated_at=key.updated_at,
    )


def to_group_schema(service, group) -> GroupSchema:
    return GroupSchema(
        id=group.id,
        tenant_id=group.tenant_id,
        name=group.name,
        description=group.description,
        created_at=group.created_at,
        updated_at=group.updated_at,
        permissions=[
            PermissionInfo(
                id=p.id,
                name=p.name,
                display_name=p.display_name,
                description=p.description,
                resource_type=p.resource_type,
                action=p.action,
            )
            for p in (group.permissions or [])
        ],
    )
