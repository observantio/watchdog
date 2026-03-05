"""
User authentication and registration endpoints for Be Observant access management.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import List

from fastapi import Depends, HTTPException, Query, status

from config import config
from middleware.dependencies import (
    auth_service,
    require_any_permission_with_scope,
    require_authenticated_with_scope,
)
from middleware.error_handlers import handle_route_errors
from models.access.auth_models import Permission, ROLE_PERMISSIONS, Role, TokenData
from models.access.user_models import TempPasswordResetResponse, UserCreate, UserPasswordUpdate, UserResponse, UserUpdate
from services.auth.helper import (
    invalidate_grafana_proxy_auth_cache,
    is_admin_check,
    perms_check,
    role_permission_strings,
)

from .shared import USER_NOT_FOUND, logger, notification_service, router, rtp


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: TokenData = Depends(require_authenticated_with_scope("auth"))):
    user = await rtp(auth_service.get_user_by_id, current_user.user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    user_response = await rtp(auth_service.build_user_response, user, current_user.permissions)
    user_response.api_keys = await rtp(auth_service.list_api_keys, current_user.user_id)
    return user_response


@router.put("/me", response_model=UserResponse)
async def update_current_user_info(
    user_update: UserUpdate,
    current_user: TokenData = Depends(require_authenticated_with_scope("auth")),
):
    data = user_update.model_dump(exclude_unset=True)
    for field in ("role", "group_ids", "is_active"):
        data.pop(field, None)
    updated = await rtp(
        auth_service.update_user,
        current_user.user_id,
        UserUpdate(**data),
        current_user.tenant_id,
        current_user.user_id,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    user_response = await rtp(auth_service.build_user_response, updated, current_user.permissions)
    user_response.api_keys = await rtp(auth_service.list_api_keys, current_user.user_id)
    return user_response


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(
        require_any_permission_with_scope(
            [Permission.READ_USERS, Permission.MANAGE_USERS, Permission.MANAGE_TENANTS],
            "auth",
        )
    ),
):
    users = await rtp(auth_service.list_users, current_user.tenant_id, limit=limit, offset=offset)
    return [await rtp(auth_service.build_user_response, user, role_permission_strings(user.role)) for user in users]


@router.post("/users", response_model=UserResponse)
@handle_route_errors()
async def create_user(
    user_create: UserCreate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.CREATE_USERS, Permission.MANAGE_USERS], "auth")
    ),
):
    user = await rtp(
        auth_service.create_user,
        user_create,
        current_user.tenant_id,
        current_user.user_id,
        current_user.role,
        list(perms_check(current_user)),
        bool(getattr(current_user, "is_superuser", False)),
    )
    try:
        await notification_service.send_user_welcome_email(
            recipient_email=user.email,
            username=user.username,
            full_name=user.full_name,
            login_url=None,
        )
    except Exception as exc:
        logger.warning("User welcome email skipped: %s", exc)
    invalidate_grafana_proxy_auth_cache()
    return await rtp(auth_service.build_user_response, user, role_permission_strings(user.role))


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_update: UserUpdate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_USERS, Permission.MANAGE_USERS, Permission.MANAGE_TENANTS], "auth")
    ),
):
    perms = perms_check(current_user)
    is_admin = is_admin_check(current_user)
    can_manage = Permission.MANAGE_USERS.value in perms or Permission.UPDATE_USERS.value in perms
    update_fields = set(user_update.model_dump(exclude_unset=True).keys())

    if Permission.MANAGE_TENANTS.value in perms and not can_manage and not is_admin:
        if update_fields - {"is_active"}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "manage:tenants can only activate/deactivate non-admin users")

    if (update_fields & {"role", "org_id", "group_ids"}) and not is_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only administrators can modify role, tenant scope, or group memberships",
        )

    user = await rtp(auth_service.update_user, user_id, user_update, current_user.tenant_id, current_user.user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    if update_fields & {"role", "group_ids", "org_id", "is_active"}:
        invalidate_grafana_proxy_auth_cache()
    return await rtp(auth_service.build_user_response, user, role_permission_strings(user.role))


@router.put("/users/{user_id}/password")
@handle_route_errors()
async def update_user_password(
    user_id: str,
    password_update: UserPasswordUpdate,
    current_user: TokenData = Depends(require_authenticated_with_scope("auth")),
):
    if current_user.user_id != user_id:
        perms = perms_check(current_user)
        if not (
            Permission.MANAGE_USERS.value in perms
            or Permission.UPDATE_USERS.value in perms
            or getattr(current_user, "is_superuser", False)
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot update another user's password")
    if not await rtp(auth_service.update_password, user_id, password_update, current_user.tenant_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    return {"message": "Password updated successfully"}


@router.post("/users/{user_id}/password/reset-temp", response_model=TempPasswordResetResponse)
async def reset_user_password_temp(
    user_id: str,
    current_user: TokenData = Depends(require_authenticated_with_scope("auth")),
):
    if not (is_admin_check(current_user) or Permission.MANAGE_USERS.value in perms_check(current_user)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted to reset passwords")

    target = await rtp(auth_service.get_user_by_id_in_tenant, user_id, current_user.tenant_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    if target.role == Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin account passwords cannot be reset")

    result = await rtp(auth_service.reset_user_password_temp, current_user.user_id, user_id, current_user.tenant_id)
    temp_pw = result.get("temporary_password", "")
    email_sent = False
    if result.get("target_email"):
        try:
            email_sent = await notification_service.send_temporary_password_email(
                recipient_email=result["target_email"],
                username=result.get("target_username") or target.username,
                temporary_password=temp_pw,
                login_url=None,
            )
        except Exception as exc:
            logger.warning("Temporary password email skipped: %s", exc)
    return TempPasswordResetResponse(
        temporary_password=temp_pw,
        email_sent=bool(email_sent),
        message="Temporary password generated; user must change password on next login.",
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: TokenData = Depends(require_authenticated_with_scope("auth")),
):
    if not is_admin_check(current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only administrators can delete users")
    if current_user.user_id == user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete your own account")
    target = await rtp(auth_service.get_user_by_id_in_tenant, user_id, current_user.tenant_id)
    if target and target.role == Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin accounts cannot be deleted")
    if not await rtp(auth_service.delete_user, user_id, current_user.tenant_id, current_user.user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    invalidate_grafana_proxy_auth_cache()
    return {"message": "User deleted successfully"}


@router.put("/users/{user_id}/permissions")
async def update_user_permissions(
    user_id: str,
    permission_names: List[str],
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_USER_PERMISSIONS, Permission.MANAGE_USERS], "auth")
    ),
):
    if not await rtp(
        auth_service.update_user_permissions,
        user_id,
        permission_names,
        current_user.tenant_id,
        current_user.user_id,
        current_user.role,
        list(perms_check(current_user)),
        bool(getattr(current_user, "is_superuser", False)),
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    invalidate_grafana_proxy_auth_cache()
    return {"success": True, "permissions": permission_names}


@router.get("/permissions")
async def list_all_permissions(
    current_user: TokenData = Depends(
        require_any_permission_with_scope(
            [Permission.READ_USERS, Permission.READ_GROUPS, Permission.MANAGE_USERS, Permission.MANAGE_GROUPS],
            "auth",
        )
    ),
):
    all_permissions = await rtp(auth_service.list_all_permissions)
    if getattr(current_user, "is_superuser", False):
        return all_permissions

    allowed = set(perms_check(current_user))
    return [permission for permission in all_permissions if str(permission.get("name") or "") in allowed]


@router.get("/role-defaults")
async def list_role_defaults(
    current_user: TokenData = Depends(
        require_any_permission_with_scope(
            [Permission.READ_USERS, Permission.READ_GROUPS, Permission.MANAGE_USERS, Permission.MANAGE_GROUPS],
            "auth",
        )
    ),
):
    defaults = {role.value: [permission.value for permission in perms] for role, perms in ROLE_PERMISSIONS.items()}
    if getattr(current_user, "is_superuser", False):
        return defaults

    allowed = set(perms_check(current_user))
    return {role: [permission for permission in perms if permission in allowed] for role, perms in defaults.items()}
