"""
Middleware and helpers for request auditing and security headers.

This module centralises the logic that was previously embedded in
``server/main.py``. It exposes a ``security_headers_middleware`` function that
can be registered with the FastAPI app. The middleware records `resource.view`
entries for authenticated GET requests and appends standard security headers to
all responses. Sensitive query parameters are redacted before logging.

The constants and helper functions are also available for tests and other
modules.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode
import logging

from fastapi import Request

from middleware.rate_limit import client_ip
from services.audit_context import set_request_audit_context, reset_request_audit_context
from database import get_db_session
from db_models import AuditLog
from middleware.dependencies import auth_service

logger = logging.getLogger(__name__)

RESOURCE_VIEW_AUDIT_EXCLUDED_PATHS = {
    "/api/auth/me",
    "/api/auth/users",
    "/api/internal/otlp/validate",
}
RESOURCE_VIEW_AUDIT_EXCLUDED_PREFIXES = (
    "/api/auth/audit-logs",
)

SENSITIVE_AUDIT_KEYS = (
    "token",
    "secret",
    "password",
    "passcode",
    "authorization",
    "bearer",
    "jwt",
    "mfa_code",
    "setup_token",
    "code",
)


def _skip_resource_view_audit(path: str) -> bool:
    if path in RESOURCE_VIEW_AUDIT_EXCLUDED_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in RESOURCE_VIEW_AUDIT_EXCLUDED_PREFIXES)


def _is_sensitive_audit_key(key: str) -> bool:
    lowered = str(key or "").strip().lower()
    if lowered == "status_code":
        return False
    return any(marker in lowered for marker in SENSITIVE_AUDIT_KEYS)


def _sanitize_query_string(raw_query: str) -> str:
    if not raw_query:
        return ""
    pairs = parse_qsl(raw_query, keep_blank_values=True)
    sanitized: list[tuple[str, str]] = []
    for key, value in pairs:
        if _is_sensitive_audit_key(key):
            sanitized.append((key, "[REDACTED]"))
        else:
            sanitized.append((key, value))
    return urlencode(sanitized, doseq=True)


async def security_headers_middleware(request: Request, call_next):
    context_tokens = set_request_audit_context(
        client_ip(request), request.headers.get("user-agent")
    )
    try:
        response = await call_next(request)
    finally:
        reset_request_audit_context(context_tokens)

    try:
        if request.method == "GET" and request.url.path.startswith("/api/") and not _skip_resource_view_audit(request.url.path):
            auth_header = request.headers.get("authorization", "")
            cookie_token = request.cookies.get("beobservant_token")
            bearer = auth_header.split(" ", 1)[1].strip() if auth_header.lower().startswith("bearer ") else None
            token = bearer or cookie_token
            if token:
                token_data = auth_service.decode_token(token)
                if token_data:
                    with get_db_session() as db:
                        db.add(
                            AuditLog(
                                tenant_id=token_data.tenant_id,
                                user_id=token_data.user_id,
                                action="resource.view",
                                resource_type="http",
                                resource_id=request.url.path,
                                details={
                                    "method": request.method,
                                    "status_code": response.status_code,
                                    "query": _sanitize_query_string(str(request.query_params)),
                                },
                                ip_address=client_ip(request),
                                user_agent=request.headers.get("user-agent"),
                            )
                        )
    except Exception:
        logger.debug("Skipping middleware audit write for request %s", request.url.path)

    # security headers
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "connect-src 'self' https:; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com;"
    )
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response
