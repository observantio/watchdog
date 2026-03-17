"""
Group management endpoints for Watchdog authentication router.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import List

from fastapi import Depends, HTTPException, status

from middleware.dependencies import auth_service, require_any_permission_with_scope, require_permission_with_scope
from middleware.error_handlers import handle_route_errors
from models.access.auth_models import Permission, TokenData
from models.access.group_models import Group, GroupCreate, GroupMembersUpdate, GroupUpdate
from services.auth.helper import invalidate_grafana_proxy_auth_cache, perms_check

from .shared import GROUP_NOT_FOUND, router, rtp


@router.get("/groups", response_model=List[Group])
async def list_groups(current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_GROUPS, "auth"))) -> List[Group]:
    return await rtp(
        auth_service.list_groups,
        current_user.tenant_id,
        current_user.user_id,
        current_user.role,
        bool(getattr(current_user, "is_superuser", False)),
    )


@router.post("/groups", response_model=Group)
@handle_route_errors()
async def create_group(
    group_create: GroupCreate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.CREATE_GROUPS, Permission.MANAGE_GROUPS], "auth")
    ),
) -> Group:
    group = await rtp(auth_service.create_group, group_create, current_user.tenant_id, current_user.user_id)
    invalidate_grafana_proxy_auth_cache()
    return group


@router.get("/groups/{group_id}", response_model=Group)
async def get_group(
    group_id: str,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.READ_GROUPS, Permission.MANAGE_GROUPS], "auth")
    ),
) -> Group:
    group = await rtp(
        auth_service.get_group,
        group_id,
        current_user.tenant_id,
        current_user.user_id,
        current_user.role,
        bool(getattr(current_user, "is_superuser", False)),
    )
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GROUP_NOT_FOUND)
    return group


@router.put("/groups/{group_id}", response_model=Group)
@handle_route_errors()
async def update_group(
    group_id: str,
    group_update: GroupUpdate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_GROUPS, Permission.MANAGE_GROUPS], "auth")
    ),
) -> Group:
    group = await rtp(
        auth_service.update_group,
        group_id,
        group_update,
        current_user.tenant_id,
        current_user.user_id,
        current_user.role,
        bool(getattr(current_user, "is_superuser", False)),
    )
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GROUP_NOT_FOUND)
    invalidate_grafana_proxy_auth_cache()
    return group


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: str,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.DELETE_GROUPS, Permission.MANAGE_GROUPS], "auth")
    ),
) -> dict[str, str]:
    if not await rtp(
        auth_service.delete_group,
        group_id,
        current_user.tenant_id,
        current_user.user_id,
        current_user.role,
        bool(getattr(current_user, "is_superuser", False)),
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, GROUP_NOT_FOUND)
    invalidate_grafana_proxy_auth_cache()
    return {"message": "Group deleted successfully"}


@router.put("/groups/{group_id}/permissions")
async def update_group_permissions(
    group_id: str,
    permission_names: List[str],
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_GROUP_PERMISSIONS, Permission.MANAGE_GROUPS], "auth")
    ),
) -> dict[str, object]:
    if not await rtp(
        auth_service.update_group_permissions,
        group_id,
        permission_names,
        current_user.tenant_id,
        current_user.user_id,
        current_user.role,
        list(perms_check(current_user)),
        bool(getattr(current_user, "is_superuser", False)),
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, GROUP_NOT_FOUND)
    invalidate_grafana_proxy_auth_cache()
    return {"success": True, "permissions": permission_names}


@router.put("/groups/{group_id}/members")
async def update_group_members(
    group_id: str,
    members: GroupMembersUpdate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_GROUP_MEMBERS, Permission.MANAGE_GROUPS], "auth")
    ),
) -> dict[str, object]:
    if not await rtp(
        auth_service.update_group_members,
        group_id,
        members.user_ids,
        current_user.tenant_id,
        current_user.user_id,
        current_user.role,
        list(perms_check(current_user)),
        bool(getattr(current_user, "is_superuser", False)),
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, GROUP_NOT_FOUND)
    invalidate_grafana_proxy_auth_cache()
    return {"success": True, "user_ids": members.user_ids}
