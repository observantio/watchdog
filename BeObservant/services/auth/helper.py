from urllib.request import Request
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from typing import Optional, List
import logging

from db_models import AuditLog
from sqlalchemy import String

from fastapi import Depends, HTTPException, status, Response
    
from config import config
from models.access.auth_models import TokenData, Permission, Role, ROLE_PERMISSIONS
from services.common.cookies import cookie_secure
from middleware.dependencies import enforce_public_endpoint_security, require_permission_with_scope
logger = logging.getLogger(__name__)

AUDIT_SENSITIVE_KEYS = (
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
    "code",
)

def invalidate_grafana_proxy_auth_cache() -> None:
    try:
        from services.grafana.proxy_auth_ops import clear_proxy_auth_cache

        clear_proxy_auth_cache()
    except Exception as exc:
        logger.warning("Failed to invalidate Grafana proxy auth cache: %s", exc)


def require_admin_with_audit_permission(current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_AUDIT_LOGS, "auth"))):
    if str(getattr(current_user, "role", "")).lower() != Role.ADMIN.value and not getattr(current_user, "is_superuser", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required to view audit logs")
    return current_user



def set_auth_cookie(request: Request, response: Response, token: str) -> None:
    secure_flag = bool(config.FORCE_SECURE_COOKIES) or cookie_secure(request)
    response.set_cookie(
        key="beobservant_token",
        value=token,
        httponly=True,
        secure=secure_flag,
        samesite="lax",
        max_age=config.JWT_EXPIRATION_MINUTES * 60,
        path="/",
    )

def audit_key_is_sensitive(key: str) -> bool:
    lowered = str(key or "").strip().lower()
    if lowered == "status_code":
        return False
    return any(marker in lowered for marker in AUDIT_SENSITIVE_KEYS)


def redact_query_string(raw: str) -> str:
    if not raw:
        return ""
    pairs = parse_qsl(raw, keep_blank_values=True)
    sanitized = []
    for key, value in pairs:
        sanitized.append((key, "[REDACTED]" if audit_key_is_sensitive(key) else value))
    return urlencode(sanitized, doseq=True)


def sanitize_resource_id(resource_id: Optional[str]) -> str:
    text = str(resource_id or "")
    if not text or "?" not in text:
        return text
    parsed = urlsplit(text)
    if not parsed.query:
        return text
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, redact_query_string(parsed.query), parsed.fragment))


def sanitize_audit_details(details: Optional[dict]) -> dict:
    source = details if isinstance(details, dict) else {}
    sanitized = {}
    for key, value in source.items():
        if audit_key_is_sensitive(key):
            sanitized[key] = "[REDACTED]"
            continue
        if key == "query" and isinstance(value, str):
            sanitized[key] = redact_query_string(value)
            continue
        sanitized[key] = value
    return sanitized


def clear_auth_cookie(request: Request, response: Response) -> None:
    secure_flag = bool(config.FORCE_SECURE_COOKIES) or cookie_secure(request)
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

def build_audit_log_query(db, current_user: TokenData, tenant_id: Optional[str], actor):
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


def role_permission_strings(role) -> List[str]:
    return [p.value for p in ROLE_PERMISSIONS.get(role, [])]


def perms_check(user: TokenData) -> set:
    return set(getattr(user, "permissions", []) or [])


def is_admin_check(user: TokenData) -> bool:
    return bool(getattr(user, "is_superuser", False) or user.role == Role.ADMIN)


def apply_audit_filters_func(query, start, end, user_id, action, resource_type, q=None):
    if start:
        query = query.filter(AuditLog.created_at >= start)
    if end:
        query = query.filter(AuditLog.created_at <= end)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    if q:
        query = query.filter(AuditLog.details.cast(String).ilike(f"%{q}%"))
    return query


def rate_limit_func(request: Request, scope: str, limit: int, window: int):
    enforce_public_endpoint_security(
        request, scope=scope, limit=limit, window_seconds=window,
        allowlist=config.AUTH_PUBLIC_IP_ALLOWLIST,
    )