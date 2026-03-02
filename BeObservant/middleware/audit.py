"""
Middleware and helpers for request auditing and security headers.

This module centralises the logic that was previously embedded in
``server/main.py``. It exposes a ``security_headers_middleware`` function that
can be registered with the FastAPI app. The middleware records `resource.view`
entries for authenticated GET requests and appends standard security headers to
all responses. Sensitive query parameters are redacted before logging.

The constants and helper functions are also available for tests and other
modules.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import logging
from urllib.parse import parse_qsl, urlencode

from fastapi import Request

from database import get_db_session
from db_models import AuditLog
from middleware.dependencies import auth_service
from middleware.rate_limit import client_ip
from services.audit_context import reset_request_audit_context, set_request_audit_context

logger = logging.getLogger(__name__)

RESOURCE_VIEW_AUDIT_EXCLUDED_PATHS = {
    "/api/auth/me",
    "/api/auth/users",
    "/api/internal/otlp/validate",
}
RESOURCE_VIEW_AUDIT_EXCLUDED_PREFIXES = ("/api/auth/audit-logs",)

SENSITIVE_AUDIT_KEYS_EXACT = {
    "token",
    "secret",
    "password",
    "passcode",
    "authorization",
    "jwt",
    "mfa_code",
    "setup_token",
}
SENSITIVE_AUDIT_KEY_SUFFIXES = ("_token", "_secret", "_password", "_passcode", "_jwt")


def _skip_resource_view_audit(path: str) -> bool:
    return path in RESOURCE_VIEW_AUDIT_EXCLUDED_PATHS or any(
        path.startswith(prefix) for prefix in RESOURCE_VIEW_AUDIT_EXCLUDED_PREFIXES
    )


def _is_sensitive_audit_key(key: str) -> bool:
    lowered = str(key or "").strip().lower()
    if lowered == "status_code":
        return False
    if lowered in SENSITIVE_AUDIT_KEYS_EXACT:
        return True
    return any(lowered.endswith(suffix) for suffix in SENSITIVE_AUDIT_KEY_SUFFIXES)


def _sanitize_query_string(raw_query: str) -> str:
    if not raw_query:
        return ""
    pairs = parse_qsl(raw_query, keep_blank_values=True)
    sanitized: list[tuple[str, str]] = []
    for key, value in pairs:
        sanitized.append((key, "[REDACTED]") if _is_sensitive_audit_key(key) else (key, value))
    return urlencode(sanitized, doseq=True)


def _is_https_request(request: Request) -> bool:
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    return scheme == "https"


def _set_header_if_missing(headers, key: str, value: str) -> None:
    if key not in headers:
        headers[key] = value


async def security_headers_middleware(request: Request, call_next):
    context_tokens = set_request_audit_context(client_ip(request), request.headers.get("user-agent"))
    try:
        response = await call_next(request)
    finally:
        reset_request_audit_context(context_tokens)

    try:
        path = request.url.path
        if request.method == "GET" and path.startswith("/api/") and not _skip_resource_view_audit(path):
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
                                resource_id=path,
                                details={
                                    "method": request.method,
                                    "status_code": response.status_code,
                                    "query": _sanitize_query_string(request.url.query),
                                },
                                ip_address=client_ip(request),
                                user_agent=request.headers.get("user-agent"),
                            )
                        )
    except Exception:
        logger.debug("Skipping middleware audit write for request %s", request.url.path, exc_info=True)

    _set_header_if_missing(response.headers, "X-Content-Type-Options", "nosniff")
    _set_header_if_missing(response.headers, "X-Frame-Options", "DENY")
    _set_header_if_missing(response.headers, "Referrer-Policy", "no-referrer")
    _set_header_if_missing(
        response.headers,
        "Content-Security-Policy",
        "default-src 'self'; "
        "connect-src 'self' https:; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com;",
    )

    if _is_https_request(request):
        _set_header_if_missing(response.headers, "Strict-Transport-Security", "max-age=31536000; includeSubDomains")

    return response