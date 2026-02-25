"""
Router for authentication, user management, API keys, and audit logs.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""



import logging
from typing import List, Optional
from datetime import datetime, timedelta, timezone
import csv
import io
import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import aliased
from sqlalchemy import String

from config import config
from models.access.user_models import (
    LoginRequest, RegisterRequest, UserResponse,
    UserCreate, UserUpdate, UserPasswordUpdate,
    TotpEnrollResponse, MfaVerifyRequest, MfaDisableRequest, RecoveryCodesResponse,
    TempPasswordResetResponse,
)
from models.access.group_models import (
    Group, GroupCreate, GroupUpdate, GroupMembersUpdate
)
from models.access.api_key_models import (
    ApiKey, ApiKeyCreate, ApiKeyUpdate, ApiKeyShareUpdateRequest, ApiKeyShareUser
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
from db_models import Tenant, AuditLog, User
from services.audit_context import get_request_audit_context
from services.common.cookies import is_secure_cookie_request

logger = logging.getLogger(__name__)

USER_NOT_FOUND = "User not found"
GROUP_NOT_FOUND = "Group not found"

router = APIRouter(prefix="/api/auth", tags=["authentication"])
notification_service = NotificationService()


def _invalidate_grafana_proxy_auth_cache() -> None:
    try:
        from services.grafana.proxy_auth_ops import clear_proxy_auth_cache

        clear_proxy_auth_cache()
    except Exception as exc:
        logger.warning("Failed to invalidate Grafana proxy auth cache: %s", exc)


def _require_admin_with_audit_permission(current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_AUDIT_LOGS, "auth"))):
    if str(getattr(current_user, "role", "")).lower() != Role.ADMIN.value and not getattr(current_user, "is_superuser", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required to view audit logs")
    return current_user


def _cookie_secure(request: Request) -> bool:
    return is_secure_cookie_request(
        request,
        trust_proxy_headers=bool(config.TRUST_PROXY_HEADERS),
        trusted_proxy_cidrs=getattr(config, "TRUSTED_PROXY_CIDRS", []) or [],
    )


def _set_auth_cookie(request: Request, response: Response, token: str) -> None:
    secure_flag = bool(config.FORCE_SECURE_COOKIES) or _cookie_secure(request)
    response.set_cookie(
        key="beobservant_token",
        value=token,
        httponly=True,
        secure=secure_flag,
        samesite="lax",
        max_age=config.JWT_EXPIRATION_MINUTES * 60,
        path="/",
    )


_AUDIT_SENSITIVE_KEYS = (
    "token",
    "secret",
    "password",
    "passcode",
    "authorization",
    "bearer",
    "jwt",
    "mfa_code",
    "setup_token",
    "auth_code",
    "oauth_code",
    # generic code parameter should also be treated as sensitive
    "code",
)


def _audit_key_is_sensitive(key: str) -> bool:
    lowered = str(key or "").strip().lower()
    if lowered == "status_code":
        return False
    return any(marker in lowered for marker in _AUDIT_SENSITIVE_KEYS)


def _redact_query_string(raw: str) -> str:
    if not raw:
        return ""
    pairs = parse_qsl(raw, keep_blank_values=True)
    sanitized = []
    for key, value in pairs:
        sanitized.append((key, "[REDACTED]" if _audit_key_is_sensitive(key) else value))
    return urlencode(sanitized, doseq=True)


def _sanitize_resource_id(resource_id: Optional[str]) -> str:
    text = str(resource_id or "")
    if not text or "?" not in text:
        return text
    parsed = urlsplit(text)
    if not parsed.query:
        return text
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, _redact_query_string(parsed.query), parsed.fragment))


def _sanitize_audit_details(details: Optional[dict]) -> dict:
    source = details if isinstance(details, dict) else {}
    sanitized = {}
    for key, value in source.items():
        if _audit_key_is_sensitive(key):
            sanitized[key] = "[REDACTED]"
            continue
        if key == "query" and isinstance(value, str):
            sanitized[key] = _redact_query_string(value)
            continue
        sanitized[key] = value
    return sanitized


def _clear_auth_cookie(request: Request, response: Response) -> None:
    secure_flag = bool(config.FORCE_SECURE_COOKIES) or _cookie_secure(request)
    response.set_cookie(
        key="beobservant_token",
        value="",
        httponly=True,
        secure=secure_flag,
        samesite="lax",
        max_age=0,
        expires=0,
        path="/",
    )


def _build_audit_log_query(db, current_user: TokenData, tenant_id: Optional[str], actor):
    query = (
        db.query(AuditLog, actor.username, actor.email)
        .outerjoin(actor, actor.id == AuditLog.user_id)
    )
    scoped_tenant = tenant_id if (getattr(current_user, "is_superuser", False) and tenant_id) else current_user.tenant_id
    if not getattr(current_user, "is_superuser", False):
        query = query.filter(AuditLog.tenant_id == current_user.tenant_id)
    elif scoped_tenant:
        query = query.filter(AuditLog.tenant_id == scoped_tenant)
    return query


def _role_permission_strings(role) -> List[str]:
    return [p.value for p in ROLE_PERMISSIONS.get(role, [])]


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

    if isinstance(token_or_challenge, dict):
        if token_or_challenge.get('mfa_required'):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA required")
        if token_or_challenge.get('mfa_setup_required'):
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
        oidc_session = await run_in_threadpool(
            auth_service.get_oidc_authorization_url,
            payload.redirect_uri,
            payload.state,
            payload.nonce,
            payload.code_challenge,
            payload.code_challenge_method,
        )
        return OIDCAuthURLResponse(**oidc_session)
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
    token_or_challenge = await run_in_threadpool(
        auth_service.exchange_oidc_authorization_code,
        payload.code,
        payload.redirect_uri,
        payload.transaction_id,
        payload.state,
        payload.code_verifier,
    )
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

    def _resolve_default_tenant_id() -> str:
        with get_db_session() as db:
            default_tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
            return default_tenant.id if default_tenant else config.DEFAULT_ADMIN_TENANT

    tenant_id = await run_in_threadpool(_resolve_default_tenant_id)
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

    return await run_in_threadpool(auth_service.build_user_response, user, _role_permission_strings(user.role))


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: TokenData = Depends(require_authenticated_with_scope("auth"))):
    user = await run_in_threadpool(auth_service.get_user_by_id, current_user.user_id)

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)

    return await run_in_threadpool(auth_service.build_user_response, user, current_user.permissions)


@router.post('/mfa/enroll', response_model=TotpEnrollResponse)
async def mfa_enroll(current_user: TokenData = Depends(get_current_user_or_mfa_setup)):
    try:
        payload = await run_in_threadpool(auth_service.enroll_totp, current_user.user_id)
        return TotpEnrollResponse(**payload)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to enroll MFA")


@router.post('/mfa/verify', response_model=RecoveryCodesResponse)
async def mfa_verify(payload: MfaVerifyRequest, current_user: TokenData = Depends(get_current_user_or_mfa_setup)):
    try:
        codes = await run_in_threadpool(auth_service.verify_enable_totp, current_user.user_id, payload.code)
        return RecoveryCodesResponse(recovery_codes=codes)
    except ValueError as ve:
        msg = str(ve)
        if "not enrolled" in msg:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="TOTP not enrolled for user")
        if "Invalid TOTP code" in msg:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid TOTP code")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to verify MFA code")


@router.post('/mfa/disable')
async def mfa_disable(payload: MfaDisableRequest, current_user: TokenData = Depends(require_authenticated_with_scope("auth"))):
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


@router.post("/api-keys/{key_id}/otlp-token/regenerate", response_model=ApiKey)
@handle_route_errors()
async def regenerate_api_key_otlp_token(
    key_id: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_API_KEYS, "auth"))
):
    return await run_in_threadpool(auth_service.regenerate_api_key_otlp_token, current_user.user_id, key_id)


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


@router.get("/api-keys/{key_id}/shares", response_model=List[ApiKeyShareUser])
@handle_route_errors()
async def get_api_key_shares(
    key_id: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_API_KEYS, "auth"))
):
    return await run_in_threadpool(auth_service.list_api_key_shares, current_user.user_id, current_user.tenant_id, key_id)


@router.put("/api-keys/{key_id}/shares", response_model=List[ApiKeyShareUser])
@handle_route_errors()
async def put_api_key_shares(
    key_id: str,
    payload: ApiKeyShareUpdateRequest,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_API_KEYS, "auth"))
):
    return await run_in_threadpool(
        auth_service.replace_api_key_shares,
        current_user.user_id,
        current_user.tenant_id,
        key_id,
        payload.user_ids,
        payload.group_ids,
    )


@router.delete("/api-keys/{key_id}/shares/{shared_user_id}")
@handle_route_errors()
async def remove_api_key_share(
    key_id: str,
    shared_user_id: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_API_KEYS, "auth"))
):
    success = await run_in_threadpool(
        auth_service.delete_api_key_share,
        current_user.user_id,
        current_user.tenant_id,
        key_id,
        shared_user_id,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")
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
    current_user: TokenData = Depends(_require_admin_with_audit_permission),
):
    actor = aliased(User)

    def _list_audit_logs_sync() -> list[dict]:
        with get_db_session() as db:
            query = _build_audit_log_query(db, current_user, tenant_id, actor)

            if start is not None:
                query = query.filter(AuditLog.created_at >= start)
            if end is not None:
                query = query.filter(AuditLog.created_at <= end)
            if user_id:
                query = query.filter(AuditLog.user_id == user_id)
            if action:
                query = query.filter(AuditLog.action == action)
            if resource_type:
                query = query.filter(AuditLog.resource_type == resource_type)
            if q:
                query = query.filter(AuditLog.details.cast(String).ilike(f"%{q}%"))

            rows = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
            items = []
            for log, username, email in rows:
                items.append({
                    "id": log.id,
                    "tenant_id": log.tenant_id,
                    "user_id": log.user_id,
                    "username": username,
                    "email": email,
                    "action": log.action,
                    "resource_type": log.resource_type,
                    "resource_id": _sanitize_resource_id(log.resource_id),
                    "details": _sanitize_audit_details(log.details),
                    "ip_address": log.ip_address,
                    "user_agent": log.user_agent,
                    "created_at": log.created_at,
                })

            ip_address, user_agent = get_request_audit_context()
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=5)
            recent_view = (
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
            if not recent_view:
                db.add(AuditLog(
                    tenant_id=current_user.tenant_id,
                    user_id=current_user.user_id,
                    action="audit_logs.view",
                    resource_type="audit_logs",
                    resource_id="list",
                    details={"limit": limit, "offset": offset},
                    ip_address=ip_address,
                    user_agent=user_agent,
                ))
            return items

    return await run_in_threadpool(_list_audit_logs_sync)


@router.get("/audit-logs/export")
async def export_audit_logs_csv(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    user_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    current_user: TokenData = Depends(_require_admin_with_audit_permission),
):
    actor = aliased(User)

    def _export_audit_rows_sync():
        with get_db_session() as db:
            query = _build_audit_log_query(db, current_user, tenant_id, actor)

            if start is not None:
                query = query.filter(AuditLog.created_at >= start)
            if end is not None:
                query = query.filter(AuditLog.created_at <= end)
            if user_id:
                query = query.filter(AuditLog.user_id == user_id)
            if action:
                query = query.filter(AuditLog.action == action)
            if resource_type:
                query = query.filter(AuditLog.resource_type == resource_type)

            rows = query.order_by(AuditLog.created_at.desc()).all()

            ip_address, user_agent = get_request_audit_context()
            db.add(AuditLog(
                tenant_id=current_user.tenant_id,
                user_id=current_user.user_id,
                action="audit_logs.export",
                resource_type="audit_logs",
                resource_id="csv",
                details={"count": len(rows)},
                ip_address=ip_address,
                user_agent=user_agent,
            ))
            return rows

    rows = await run_in_threadpool(_export_audit_rows_sync)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "created_at", "tenant_id", "user_id", "username", "email", "action", "resource_type", "resource_id", "ip_address", "user_agent", "details"])
    for log, username, email in rows:
        writer.writerow([
            log.id,
            log.created_at.isoformat() if log.created_at else "",
            log.tenant_id or "",
            log.user_id or "",
            username or "",
            email or "",
            log.action,
            log.resource_type,
            _sanitize_resource_id(log.resource_id) or "",
            log.ip_address or "",
            log.user_agent or "",
            json.dumps(_sanitize_audit_details(log.details)),
        ])

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-logs.csv"},
    )


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.READ_USERS, Permission.MANAGE_USERS, Permission.MANAGE_TENANTS], "auth")
    )
):
    users = await run_in_threadpool(auth_service.list_users, current_user.tenant_id, limit=limit, offset=offset)
    return [await run_in_threadpool(auth_service.build_user_response, user, _role_permission_strings(user.role)) for user in users]


@router.post("/users", response_model=UserResponse)
@handle_route_errors()
async def create_user(
    user_create: UserCreate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.CREATE_USERS, Permission.MANAGE_USERS], "auth")
    )
):
    user = await run_in_threadpool(
        auth_service.create_user,
        user_create,
        current_user.tenant_id,
        current_user.user_id,
        current_user.role,
        list(getattr(current_user, "permissions", []) or []),
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

    _invalidate_grafana_proxy_auth_cache()
    return await run_in_threadpool(auth_service.build_user_response, user, _role_permission_strings(user.role))


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_update: UserUpdate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_USERS, Permission.MANAGE_USERS, Permission.MANAGE_TENANTS], "auth")
    )
):
    current_perms = set(getattr(current_user, "permissions", []) or [])
    is_admin_actor = bool(getattr(current_user, "is_superuser", False) or current_user.role == Role.ADMIN)
    has_manage_users = Permission.MANAGE_USERS.value in current_perms or Permission.UPDATE_USERS.value in current_perms
    has_manage_tenants = Permission.MANAGE_TENANTS.value in current_perms
    update_fields = set(user_update.model_dump(exclude_unset=True).keys())

    if has_manage_tenants and not has_manage_users and not is_admin_actor:
        if update_fields - {"is_active"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="manage:tenants can only activate/deactivate non-admin users",
            )

    sensitive_fields = {"role", "org_id", "group_ids"}
    if (update_fields & sensitive_fields) and not is_admin_actor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can modify role, tenant scope, or group memberships",
        )

    user = await run_in_threadpool(auth_service.update_user, user_id, user_update, current_user.tenant_id, current_user.user_id)

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)

    if update_fields & {"role", "group_ids", "org_id", "is_active"}:
        _invalidate_grafana_proxy_auth_cache()
    return await run_in_threadpool(auth_service.build_user_response, user, _role_permission_strings(user.role))


@router.put("/users/{user_id}/password")
@handle_route_errors()
async def update_user_password(
    user_id: str,
    password_update: UserPasswordUpdate,
    current_user: TokenData = Depends(require_authenticated_with_scope("auth"))
):
    if current_user.user_id != user_id:
        current_perms = getattr(current_user, "permissions", []) or []
        if (
            Permission.MANAGE_USERS.value not in current_perms
            and Permission.UPDATE_USERS.value not in current_perms
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


@router.post("/users/{user_id}/password/reset-temp", response_model=TempPasswordResetResponse)
async def reset_user_password_temp(
    user_id: str,
    current_user: TokenData = Depends(require_authenticated_with_scope("auth")),
):
    perms = set(getattr(current_user, "permissions", []) or [])
    is_admin_actor = bool(getattr(current_user, "is_superuser", False) or current_user.role == Role.ADMIN)
    can_manage_users = Permission.MANAGE_USERS.value in perms
    if not (is_admin_actor or can_manage_users):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted to reset passwords")

    target_user = await run_in_threadpool(auth_service.get_user_by_id_in_tenant, user_id, current_user.tenant_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)
    if target_user.role == Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin account passwords cannot be reset")

    result = await run_in_threadpool(
        auth_service.reset_user_password_temp,
        current_user.user_id,
        user_id,
        current_user.tenant_id,
    )
    temporary_password = result.get("temporary_password", "")
    target_email = result.get("target_email")
    target_username = result.get("target_username") or target_user.username

    email_sent = False
    if target_email:
        try:
            email_sent = await notification_service.send_temporary_password_email(
                recipient_email=target_email,
                username=target_username,
                temporary_password=temporary_password,
                login_url=None,
            )
        except Exception as exc:
            logger.warning("Temporary password email skipped: %s", exc)

    return TempPasswordResetResponse(
        temporary_password=temporary_password,
        email_sent=bool(email_sent),
        message="Temporary password generated; user must change password on next login.",
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: TokenData = Depends(require_authenticated_with_scope("auth"))
):
    if not (current_user.is_superuser or current_user.role == Role.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can delete users",
        )
    if current_user.user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )

    target_user = await run_in_threadpool(auth_service.get_user_by_id_in_tenant, user_id, current_user.tenant_id)
    if target_user and target_user.role == Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin accounts cannot be deleted"
        )
    success = await run_in_threadpool(auth_service.delete_user, user_id, current_user.tenant_id, current_user.user_id)

    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)

    _invalidate_grafana_proxy_auth_cache()
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
    group = await run_in_threadpool(auth_service.create_group, group_create, current_user.tenant_id, current_user.user_id)
    _invalidate_grafana_proxy_auth_cache()
    return group


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
    group = await run_in_threadpool(auth_service.update_group, group_id, group_update, current_user.tenant_id, current_user.user_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GROUP_NOT_FOUND)
    _invalidate_grafana_proxy_auth_cache()
    return group


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: str,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.DELETE_GROUPS, Permission.MANAGE_GROUPS], "auth")
    )
):
    success = await run_in_threadpool(auth_service.delete_group, group_id, current_user.tenant_id, current_user.user_id)

    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GROUP_NOT_FOUND)

    _invalidate_grafana_proxy_auth_cache()
    return {"message": "Group deleted successfully"}


@router.put("/users/{user_id}/permissions")
async def update_user_permissions(
    user_id: str,
    permission_names: List[str],
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_USER_PERMISSIONS, Permission.MANAGE_USERS], "auth")
    )
):
    success = await run_in_threadpool(
        auth_service.update_user_permissions,
        user_id,
        permission_names,
        current_user.tenant_id,
        current_user.user_id,
        current_user.role,
        list(getattr(current_user, "permissions", []) or []),
        bool(getattr(current_user, "is_superuser", False)),
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)
    _invalidate_grafana_proxy_auth_cache()
    return {"success": True, "permissions": permission_names}


@router.put("/groups/{group_id}/permissions")
async def update_group_permissions(
    group_id: str,
    permission_names: List[str],
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_GROUP_PERMISSIONS, Permission.MANAGE_GROUPS], "auth")
    )
):
    success = await run_in_threadpool(
        auth_service.update_group_permissions,
        group_id,
        permission_names,
        current_user.tenant_id,
        current_user.user_id,
        current_user.role,
        list(getattr(current_user, "permissions", []) or []),
        bool(getattr(current_user, "is_superuser", False)),
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GROUP_NOT_FOUND)
    _invalidate_grafana_proxy_auth_cache()
    return {"success": True, "permissions": permission_names}


@router.put("/groups/{group_id}/members")
async def update_group_members(
    group_id: str,
    members: GroupMembersUpdate,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_GROUP_MEMBERS, Permission.MANAGE_GROUPS], "auth")
    )
):
    success = await run_in_threadpool(
        auth_service.update_group_members,
        group_id,
        members.user_ids,
        current_user.tenant_id,
        current_user.user_id,
        current_user.role,
        list(getattr(current_user, "permissions", []) or []),
        bool(getattr(current_user, "is_superuser", False)),
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GROUP_NOT_FOUND)
    _invalidate_grafana_proxy_auth_cache()
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
    return {
        role.value: [perm.value for perm in perms]
        for role, perms in ROLE_PERMISSIONS.items()
    }
