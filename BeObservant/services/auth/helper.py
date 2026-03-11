"""
Helper functions for authentication and authorization operations.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from typing import List, Optional, Set, TypeAlias
import logging

from db_models import AuditLog, User
from sqlalchemy import String
from sqlalchemy.orm import Session
from sqlalchemy.orm.query import RowReturningQuery

from fastapi import Depends, HTTPException, Request, Response, status

from config import config
from models.access.auth_models import TokenData, Permission, Role, ROLE_PERMISSIONS
from custom_types.json import JSONDict
from services.common.cookies import cookie_secure
from services.auth.delegation import is_admin_actor as _is_admin_actor, role_to_text as _role_to_text
from middleware.dependencies import enforce_public_endpoint_security, require_permission_with_scope
logger = logging.getLogger(__name__)

AuditLogQueryRow: TypeAlias = tuple[AuditLog, str, str]

AUDIT_SENSITIVE_SUBSTRINGS = (
    "token",
    "secret",
    "password",
    "passcode",
    "authorization",
    "bearer",
    "jwt",
)

AUDIT_SENSITIVE_EXACT_KEYS = {
    "mfa_code",
    "setup_token",
    "auth_code",
    "oauth_code",
    "code",
}

def invalidate_grafana_proxy_auth_cache() -> None:
    try:
        from services.grafana.proxy_auth_ops import clear_proxy_auth_cache

        clear_proxy_auth_cache()
    except (AttributeError, ImportError) as exc:
        logger.warning("Failed to invalidate Grafana proxy auth cache: %s", exc)


def require_admin_with_audit_permission(current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_AUDIT_LOGS, "auth"))) -> TokenData:
    if not is_admin_check(current_user):
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
    if lowered in AUDIT_SENSITIVE_EXACT_KEYS:
        return True
    return any(marker in lowered for marker in AUDIT_SENSITIVE_SUBSTRINGS)


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


def sanitize_audit_details(details: Optional[JSONDict]) -> JSONDict:
    source = details if isinstance(details, dict) else {}
    sanitized: JSONDict = {}
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

def build_audit_log_query(
    db: Session,
    current_user: TokenData,
    tenant_id: Optional[str],
    actor: type[User],
) -> RowReturningQuery[AuditLogQueryRow]:
    query = (
        db.query(AuditLog, actor.username, actor.email)
        .outerjoin(actor, actor.id == AuditLog.user_id)
    )
    if not getattr(current_user, "is_superuser", False):
        query = query.filter(AuditLog.tenant_id == current_user.tenant_id)
    elif tenant_id:
        query = query.filter(AuditLog.tenant_id == tenant_id)
    return query


def role_permission_strings(role: object) -> List[str]:
    if not isinstance(role, Role):
        return []
    return [p.value for p in ROLE_PERMISSIONS.get(role, [])]


def perms_check(user: TokenData) -> Set[str]:
    return {str(permission) for permission in (getattr(user, "permissions", []) or [])}


def is_admin_check(user: TokenData) -> bool:
    return _is_admin_actor(
        actor_role=_role_to_text(getattr(user, "role", None)),
        actor_is_superuser=bool(getattr(user, "is_superuser", False)),
    )


def apply_audit_filters_func(
    query: RowReturningQuery[AuditLogQueryRow],
    start: object,
    end: object,
    user_id: Optional[str],
    action: Optional[str],
    resource_type: Optional[str],
    q: Optional[str] = None,
) -> RowReturningQuery[AuditLogQueryRow]:
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


def rate_limit_func(request: Request, scope: str, limit: int, window: int) -> None:
    enforce_public_endpoint_security(
        request, scope=scope, limit=limit, window_seconds=window,
        allowlist=config.AUTH_PUBLIC_IP_ALLOWLIST,
    )
