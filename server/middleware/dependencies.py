"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


"""Shared FastAPI dependency helpers (moved from routers).

This module centralizes authentication and scoped rate-limit dependencies
for use by route handlers and other middleware.
"""

from hmac import compare_digest
from ipaddress import ip_address, ip_network
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import config
from middleware.rate_limit import enforce_rate_limit, enforce_ip_rate_limit, client_ip
from models.access.auth_models import Permission, TokenData
from services.database_auth_service import DatabaseAuthService


auth_service = DatabaseAuthService()
security = HTTPBearer(auto_error=False)


def _extract_bearer_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    if credentials and getattr(credentials, "credentials", None):
        return credentials.credentials

    cookie_token = request.cookies.get("beobservant_token")
    if cookie_token:
        return cookie_token

    return None


def resolve_tenant_id(request: Request, current_user: TokenData) -> str:
    """Resolve tenant from request headers with scoped authorization checks.

    Rules:
    - No header -> use user's org_id fallback.
    - Superusers may target any org_id via header.
    - Regular users may target only their own org_id or one of their API key values.
    """
    default_org_id = getattr(current_user, "org_id", config.DEFAULT_ORG_ID)
    header_value = request.headers.get("x-scope-orgid") or request.headers.get("X-Scope-OrgID")
    if not header_value:
        return default_org_id

    candidate_org_id = header_value.strip()
    if not candidate_org_id:
        return default_org_id

    if candidate_org_id == default_org_id:
        return candidate_org_id

    if getattr(current_user, "is_superuser", False):
        return candidate_org_id

    try:
        user_keys = auth_service.list_api_keys(current_user.user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to resolve tenant scope",
        )

    allowed_org_ids = {key.key for key in user_keys if getattr(key, "is_enabled", True)}
    allowed_org_ids.add(default_org_id)
    if candidate_org_id in allowed_org_ids:
        return candidate_org_id

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Tenant scope not permitted for this user",
    )


def apply_scoped_rate_limit(current_user: TokenData, scope: str) -> None:
    """Apply per-user scoped rate limiting for an API subsystem."""
    enforce_rate_limit(
        key=f"user:{current_user.user_id}:{scope}",
        limit=config.RATE_LIMIT_USER_PER_MINUTE,
        window_seconds=60,
    )


def _parse_ip_allowlist(allowlist: str | None) -> list:
    if not allowlist:
        return []

    networks = []
    for raw in allowlist.split(","):
        entry = raw.strip()
        if not entry:
            continue
        try:
            if "/" in entry:
                networks.append(ip_network(entry, strict=False))
            else:
                ip = ip_address(entry)
                suffix = 32 if ip.version == 4 else 128
                networks.append(ip_network(f"{entry}/{suffix}", strict=False))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Invalid IP allowlist entry: {entry}",
            ) from exc
    return networks


def enforce_ip_allowlist(request: Request, allowlist: str | None, *, scope: str) -> None:
    networks = _parse_ip_allowlist(allowlist)
    if not networks:
        return

    client = client_ip(request)
    try:
        client_addr = ip_address(client)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied for {scope}: invalid client IP",
        )

    if any(client_addr in network for network in networks):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Access denied for {scope}: source IP not allowed",
    )


def enforce_public_endpoint_security(
    request: Request,
    *,
    scope: str,
    limit: int,
    window_seconds: int,
    allowlist: str | None = None,
) -> None:
    resolved_ip = client_ip(request)
    if config.REQUIRE_CLIENT_IP_FOR_PUBLIC_ENDPOINTS and resolved_ip == "unknown":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied for {scope}: client IP resolution failed",
        )

    enforce_ip_rate_limit(
        request,
        scope=scope,
        limit=limit,
        window_seconds=window_seconds,
    )
    enforce_ip_allowlist(request, allowlist, scope=scope)


def enforce_header_token(
    request: Request,
    *,
    header_name: str,
    expected_token: str | None,
    unauthorized_detail: str,
) -> None:
    if not expected_token:
        return
    provided = request.headers.get(header_name)
    if not provided or not compare_digest(provided, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=unauthorized_detail,
        )


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> TokenData:
    """Decode JWT, validate the user, and resolve fresh permissions in a single pass.

    Kept intentionally identical to the previous implementation to avoid
    behavioral changes when moving the dependency.
    """
    token = _extract_bearer_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = auth_service.decode_token(token)

    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired or your token is invalid. Let's get you a new one.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if isinstance(token_data, dict):
        try:
            token_data = TokenData(**token_data)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Your session has expired or your token is invalid. Let's get you a new one.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    user = auth_service.get_user_by_id(token_data.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    token_data.org_id = getattr(user, "org_id", token_data.org_id)
    token_data.permissions = auth_service.get_user_permissions(user)
    enforce_rate_limit(
        key=f"user:{token_data.user_id}",
        limit=config.RATE_LIMIT_USER_PER_MINUTE,
        window_seconds=60,
    )

    return token_data


def get_current_user_or_mfa_setup(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> TokenData:
    """Allow either a fully-authenticated token or a short-lived MFA-setup token.

    Used by `/api/auth/mfa/*` endpoints so a freshly-logged-in admin can
    use the provided setup token to enroll/verify TOTP without having full
    application sessions yet.
    """
    token = _extract_bearer_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You need to log in to access this resource",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = auth_service.decode_token(token)

    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired or your token is invalid. Let's get you a new one.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if getattr(token_data, "is_mfa_setup", False):
        user = auth_service.get_user_by_id(token_data.user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
        if getattr(user, 'mfa_enabled', False):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MFA setup not permitted for this user")
        return token_data

    return get_current_user(request, credentials)


def require_permission(permission: Permission | str):
    """FastAPI dependency that enforces a specific permission.

    Accepts either a Permission enum member or a raw string permission name.
    """
    perm_value = permission.value if hasattr(permission, "value") else str(permission)

    def permission_checker(current_user: TokenData = Depends(get_current_user)):
        if perm_value not in current_user.permissions and not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"You don't have the permission to {perm_value.upper()}, "
                    "please contact your administrator if you think this is a mistake."
                ),
            )
        return current_user

    return permission_checker


def require_permission_with_scope(permission: Permission | str, scope: str):
    perm_checker = require_permission(permission)

    def dependency(current_user: TokenData = Depends(perm_checker)):
        apply_scoped_rate_limit(current_user, scope)
        return current_user

    return dependency


def require_any_permission(permissions: list[Permission | str]):
    perm_values = [permission.value if hasattr(permission, "value") else str(permission) for permission in permissions]

    def permission_checker(current_user: TokenData = Depends(get_current_user)):
        if current_user.is_superuser:
            return current_user
        if any(perm_value in current_user.permissions for perm_value in perm_values):
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You don't have any of the required permissions: "
                f"{', '.join(p.upper() for p in perm_values)}"
            ),
        )

    return permission_checker


def require_any_permission_with_scope(permissions: list[Permission | str], scope: str):
    perm_checker = require_any_permission(permissions)

    def dependency(current_user: TokenData = Depends(perm_checker)):
        apply_scoped_rate_limit(current_user, scope)
        return current_user

    return dependency


def require_authenticated_with_scope(scope: str):
    def dependency(current_user: TokenData = Depends(get_current_user)):
        apply_scoped_rate_limit(current_user, scope)
        return current_user

    return dependency
