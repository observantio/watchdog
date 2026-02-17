"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

Authentication and access management router.
"""


import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Query
from fastapi.concurrency import run_in_threadpool

from config import config
from models.access.user_models import (
    LoginRequest, RegisterRequest, UserResponse,
    UserCreate, UserUpdate, UserPasswordUpdate,
    TotpEnrollResponse, MfaVerifyRequest, MfaDisableRequest, RecoveryCodesResponse,
)
from models.access.group_models import (
    Group, GroupCreate, GroupUpdate, GroupMembersUpdate
)
from models.access.api_key_models import (
    ApiKey, ApiKeyCreate, ApiKeyUpdate
)
from models.access.auth_models import TokenData, Permission, Role, ROLE_PERMISSIONS, Token
from models.access.auth_models import OIDCAuthURLRequest, OIDCCodeExchangeRequest, OIDCAuthURLResponse
from models.access.auth_models import AuthModeResponse

from middleware.dependencies import (
    get_current_user,
    get_current_user_or_mfa_setup,
    require_permission,
    require_any_permission_with_scope,
    auth_service,
    enforce_public_endpoint_security,
    require_authenticated_with_scope,
    require_permission_with_scope,
)
from middleware.error_handlers import handle_route_errors
from services.notification_service import NotificationService
from database import get_db_session
from db_models import Tenant

logger = logging.getLogger(__name__)

USER_NOT_FOUND = "User not found"
GROUP_NOT_FOUND = "Group not found"

router = APIRouter(prefix="/api/auth", tags=["authentication"])
notification_service = NotificationService()


def _cookie_secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https"


def _set_auth_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        key="beobservant_token",
        value=token,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="lax",
        max_age=config.JWT_EXPIRATION_MINUTES * 60,
        path="/",
    )


def _clear_auth_cookie(request: Request, response: Response) -> None:
    response.set_cookie(
        key="beobservant_token",
        value="",
        httponly=True,
        secure=_cookie_secure(request),
        samesite="lax",
        max_age=0,
        expires=0,
        path="/",
    )


@router.get("/mode", response_model=AuthModeResponse)
async def auth_mode():
    oidc_enabled = await run_in_threadpool(auth_service.is_external_auth_enabled)
    password_enabled = await run_in_threadpool(auth_service.is_password_auth_enabled) if oidc_enabled else True
    return AuthModeResponse(
        provider=config.AUTH_PROVIDER,
        oidc_enabled=oidc_enabled,
        password_enabled=password_enabled,
        registration_enabled=not oidc_enabled,
        oidc_scopes=config.OIDC_SCOPES,
    )


@router.post("/login", response_model=Token)
async def login(request: Request, login_request: LoginRequest, response: Response):
    enforce_public_endpoint_security(
        request,
        scope="auth_login",
        limit=config.RATE_LIMIT_LOGIN_PER_MINUTE,
        window_seconds=60,
        allowlist=config.AUTH_PUBLIC_IP_ALLOWLIST,
    )
    token_or_challenge = await run_in_threadpool(
        auth_service.login,
        login_request.username,
        login_request.password,
        getattr(login_request, 'mfa_code', None),
    )

    if not token_or_challenge:
        if await run_in_threadpool(auth_service.is_external_auth_enabled) and not await run_in_threadpool(auth_service.is_password_auth_enabled):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Password login is disabled. Use OIDC login.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password or invalid MFA code",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # MFA challenge response
    if isinstance(token_or_challenge, dict):
        if token_or_challenge.get('mfa_required'):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA required")
        if token_or_challenge.get('mfa_setup_required'):
            # return setup token to the client so it can enroll/verify TOTP
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=token_or_challenge)

    _set_auth_cookie(request, response, token_or_challenge.access_token)
    return token_or_challenge


@router.post("/oidc/authorize-url", response_model=OIDCAuthURLResponse)
async def oidc_authorize_url(request: Request, payload: OIDCAuthURLRequest):
    enforce_public_endpoint_security(
        request,
        scope="auth_oidc_authorize",
        limit=config.RATE_LIMIT_LOGIN_PER_MINUTE,
        window_seconds=60,
        allowlist=config.AUTH_PUBLIC_IP_ALLOWLIST,
    )
    if not await run_in_threadpool(auth_service.is_external_auth_enabled):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OIDC is not enabled")
    try:
        url = await run_in_threadpool(
            auth_service.get_oidc_authorization_url,
            redirect_uri=payload.redirect_uri,
            state=payload.state,
            nonce=payload.nonce,
        )
        return OIDCAuthURLResponse(authorization_url=url)
    except Exception as exc:
        logger.error("Failed to build OIDC authorization URL: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to initialize OIDC login")


@router.post("/oidc/exchange", response_model=Token)
async def oidc_exchange_token(request: Request, payload: OIDCCodeExchangeRequest, response: Response):
    enforce_public_endpoint_security(
        request,
        scope="auth_oidc_exchange",
        limit=config.RATE_LIMIT_LOGIN_PER_MINUTE,
        window_seconds=60,
        allowlist=config.AUTH_PUBLIC_IP_ALLOWLIST,
    )
    if not await run_in_threadpool(auth_service.is_external_auth_enabled):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OIDC is not enabled")
    token_or_challenge = await run_in_threadpool(auth_service.exchange_oidc_authorization_code, payload.code, payload.redirect_uri)
    if not token_or_challenge:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC authentication failed")
    if isinstance(token_or_challenge, dict) and token_or_challenge.get('mfa_setup_required'):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=token_or_challenge)
    _set_auth_cookie(request, response, token_or_challenge.access_token)
    return token_or_challenge


@router.post("/logout")
async def logout(request: Request, response: Response):
    _clear_auth_cookie(request, response)
    return {"message": "Logged out"}


@router.post("/register", response_model=UserResponse)
@handle_route_errors()
async def register(request: Request, register_request: RegisterRequest):
    if await run_in_threadpool(auth_service.is_external_auth_enabled):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is managed by the external identity provider",
        )
    enforce_public_endpoint_security(
        request,
        scope="auth_register",
        limit=config.RATE_LIMIT_REGISTER_PER_HOUR,
        window_seconds=3600,
        allowlist=config.AUTH_PUBLIC_IP_ALLOWLIST,
    )
    user_create = UserCreate(
        username=register_request.username,
        email=register_request.email,
        password=register_request.password,
        full_name=register_request.full_name
    )

    with get_db_session() as db:
        default_tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = default_tenant.id if default_tenant else config.DEFAULT_ADMIN_TENANT

    user = await run_in_threadpool(auth_service.create_user, user_create, tenant_id)

    try:
        await notification_service.send_user_welcome_email(
            recipient_email=user.email,
            username=user.username,
            full_name=user.full_name,
            login_url=None,
        )
    except Exception as exc:
        logger.warning("User welcome email skipped: %s", exc)

    return await run_in_threadpool(auth_service.build_user_response, user, ROLE_PERMISSIONS.get(user.role, []))


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: TokenData = Depends(require_authenticated_with_scope("auth"))):
    user = await run_in_threadpool(auth_service.get_user_by_id, current_user.user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=USER_NOT_FOUND
        )
    
    return await run_in_threadpool(auth_service.build_user_response, user, current_user.permissions)


@router.post('/mfa/enroll', response_model=TotpEnrollResponse)
async def mfa_enroll(current_user: TokenData = Depends(get_current_user_or_mfa_setup)):
    """Generate a TOTP secret for the current user (persist encrypted secret, not enabled until verify)."""
    try:
        payload = await run_in_threadpool(auth_service.enroll_totp, current_user.user_id)
        return TotpEnrollResponse(**payload)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post('/mfa/verify', response_model=RecoveryCodesResponse)
async def mfa_verify(payload: MfaVerifyRequest, current_user: TokenData = Depends(get_current_user_or_mfa_setup)):
    """Verify TOTP code and enable MFA for the current user; return recovery codes."""
    try:
        codes = await run_in_threadpool(auth_service.verify_enable_totp, current_user.user_id, payload.code)
        return RecoveryCodesResponse(recovery_codes=codes)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post('/mfa/disable')
async def mfa_disable(payload: MfaDisableRequest, current_user: TokenData = Depends(require_authenticated_with_scope("auth"))):
    """Disable MFA after verifying password or TOTP code."""
    ok = await run_in_threadpool(auth_service.disable_totp, current_user.user_id, current_password=payload.current_password, code=payload.code)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to disable MFA")
    return {"message": "MFA disabled"}


@router.post('/users/{user_id}/mfa/reset')
async def admin_reset_user_mfa(user_id: str, current_user: TokenData = Depends(require_any_permission_with_scope([Permission.MANAGE_USERS], "auth"))):
    ok = await run_in_threadpool(auth_service.reset_totp, user_id, current_user.user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)
    return {"message": "User MFA reset"}


@router.put("/me", response_model=UserResponse)
async def update_current_user_info(
    user_update: UserUpdate,
    current_user: TokenData = Depends(require_authenticated_with_scope("auth"))
):
    update_data = user_update.model_dump(exclude_unset=True)
    for field in ("role", "group_ids", "is_active"):
        update_data.pop(field, None)
    user_update = UserUpdate(**update_data)
    updated_user = await run_in_threadpool(
        auth_service.update_user,
        current_user.user_id,
        user_update,
        current_user.tenant_id,
        current_user.user_id,
    )

    if not updated_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)

    return await run_in_threadpool(auth_service.build_user_response, updated_user, current_user.permissions)


@router.get("/api-keys", response_model=List[ApiKey])
async def list_api_keys(current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_API_KEYS, "auth"))):
    return await run_in_threadpool(auth_service.list_api_keys, current_user.user_id)


@router.post("/api-keys", response_model=ApiKey)
@handle_route_errors()
async def create_api_key(
    key_create: ApiKeyCreate,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.CREATE_API_KEYS, "auth"))
):
    return await run_in_threadpool(auth_service.create_api_key, current_user.user_id, current_user.tenant_id, key_create)


@router.patch("/api-keys/{key_id}", response_model=ApiKey)
@handle_route_errors()
async def update_api_key(
    key_id: str,
    key_update: ApiKeyUpdate,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_API_KEYS, "auth"))
):
    return await run_in_threadpool(auth_service.update_api_key, current_user.user_id, key_id, key_update)


@router.delete("/api-keys/{key_id}")
@handle_route_errors()
async def delete_api_key(
    key_id: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.DELETE_API_KEYS, "auth"))
):
    success = await run_in_threadpool(auth_service.delete_api_key, current_user.user_id, key_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return {"message": "API key deleted"}


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.READ_USERS, Permission.MANAGE_USERS], "auth")
    )
):
    users = await run_in_threadpool(auth_service.list_users, current_user.tenant_id, limit=limit, offset=offset)
    return [await run_in_threadpool(auth_service.build_user_response, user, ROLE_PERMISSIONS.get(user.role, [])) for user in users]


@router.post("/users", response_model=UserResponse)
@handle_route_errors()
async def create_user(
    user_create: UserCreate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.CREATE_USERS, Permission.MANAGE_USERS], "auth")
    )
):
    user = await run_in_threadpool(auth_service.create_user, user_create, current_user.tenant_id)
    try:
        await notification_service.send_user_welcome_email(
            recipient_email=user.email,
            username=user.username,
            full_name=user.full_name,
            login_url=None,
        )
    except Exception as exc:
        logger.warning("User welcome email skipped: %s", exc)

    return await run_in_threadpool(auth_service.build_user_response, user, ROLE_PERMISSIONS.get(user.role, []))


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_update: UserUpdate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_USERS, Permission.MANAGE_USERS], "auth")
    )
):
    user = await run_in_threadpool(auth_service.update_user, user_id, user_update, current_user.tenant_id, current_user.user_id)
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)
    
    return await run_in_threadpool(auth_service.build_user_response, user, ROLE_PERMISSIONS.get(user.role, []))


@router.put("/users/{user_id}/password")
@handle_route_errors()
async def update_user_password(
    user_id: str,
    password_update: UserPasswordUpdate,
    current_user: TokenData = Depends(require_authenticated_with_scope("auth"))
):
    if current_user.user_id != user_id:
        user_obj = await run_in_threadpool(auth_service.get_user_by_id, current_user.user_id)
        user_perms = await run_in_threadpool(auth_service.get_user_permissions, user_obj) if user_obj else (getattr(current_user, "permissions", []) or [])
        if (
            Permission.MANAGE_USERS.value not in user_perms
            and Permission.UPDATE_USERS.value not in user_perms
            and not getattr(current_user, "is_superuser", False)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot update another user's password"
            )

    success = await run_in_threadpool(auth_service.update_password, user_id, password_update, current_user.tenant_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    return {"message": "Password updated successfully"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.DELETE_USERS, Permission.MANAGE_USERS], "auth")
    )
):
    if current_user.user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )

    target_user = await run_in_threadpool(auth_service.get_user_by_id, user_id)
    if target_user and target_user.role == Role.ADMIN and current_user.role != Role.ADMIN and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can delete admin accounts"
        )
    success = await run_in_threadpool(auth_service.delete_user, user_id, current_user.tenant_id, current_user.user_id)

    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)

    return {"message": "User deleted successfully"}


@router.get("/groups", response_model=List[Group])
async def list_groups(current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_GROUPS, "auth"))):
    return await run_in_threadpool(auth_service.list_groups, current_user.tenant_id)


@router.post("/groups", response_model=Group)
async def create_group(
    group_create: GroupCreate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.CREATE_GROUPS, Permission.MANAGE_GROUPS], "auth")
    )
):
    return await run_in_threadpool(auth_service.create_group, group_create, current_user.tenant_id)


@router.get("/groups/{group_id}", response_model=Group)
async def get_group(
    group_id: str,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.READ_GROUPS, Permission.MANAGE_GROUPS], "auth")
    )
):
    group = await run_in_threadpool(auth_service.get_group, group_id, current_user.tenant_id)
    
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GROUP_NOT_FOUND)
    
    return group


@router.put("/groups/{group_id}", response_model=Group)
async def update_group(
    group_id: str,
    group_update: GroupUpdate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_GROUPS, Permission.MANAGE_GROUPS], "auth")
    )
):
    group = await run_in_threadpool(auth_service.update_group, group_id, group_update, current_user.tenant_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GROUP_NOT_FOUND)
    return group


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: str,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.DELETE_GROUPS, Permission.MANAGE_GROUPS], "auth")
    )
):
    success = await run_in_threadpool(auth_service.delete_group, group_id, current_user.tenant_id)
    
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GROUP_NOT_FOUND)
    
    return {"message": "Group deleted successfully"}


@router.put("/users/{user_id}/permissions")
async def update_user_permissions(
    user_id: str,
    permission_names: List[str],
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_USER_PERMISSIONS, Permission.MANAGE_USERS], "auth")
    )
):
    """Update user's direct permissions."""
    success = await run_in_threadpool(auth_service.update_user_permissions, user_id, permission_names, current_user.tenant_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)
    return {"success": True, "permissions": permission_names}


@router.put("/groups/{group_id}/permissions")
async def update_group_permissions(
    group_id: str,
    permission_names: List[str],
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_GROUP_PERMISSIONS, Permission.MANAGE_GROUPS], "auth")
    )
):
    """Update group's permissions."""
    success = await run_in_threadpool(auth_service.update_group_permissions, group_id, permission_names, current_user.tenant_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GROUP_NOT_FOUND)
    return {"success": True, "permissions": permission_names}


@router.put("/groups/{group_id}/members")
async def update_group_members(
    group_id: str,
    members: GroupMembersUpdate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_GROUP_MEMBERS, Permission.MANAGE_GROUPS], "auth")
    )
):
    """Update group membership."""
    success = await run_in_threadpool(auth_service.update_group_members, group_id, members.user_ids, current_user.tenant_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GROUP_NOT_FOUND)
    return {"success": True, "user_ids": members.user_ids}


@router.get("/permissions")
async def list_all_permissions(
    current_user: TokenData = Depends(
        require_any_permission_with_scope(
            [Permission.READ_USERS, Permission.READ_GROUPS, Permission.MANAGE_USERS, Permission.MANAGE_GROUPS],
            "auth",
        )
    )
):
    """List all available permissions."""
    return await run_in_threadpool(auth_service.list_all_permissions)


@router.get("/role-defaults")
async def list_role_defaults(
    current_user: TokenData = Depends(
        require_any_permission_with_scope(
            [Permission.READ_USERS, Permission.READ_GROUPS, Permission.MANAGE_USERS, Permission.MANAGE_GROUPS],
            "auth",
        )
    )
):
    """List role default permissions."""
    return {
        role.value: [perm.value for perm in perms]
        for role, perms in ROLE_PERMISSIONS.items()
    }
