"""
Database authentication service utilities for handling token decoding and user information extraction, including functions to decode access tokens, extract user information from tokens, and build token data structures based on user information. This module provides a common interface for handling token-related operations in the database authentication service, allowing for consistent decoding of tokens and extraction of relevant user information such as permissions and group memberships while also supporting integration with external authentication providers when enabled.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import Optional

from models.access.auth_models import Role, TokenData
from services.auth.auth_ops import decode_token as decode_token_op


def build_token_data_for_user(service, user) -> TokenData:
    try:
        role = Role(user.role)
    except ValueError:
        role = Role.USER

    return TokenData(
        user_id=user.id,
        username=user.username,
        tenant_id=user.tenant_id,
        org_id=user.org_id,
        role=role,
        is_superuser=user.is_superuser,
        permissions=service.get_user_permissions(user),
        group_ids=[g.id for g in (getattr(user, "groups", None) or [])],
    )


def decode_token(service, token: str) -> Optional[TokenData]:
    local_token = decode_token_op(service, token)
    if local_token:
        return local_token

    if not service.is_external_auth_enabled():
        return None

    claims = service.oidc_service.verify_access_token(token)
    if not claims:
        return None

    user = service._sync_user_from_oidc_claims(claims)
    if not user or not user.is_active:
        return None

    token_data = build_token_data_for_user(service, user)

    known_permissions = {p["name"] for p in service.list_all_permissions()}
    oidc_perms = set(service._extract_permissions_from_oidc_claims(claims)) & known_permissions
    token_data.permissions = list(set(token_data.permissions) | oidc_perms)

    return token_data