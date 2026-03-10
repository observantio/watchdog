"""
These are ASGI middleware components for enforcing request size limits
and concurrency limits on incoming HTTP requests.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from hmac import compare_digest
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network

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

ALLOWLIST_DISABLED = object()
GENERIC_ACCESS_DENIED_DETAIL = "Access denied"
GENERIC_SCOPE_DENIED_DETAIL = "Requested tenant scope is not permitted"
RATE_LIMIT_FALLBACK_MODES = {"memory", "deny", "allow"}


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


def _normalize_group_ids(group_ids: object) -> list[str]:
    if isinstance(group_ids, list):
        source_group_ids = group_ids
    elif isinstance(group_ids, tuple):
        source_group_ids = list(group_ids)
    elif isinstance(group_ids, set):
        source_group_ids = list(group_ids)
    else:
        source_group_ids = []

    normalized: list[str] = []
    seen: set[str] = set()
    for group_id in source_group_ids:
        value = str(group_id).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _hydrate_authenticated_user(token_data: TokenData, user: object) -> TokenData:
    token_data.org_id = getattr(user, "org_id", token_data.org_id)
    token_data.permissions = auth_service.get_user_permissions(user)
    token_data.group_ids = _normalize_group_ids(getattr(user, "group_ids", None))
    return token_data


def _authenticate_request(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    *,
    missing_detail: str,
    allow_mfa_setup: bool = False,
    apply_base_rate_limit: bool = True,
) -> TokenData:
    token = _extract_bearer_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=missing_detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = auth_service.decode_token(token)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired or your token is invalid. Let's get you a new one.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if getattr(token_data, "is_mfa_setup", False) and not allow_mfa_setup:
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

    if getattr(token_data, "is_mfa_setup", False):
        if getattr(user, "mfa_enabled", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="MFA setup not permitted for this user",
            )
        return token_data

    token_data = _hydrate_authenticated_user(token_data, user)

    if apply_base_rate_limit:
        enforce_rate_limit(
            key=f"user:{token_data.user_id}",
            limit=config.RATE_LIMIT_USER_PER_MINUTE,
            window_seconds=60,
        )

    return token_data


def _resolve_allowlist_setting(allowlist: str | None) -> str | object:
    if allowlist is None:
        return ALLOWLIST_DISABLED
    return str(allowlist)


def _validate_rate_limit_fallback_mode(fallback_mode: str | None) -> str | None:
    if fallback_mode is None:
        return None
    normalized = str(fallback_mode).strip().lower()
    if not normalized:
        return None
    if normalized not in RATE_LIMIT_FALLBACK_MODES:
        raise ValueError("fallback_mode must be one of: allow, deny, memory")
    return normalized

async def resolve_tenant_id(request: Request, current_user: TokenData) -> str:
    default_scope_id = getattr(current_user, "org_id", config.DEFAULT_ORG_ID)
    header_value = request.headers.get("x-scope-orgid")
    if not header_value:
        return default_scope_id

    candidate_scope_id = header_value.strip()
    if not candidate_scope_id or candidate_scope_id == default_scope_id:
        return default_scope_id

    if getattr(current_user, "is_superuser", False):
        return candidate_scope_id

    try:
        allowed_scope_ids = await run_in_threadpool(
            _load_allowed_scope_ids_for_user,
            current_user=current_user,
            default_scope_id=default_scope_id,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to resolve tenant scope",
        ) from exc

    if candidate_scope_id not in allowed_scope_ids:
        logger.info(
            "Rejected tenant scope for user=%s tenant=%s scope=%s: not in allowed set",
            current_user.user_id,
            current_user.tenant_id,
            candidate_scope_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=GENERIC_SCOPE_DENIED_DETAIL,
        )

    try:
        conflict = await run_in_threadpool(
            _scope_exists_in_other_tenants,
            scope_id=candidate_scope_id,
            tenant_id=current_user.tenant_id,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to resolve tenant scope",
        ) from exc

    if conflict:
        logger.warning(
            "Rejected ambiguous tenant scope for user=%s tenant=%s scope=%s",
            current_user.user_id,
            current_user.tenant_id,
            candidate_scope_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=GENERIC_SCOPE_DENIED_DETAIL,
        )

    return candidate_scope_id

def _load_allowed_scope_ids_for_user(*, current_user: TokenData, default_scope_id: str) -> set[str]:
    allowed_scope_ids: set[str] = set()

    with get_db_session() as db:
        user = (
            db.query(User)
            .filter_by(id=current_user.user_id, tenant_id=current_user.tenant_id)
            .first()
        )
        if not user or not getattr(user, "is_active", False):
            return {default_scope_id}

        active_scope_id = str(getattr(user, "org_id", "") or default_scope_id)
        if active_scope_id:
            allowed_scope_ids.add(active_scope_id)

        own_enabled_rows = (
            db.query(UserApiKey.key)
            .filter(
                UserApiKey.user_id == current_user.user_id,
                UserApiKey.tenant_id == current_user.tenant_id,
                UserApiKey.is_enabled.is_(True),
            )
            .all()
        )
        allowed_scope_ids.update(str(row[0]) for row in own_enabled_rows if row and row[0])

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
        allowed_scope_ids.update(str(row[0]) for row in shared_rows if row and row[0])

    allowed_scope_ids.add(str(default_scope_id))
    return {scope_id for scope_id in allowed_scope_ids if scope_id}


def _load_allowed_org_ids_for_user(*, current_user: TokenData, default_org_id: str) -> set[str]:
    return _load_allowed_scope_ids_for_user(current_user=current_user, default_scope_id=default_org_id)


def _scope_exists_in_other_tenants(*, scope_id: str | None = None, tenant_id: str, org_id: str | None = None) -> bool:
    resolved_scope_id = str(scope_id or org_id or "").strip()
    if not resolved_scope_id:
        return False
    with get_db_session() as db:
        conflict = (
            db.query(UserApiKey.id)
            .filter(
                UserApiKey.key == resolved_scope_id,
                UserApiKey.tenant_id != tenant_id,
            )
            .first()
        )
        return conflict is not None


def _scope_aware_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> TokenData:
    return _authenticate_request(
        request,
        credentials,
        missing_detail="Authentication required",
        apply_base_rate_limit=False,
    )


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
    # Legacy rows may still store naive UTC timestamps. Treat them as UTC
    # consistently so revocation checks remain monotonic.
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
    resolved_allowlist = _resolve_allowlist_setting(allowlist)
    if resolved_allowlist is ALLOWLIST_DISABLED:
        return

    networks = _parse_ip_allowlist(str(resolved_allowlist))
    if not networks:
        logger.warning(
            "Empty IP allowlist configured for scope=%s; fail_open=%s",
            scope,
            bool(config.ALLOWLIST_FAIL_OPEN),
        )
        if config.ALLOWLIST_FAIL_OPEN:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=GENERIC_ACCESS_DENIED_DETAIL,
        )

    client = client_ip(request)
    try:
        client_addr = ip_address(client)
    except ValueError as exc:
        logger.warning("Rejected request for scope=%s due to invalid client IP: %s", scope, client)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=GENERIC_ACCESS_DENIED_DETAIL,
        ) from exc

    if any(client_addr in network for network in networks):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=GENERIC_ACCESS_DENIED_DETAIL,
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
    resolved_fallback_mode = _validate_rate_limit_fallback_mode(fallback_mode)
    resolved_ip = client_ip(request)
    if config.REQUIRE_CLIENT_IP_FOR_PUBLIC_ENDPOINTS and resolved_ip == "unknown":
        logger.warning("Rejected public request for scope=%s because client IP resolution failed", scope)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=GENERIC_ACCESS_DENIED_DETAIL,
        )
    enforce_ip_rate_limit(
        request,
        scope=scope,
        limit=limit,
        window_seconds=window_seconds,
        fallback_mode=resolved_fallback_mode,
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
    return _authenticate_request(
        request,
        credentials,
        missing_detail="Authentication required",
    )


def get_current_user_or_mfa_setup(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> TokenData:
    return _authenticate_request(
        request,
        credentials,
        missing_detail="You need to log in to access this resource",
        allow_mfa_setup=True,
    )


def require_permission(permission: Permission | str) -> Callable[..., TokenData]:
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


def require_permission_with_scope(permission: Permission | str, scope: str) -> Callable[..., TokenData]:
    perm_value = permission.value if hasattr(permission, "value") else str(permission)

    def permission_checker(current_user: TokenData = Depends(_scope_aware_current_user)) -> TokenData:
        if perm_value not in current_user.permissions and not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"You don't have the permission to {perm_value.upper()}, "
                    "please contact your administrator if you think this is a mistake."
                ),
            )
        return current_user

    def dependency(current_user: TokenData = Depends(permission_checker)) -> TokenData:
        apply_scoped_rate_limit(current_user, scope)
        return current_user

    return dependency


def require_any_permission(permissions: list[Permission | str]) -> Callable[..., TokenData]:
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


def require_any_permission_with_scope(permissions: list[Permission | str], scope: str) -> Callable[..., TokenData]:
    perm_values = [p.value if hasattr(p, "value") else str(p) for p in permissions]

    def permission_checker(current_user: TokenData = Depends(_scope_aware_current_user)) -> TokenData:
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

    def dependency(current_user: TokenData = Depends(permission_checker)) -> TokenData:
        apply_scoped_rate_limit(current_user, scope)
        return current_user

    return dependency


def require_authenticated_with_scope(scope: str) -> Callable[..., TokenData]:
    def dependency(current_user: TokenData = Depends(_scope_aware_current_user)) -> TokenData:
        apply_scoped_rate_limit(current_user, scope)
        return current_user

    return dependency
