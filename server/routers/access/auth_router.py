"""
Router for authentication, user management, API keys, and audit logs.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import csv
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import aliased

from config import config
from database import get_db_session
from db_models import AuditLog, Tenant, User
from middleware.dependencies import (
    auth_service,
    get_current_user_or_mfa_setup,
    require_any_permission_with_scope,
    require_authenticated_with_scope,
    require_permission_with_scope,
)
from middleware.error_handlers import handle_route_errors
from models.access.api_key_models import (
    ApiKey, ApiKeyCreate, ApiKeyShareUpdateRequest, ApiKeyShareUser, ApiKeyUpdate,
)
from models.access.auth_models import (
    AuthModeResponse, OIDCAuthURLRequest, OIDCAuthURLResponse, OIDCCodeExchangeRequest,
    Permission, Role, ROLE_PERMISSIONS, Token, TokenData,
)
from models.access.group_models import Group, GroupCreate, GroupMembersUpdate, GroupUpdate
from models.access.user_models import (
    LoginRequest, MfaDisableRequest, MfaVerifyRequest, RecoveryCodesResponse,
    RegisterRequest, TempPasswordResetResponse, TotpEnrollResponse,
    UserCreate, UserPasswordUpdate, UserResponse, UserUpdate,
)
from services.audit_context import get_request_audit_context
from services.auth.helper import (
    build_audit_log_query, clear_auth_cookie, invalidate_grafana_proxy_auth_cache,
    require_admin_with_audit_permission, role_permission_strings, sanitize_audit_details,
    sanitize_resource_id, set_auth_cookie, perms_check, is_admin_check, apply_audit_filters_func, rate_limit_func,
)
from services.notification_service import NotificationService

logger = logging.getLogger(__name__)

USER_NOT_FOUND = "User not found"
GROUP_NOT_FOUND = "Group not found"

router = APIRouter(prefix="/api/auth", tags=["authentication"])
notification_service = NotificationService()

rtp = run_in_threadpool



@router.get("/mode", response_model=AuthModeResponse)
async def auth_mode():
    oidc_enabled = await rtp(auth_service.is_external_auth_enabled)
    password_enabled = await rtp(auth_service.is_password_auth_enabled) if oidc_enabled else True
    return AuthModeResponse(
        provider=config.AUTH_PROVIDER,
        oidc_enabled=oidc_enabled,
        password_enabled=password_enabled,
        registration_enabled=not oidc_enabled,
        oidc_scopes=config.OIDC_SCOPES,
    )


@router.post("/login", response_model=Token)
async def login(request: Request, login_request: LoginRequest, response: Response):
    rate_limit_func(request, "auth_login", config.RATE_LIMIT_LOGIN_PER_MINUTE, 60)
    token_or_challenge = await rtp(
        auth_service.login,
        login_request.username,
        login_request.password,
        getattr(login_request, "mfa_code", None),
    )
    if not token_or_challenge:
        if await rtp(auth_service.is_external_auth_enabled) and not await rtp(auth_service.is_password_auth_enabled):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Password login is disabled. Use OIDC login.")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password or invalid MFA code",
                            headers={"WWW-Authenticate": "Bearer"})
    if isinstance(token_or_challenge, dict):
        if token_or_challenge.get("mfa_required"):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MFA required")
        if token_or_challenge.get("mfa_setup_required"):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=token_or_challenge)
    set_auth_cookie(request, response, token_or_challenge.access_token)
    return token_or_challenge


@router.post("/oidc/authorize-url", response_model=OIDCAuthURLResponse)
async def oidc_authorize_url(request: Request, payload: OIDCAuthURLRequest):
    rate_limit_func(request, "auth_oidc_authorize", config.RATE_LIMIT_LOGIN_PER_MINUTE, 60)
    if not await rtp(auth_service.is_external_auth_enabled):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OIDC is not enabled")
    try:
        session = await rtp(
            auth_service.get_oidc_authorization_url,
            payload.redirect_uri, payload.state, payload.nonce,
            payload.code_challenge, payload.code_challenge_method,
        )
        return OIDCAuthURLResponse(**session)
    except Exception as exc:
        logger.error("Failed to build OIDC authorization URL: %s", exc)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to initialize OIDC login")


@router.post("/oidc/exchange", response_model=Token)
async def oidc_exchange_token(request: Request, payload: OIDCCodeExchangeRequest, response: Response):
    rate_limit_func(request, "auth_oidc_exchange", config.RATE_LIMIT_LOGIN_PER_MINUTE, 60)
    if not await rtp(auth_service.is_external_auth_enabled):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OIDC is not enabled")
    try:
        token_or_challenge = await rtp(
            auth_service.exchange_oidc_authorization_code,
            payload.code, payload.redirect_uri, payload.transaction_id,
            payload.state, payload.code_verifier,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc) or "OIDC authentication failed")
    except Exception:
        logger.exception("OIDC exchange failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "OIDC authentication failed")
    if not token_or_challenge:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "OIDC authentication failed")
    if isinstance(token_or_challenge, dict) and token_or_challenge.get("mfa_setup_required"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=token_or_challenge)
    set_auth_cookie(request, response, token_or_challenge.access_token)
    return token_or_challenge


@router.post("/logout")
async def logout(request: Request, response: Response):
    clear_auth_cookie(request, response)
    return {"message": "Logged out"}


@router.post("/register", response_model=UserResponse)
@handle_route_errors()
async def register(request: Request, register_request: RegisterRequest):
    if await rtp(auth_service.is_external_auth_enabled):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is managed by the external identity provider")
    rate_limit_func(request, "auth_register", config.RATE_LIMIT_REGISTER_PER_HOUR, 3600)

    def _default_tenant_id() -> str:
        with get_db_session() as db:
            t = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
            return t.id if t else config.DEFAULT_ADMIN_TENANT

    tenant_id = await rtp(_default_tenant_id)
    user = await rtp(auth_service.create_user, UserCreate(
        username=register_request.username,
        email=register_request.email,
        password=register_request.password,
        full_name=register_request.full_name,
    ), tenant_id)
    try:
        await notification_service.send_user_welcome_email(
            recipient_email=user.email, username=user.username,
            full_name=user.full_name, login_url=None,
        )
    except Exception as exc:
        logger.warning("User welcome email skipped: %s", exc)
    return await rtp(auth_service.build_user_response, user, role_permission_strings(user.role))


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: TokenData = Depends(require_authenticated_with_scope("auth"))):
    user = await rtp(auth_service.get_user_by_id, current_user.user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    return await rtp(auth_service.build_user_response, user, current_user.permissions)


@router.put("/me", response_model=UserResponse)
async def update_current_user_info(
    user_update: UserUpdate,
    current_user: TokenData = Depends(require_authenticated_with_scope("auth")),
):
    data = user_update.model_dump(exclude_unset=True)
    for f in ("role", "group_ids", "is_active"):
        data.pop(f, None)
    updated = await rtp(auth_service.update_user, current_user.user_id, UserUpdate(**data),
                        current_user.tenant_id, current_user.user_id)
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    return await rtp(auth_service.build_user_response, updated, current_user.permissions)


@router.post("/mfa/enroll", response_model=TotpEnrollResponse)
async def mfa_enroll(current_user: TokenData = Depends(get_current_user_or_mfa_setup)):
    try:
        return TotpEnrollResponse(**(await rtp(auth_service.enroll_totp, current_user.user_id)))
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unable to enroll MFA")


@router.post("/mfa/verify", response_model=RecoveryCodesResponse)
async def mfa_verify(payload: MfaVerifyRequest, current_user: TokenData = Depends(get_current_user_or_mfa_setup)):
    try:
        codes = await rtp(auth_service.verify_enable_totp, current_user.user_id, payload.code)
        return RecoveryCodesResponse(recovery_codes=codes)
    except ValueError as ve:
        msg = str(ve)
        detail = ("TOTP not enrolled for user" if "not enrolled" in msg
                  else "Invalid TOTP code" if "Invalid TOTP code" in msg else msg)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unable to verify MFA code")


@router.post("/mfa/disable")
async def mfa_disable(payload: MfaDisableRequest, current_user: TokenData = Depends(require_authenticated_with_scope("auth"))):
    if not await rtp(auth_service.disable_totp, current_user.user_id,
                     current_password=payload.current_password, code=payload.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unable to disable MFA")
    return {"message": "MFA disabled"}


@router.post("/users/{user_id}/mfa/reset")
async def admin_reset_user_mfa(
    user_id: str,
    current_user: TokenData = Depends(require_any_permission_with_scope([Permission.MANAGE_USERS], "auth")),
):
    if not await rtp(auth_service.reset_totp, user_id, current_user.user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    return {"message": "User MFA reset"}


@router.get("/api-keys", response_model=List[ApiKey])
async def list_api_keys(current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_API_KEYS, "auth"))):
    return await rtp(auth_service.list_api_keys, current_user.user_id)


@router.post("/api-keys", response_model=ApiKey)
@handle_route_errors()
async def create_api_key(
    key_create: ApiKeyCreate,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.CREATE_API_KEYS, "auth")),
):
    return await rtp(auth_service.create_api_key, current_user.user_id, current_user.tenant_id, key_create)


@router.patch("/api-keys/{key_id}", response_model=ApiKey)
@handle_route_errors()
async def update_api_key(
    key_id: str,
    key_update: ApiKeyUpdate,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_API_KEYS, "auth")),
):
    return await rtp(auth_service.update_api_key, current_user.user_id, key_id, key_update)


@router.post("/api-keys/{key_id}/otlp-token/regenerate", response_model=ApiKey)
@handle_route_errors()
async def regenerate_api_key_otlp_token(
    key_id: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_API_KEYS, "auth")),
):
    return await rtp(auth_service.regenerate_api_key_otlp_token, current_user.user_id, key_id)


@router.delete("/api-keys/{key_id}")
@handle_route_errors()
async def delete_api_key(
    key_id: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.DELETE_API_KEYS, "auth")),
):
    if not await rtp(auth_service.delete_api_key, current_user.user_id, key_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")
    return {"message": "API key deleted"}


@router.get("/api-keys/{key_id}/shares", response_model=List[ApiKeyShareUser])
@handle_route_errors()
async def get_api_key_shares(
    key_id: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_API_KEYS, "auth")),
):
    return await rtp(auth_service.list_api_key_shares, current_user.user_id, current_user.tenant_id, key_id)


@router.put("/api-keys/{key_id}/shares", response_model=List[ApiKeyShareUser])
@handle_route_errors()
async def put_api_key_shares(
    key_id: str,
    payload: ApiKeyShareUpdateRequest,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_API_KEYS, "auth")),
):
    return await rtp(
        auth_service.replace_api_key_shares,
        current_user.user_id, current_user.tenant_id, key_id,
        payload.user_ids, payload.group_ids,
    )


@router.delete("/api-keys/{key_id}/shares/{shared_user_id}")
@handle_route_errors()
async def remove_api_key_share(
    key_id: str,
    shared_user_id: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_API_KEYS, "auth")),
):
    if not await rtp(auth_service.delete_api_key_share,
                     current_user.user_id, current_user.tenant_id, key_id, shared_user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share not found")
    return {"message": "API key share removed"}


@router.get("/audit-logs")
async def list_audit_logs(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    user_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(require_admin_with_audit_permission),
):
    actor = aliased(User)

    def _query():
        with get_db_session() as db:
            q_obj = apply_audit_filters_func(
                build_audit_log_query(db, current_user, tenant_id, actor),
                start, end, user_id, action, resource_type, q,
            )
            rows = q_obj.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
            items = [
                {
                    "id": log.id, "tenant_id": log.tenant_id, "user_id": log.user_id,
                    "username": username, "email": email, "action": log.action,
                    "resource_type": log.resource_type,
                    "resource_id": sanitize_resource_id(log.resource_id),
                    "details": sanitize_audit_details(log.details),
                    "ip_address": log.ip_address, "user_agent": log.user_agent,
                    "created_at": log.created_at,
                }
                for log, username, email in rows
            ]
            ip_address, user_agent = get_request_audit_context()
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=5)
            already_logged = (
                db.query(AuditLog.id)
                .filter(
                    AuditLog.tenant_id == current_user.tenant_id,
                    AuditLog.user_id == current_user.user_id,
                    AuditLog.action == "audit_logs.view",
                    AuditLog.resource_type == "audit_logs",
                    AuditLog.resource_id == "list",
                    AuditLog.created_at >= cutoff,
                )
                .first()
            )
            if not already_logged:
                db.add(AuditLog(
                    tenant_id=current_user.tenant_id, user_id=current_user.user_id,
                    action="audit_logs.view", resource_type="audit_logs", resource_id="list",
                    details={"limit": limit, "offset": offset},
                    ip_address=ip_address, user_agent=user_agent,
                ))
            return items

    return await rtp(_query)


@router.get("/audit-logs/export")
async def export_audit_logs_csv(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    user_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    current_user: TokenData = Depends(require_admin_with_audit_permission),
):
    actor = aliased(User)

    def _export():
        with get_db_session() as db:
            q_obj = apply_audit_filters_func(
                build_audit_log_query(db, current_user, tenant_id, actor),
                start, end, user_id, action, resource_type,
            )
            rows = q_obj.order_by(AuditLog.created_at.desc()).all()
            ip_address, user_agent = get_request_audit_context()
            db.add(AuditLog(
                tenant_id=current_user.tenant_id, user_id=current_user.user_id,
                action="audit_logs.export", resource_type="audit_logs", resource_id="csv",
                details={"count": len(rows)},
                ip_address=ip_address, user_agent=user_agent,
            ))
            return rows

    rows = await rtp(_export)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "created_at", "tenant_id", "user_id", "username", "email",
                     "action", "resource_type", "resource_id", "ip_address", "user_agent", "details"])
    for log, username, email in rows:
        writer.writerow([
            log.id, log.created_at.isoformat() if log.created_at else "",
            log.tenant_id or "", log.user_id or "", username or "", email or "",
            log.action, log.resource_type, sanitize_resource_id(log.resource_id) or "",
            log.ip_address or "", log.user_agent or "",
            json.dumps(sanitize_audit_details(log.details)),
        ])
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-logs.csv"},
    )


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.READ_USERS, Permission.MANAGE_USERS, Permission.MANAGE_TENANTS], "auth")
    ),
):
    users = await rtp(auth_service.list_users, current_user.tenant_id, limit=limit, offset=offset)
    return [await rtp(auth_service.build_user_response, u, role_permission_strings(u.role)) for u in users]


@router.post("/users", response_model=UserResponse)
@handle_route_errors()
async def create_user(
    user_create: UserCreate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.CREATE_USERS, Permission.MANAGE_USERS], "auth")
    ),
):
    user = await rtp(
        auth_service.create_user, user_create,
        current_user.tenant_id, current_user.user_id,
        current_user.role, bool(getattr(current_user, "is_superuser", False)),
    )
    try:
        await notification_service.send_user_welcome_email(
            recipient_email=user.email, username=user.username,
            full_name=user.full_name, login_url=None,
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
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only administrators can modify role, tenant scope, or group memberships")

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
        if not (Permission.MANAGE_USERS.value in perms or Permission.UPDATE_USERS.value in perms
                or getattr(current_user, "is_superuser", False)):
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


@router.get("/groups", response_model=List[Group])
async def list_groups(current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_GROUPS, "auth"))):
    return await rtp(auth_service.list_groups, current_user.tenant_id)


@router.post("/groups", response_model=Group)
async def create_group(
    group_create: GroupCreate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.CREATE_GROUPS, Permission.MANAGE_GROUPS], "auth")
    ),
):
    group = await rtp(auth_service.create_group, group_create, current_user.tenant_id, current_user.user_id)
    invalidate_grafana_proxy_auth_cache()
    return group


@router.get("/groups/{group_id}", response_model=Group)
async def get_group(
    group_id: str,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.READ_GROUPS, Permission.MANAGE_GROUPS], "auth")
    ),
):
    group = await rtp(auth_service.get_group, group_id, current_user.tenant_id)
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GROUP_NOT_FOUND)
    return group


@router.put("/groups/{group_id}", response_model=Group)
async def update_group(
    group_id: str,
    group_update: GroupUpdate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_GROUPS, Permission.MANAGE_GROUPS], "auth")
    ),
):
    group = await rtp(auth_service.update_group, group_id, group_update, current_user.tenant_id, current_user.user_id)
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
):
    if not await rtp(auth_service.delete_group, group_id, current_user.tenant_id, current_user.user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, GROUP_NOT_FOUND)
    invalidate_grafana_proxy_auth_cache()
    return {"message": "Group deleted successfully"}


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
        user_id, permission_names, current_user.tenant_id, current_user.user_id,
        current_user.role, list(perms_check(current_user)), bool(getattr(current_user, "is_superuser", False)),
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    invalidate_grafana_proxy_auth_cache()
    return {"success": True, "permissions": permission_names}


@router.put("/groups/{group_id}/permissions")
async def update_group_permissions(
    group_id: str,
    permission_names: List[str],
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_GROUP_PERMISSIONS, Permission.MANAGE_GROUPS], "auth")
    ),
):
    if not await rtp(
        auth_service.update_group_permissions,
        group_id, permission_names, current_user.tenant_id, current_user.user_id,
        current_user.role, list(perms_check(current_user)), bool(getattr(current_user, "is_superuser", False)),
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
):
    if not await rtp(
        auth_service.update_group_members,
        group_id, members.user_ids, current_user.tenant_id, current_user.user_id,
        current_user.role, list(perms_check(current_user)), bool(getattr(current_user, "is_superuser", False)),
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, GROUP_NOT_FOUND)
    invalidate_grafana_proxy_auth_cache()
    return {"success": True, "user_ids": members.user_ids}


@router.get("/permissions")
async def list_all_permissions(
    current_user: TokenData = Depends(
        require_any_permission_with_scope(
            [Permission.READ_USERS, Permission.READ_GROUPS, Permission.MANAGE_USERS, Permission.MANAGE_GROUPS], "auth"
        )
    ),
):
    return await rtp(auth_service.list_all_permissions)


@router.get("/role-defaults")
async def list_role_defaults(
    current_user: TokenData = Depends(
        require_any_permission_with_scope(
            [Permission.READ_USERS, Permission.READ_GROUPS, Permission.MANAGE_USERS, Permission.MANAGE_GROUPS], "auth"
        )
    ),
):
    return {role.value: [p.value for p in perms] for role, perms in ROLE_PERMISSIONS.items()}