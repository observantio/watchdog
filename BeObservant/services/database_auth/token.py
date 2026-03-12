"""
Database authentication service utilities for handling token decoding and user information extraction, including functions to decode access tokens, extract user information from tokens, and build token data structures based on user information. This module provides a common interface for handling token-related operations in the database authentication service, allowing for consistent decoding of tokens and extraction of relevant user information such as permissions and group memberships while also supporting integration with external authentication providers when enabled.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import Optional, Set, TYPE_CHECKING

from models.access.auth_models import Role, TokenData
from services.auth.auth_ops import decode_token as decode_token_op
from services.database_auth.shared import safe_role, sync_active_user_from_claims

from db_models import User

if TYPE_CHECKING:
    from services.database_auth_service import DatabaseAuthService

def build_token_data_for_user(service: DatabaseAuthService, user: User) -> TokenData:
    role = safe_role(getattr(user, "role", None))

    return TokenData(
        user_id=user.id,
        username=user.username,
        tenant_id=user.tenant_id,
        org_id=user.org_id,
        role=role,
        is_superuser=getattr(user, "is_superuser", False),
        permissions=service.get_user_permissions(user) or [],
        group_ids=[g.id for g in (getattr(user, "groups", None) or [])],
    )

def decode_token(service: DatabaseAuthService, token: str) -> Optional[TokenData]:
    local_token = decode_token_op(service, token)
    if local_token:
        return local_token

    if not service.is_external_auth_enabled():
        return None

    claims = service.oidc_service.verify_access_token(token)
    user = sync_active_user_from_claims(service, claims)
    if user is None:
        return None

    token_data = build_token_data_for_user(service, user)
    if not isinstance(claims, dict):
        return token_data

    issued_at = claims.get("iat")
    token_data.iat = issued_at if isinstance(issued_at, int) else None

    known_permissions = _known_permission_names(service)
    oidc_permissions = set(service._extract_permissions_from_oidc_claims(claims) or [])
    merged = set(token_data.permissions or []) | (oidc_permissions & known_permissions)
    token_data.permissions = sorted(merged)

    return token_data

def _safe_role(raw_role: Optional[str]) -> Role:
    return safe_role(raw_role)

def _known_permission_names(service: DatabaseAuthService) -> Set[str]:
    perms = service.list_all_permissions() or []
    names: Set[str] = set()
    for p in perms:
        name = p.get("name") if isinstance(p, dict) else None
        if isinstance(name, str) and name:
            names.add(name)
    return names
