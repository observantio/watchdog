"""
These are ASGI middleware components for enforcing request size limits
and concurrency limits on incoming HTTP requests.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import logging
from datetime import datetime, timezone
from hmac import compare_digest
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError

from config import config
from database import get_db_session
from db_models import ApiKeyShare, User, UserApiKey
from middleware.rate_limit import enforce_rate_limit, enforce_ip_rate_limit, client_ip
from models.access.auth_models import Permission, TokenData
from services.database_auth_service import DatabaseAuthService

logger = logging.getLogger(__name__)

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

async def resolve_tenant_id(request: Request, current_user: TokenData) -> str:
    default_org_id = getattr(current_user, "org_id", config.DEFAULT_ORG_ID)
    header_value = request.headers.get("x-scope-orgid")
    if not header_value:
        return default_org_id

    candidate_org_id = header_value.strip()
    if not candidate_org_id or candidate_org_id == default_org_id:
        return default_org_id

    if getattr(current_user, "is_superuser", False):
        return candidate_org_id

    try:
        allowed_org_ids = await run_in_threadpool(
            _load_allowed_org_ids_for_user,
            current_user=current_user,
            default_org_id=default_org_id,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to resolve tenant scope",
        ) from exc

    if candidate_org_id not in allowed_org_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant scope not permitted for this user",
        )

    try:
        conflict = await run_in_threadpool(
            _scope_exists_in_other_tenants,
            org_id=candidate_org_id,
            tenant_id=current_user.tenant_id,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to resolve tenant scope",
        ) from exc

    if conflict:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant scope is ambiguous across tenants",
        )

    return candidate_org_id

def _load_allowed_org_ids_for_user(*, current_user: TokenData, default_org_id: str) -> set[str]:
    allowed_org_ids: set[str] = set()

    with get_db_session() as db:
        user = (
            db.query(User)
            .filter_by(id=current_user.user_id, tenant_id=current_user.tenant_id)
            .first()
        )
        if not user or not getattr(user, "is_active", False):
            return {default_org_id}

        active_org_id = str(getattr(user, "org_id", "") or default_org_id)
        if active_org_id:
            allowed_org_ids.add(active_org_id)

        own_enabled_rows = (
            db.query(UserApiKey.key)
            .filter(
                UserApiKey.user_id == current_user.user_id,
                UserApiKey.tenant_id == current_user.tenant_id,
                UserApiKey.is_enabled.is_(True),
            )
            .all()
        )
        allowed_org_ids.update(str(row[0]) for row in own_enabled_rows if row and row[0])

        shared_rows = (
            db.query(UserApiKey.key)
            .join(ApiKeyShare, ApiKeyShare.api_key_id == UserApiKey.id)
            .filter(
                ApiKeyShare.shared_user_id == current_user.user_id,
                ApiKeyShare.can_use.is_(True),
                ApiKeyShare.tenant_id == current_user.tenant_id,
                UserApiKey.tenant_id == current_user.tenant_id,
                UserApiKey.is_enabled.is_(True),
            )
            .all()
        )
        allowed_org_ids.update(str(row[0]) for row in shared_rows if row and row[0])

    allowed_org_ids.add(str(default_org_id))
    return {org_id for org_id in allowed_org_ids if org_id}


def _scope_exists_in_other_tenants(*, org_id: str, tenant_id: str) -> bool:
    with get_db_session() as db:
        conflict = (
            db.query(UserApiKey.id)
            .filter(
                UserApiKey.key == org_id,
                UserApiKey.tenant_id != tenant_id,
            )
            .first()
        )
        return conflict is not None


def apply_scoped_rate_limit(current_user: TokenData, scope: str) -> None:
    enforce_rate_limit(
        key=f"user:{current_user.user_id}:{scope}",
        limit=config.RATE_LIMIT_USER_PER_MINUTE,
        window_seconds=60,
    )


def _enforce_session_revocation(user: object, token_data: TokenData) -> None:
    invalid_before = getattr(user, "session_invalid_before", None)
    if invalid_before is None:
        return
    if getattr(invalid_before, "tzinfo", None) is None:
        invalid_before = invalid_before.replace(tzinfo=timezone.utc)
    token_iat = getattr(token_data, "iat", None)
    if token_iat is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired or your token is invalid. Let's get you a new one.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_iat_dt = datetime.fromtimestamp(int(token_iat), tz=timezone.utc)
    if token_iat_dt <= invalid_before:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired or your token is invalid. Let's get you a new one.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _parse_ip_allowlist(allowlist: str | None) -> list[IPv4Network | IPv6Network]:
    if not allowlist:
        return []
    networks: list[IPv4Network | IPv6Network] = []
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
            logger.error("Invalid IP allowlist entry %r — failing closed", entry)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: server misconfiguration",
            ) from exc
    return networks


def enforce_ip_allowlist(request: Request, allowlist: str | None, *, scope: str) -> None:
    networks = _parse_ip_allowlist(allowlist)
    if not networks:
        if allowlist is None:
            return
        if config.ALLOWLIST_FAIL_OPEN:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied for {scope}: source IP not allowed",
        )

    client = client_ip(request)
    try:
        client_addr = ip_address(client)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied for {scope}: invalid client IP",
        ) from exc

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
    fallback_mode: str | None = None,
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
        fallback_mode=fallback_mode,
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

    if getattr(token_data, "is_mfa_setup", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA setup token cannot be used for this endpoint",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = auth_service.get_user_by_id(token_data.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    _enforce_session_revocation(user, token_data)

    token_data.org_id = getattr(user, "org_id", token_data.org_id)
    token_data.permissions = auth_service.get_user_permissions(user)

    live_group_ids = getattr(user, "group_ids", None)
    if isinstance(live_group_ids, list):
        source_group_ids = live_group_ids
    elif isinstance(live_group_ids, tuple):
        source_group_ids = list(live_group_ids)
    elif isinstance(live_group_ids, set):
        source_group_ids = list(live_group_ids)
    else:
        source_group_ids = []
    token_data.group_ids = [str(gid) for gid in source_group_ids if str(gid).strip()]

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
        if getattr(user, "mfa_enabled", False):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MFA setup not permitted for this user")
        _enforce_session_revocation(user, token_data)
        return token_data

    return get_current_user(request, credentials)


def require_permission(permission: Permission | str) -> Callable[[TokenData], TokenData]:
    perm_value = permission.value if hasattr(permission, "value") else str(permission)

    def permission_checker(current_user: TokenData = Depends(get_current_user)) -> TokenData:
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


def require_permission_with_scope(permission: Permission | str, scope: str) -> Callable[[TokenData], TokenData]:
    perm_checker = require_permission(permission)

    def dependency(current_user: TokenData = Depends(perm_checker)) -> TokenData:
        apply_scoped_rate_limit(current_user, scope)
        return current_user

    return dependency


def require_any_permission(permissions: list[Permission | str]) -> Callable[[TokenData], TokenData]:
    perm_values = [p.value if hasattr(p, "value") else str(p) for p in permissions]

    def permission_checker(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        if current_user.is_superuser:
            return current_user
        if any(pv in current_user.permissions for pv in perm_values):
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You don't have any of the required permissions: "
                f"{', '.join(p.upper() for p in perm_values)}"
            ),
        )

    return permission_checker


def require_any_permission_with_scope(permissions: list[Permission | str], scope: str) -> Callable[[TokenData], TokenData]:
    perm_checker = require_any_permission(permissions)

    def dependency(current_user: TokenData = Depends(perm_checker)) -> TokenData:
        apply_scoped_rate_limit(current_user, scope)
        return current_user

    return dependency


def require_authenticated_with_scope(scope: str) -> Callable[[TokenData], TokenData]:
    def dependency(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        apply_scoped_rate_limit(current_user, scope)
        return current_user

    return dependency
