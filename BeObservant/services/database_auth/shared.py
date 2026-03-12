"""
Shared helper functions for database authentication service.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from models.access.auth_models import Role
from custom_types.json import JSONValue

if TYPE_CHECKING:
    from db_models import User
    from services.database_auth_service import DatabaseAuthService

def sync_active_user_from_claims(
    service: DatabaseAuthService,
    claims: Optional[dict[str, JSONValue]],
) -> User | None:
    if not claims:
        return None

    user = service._sync_user_from_oidc_claims(claims)
    if not user or not getattr(user, "is_active", False):
        return None
    return user


def safe_role(raw_role: Optional[str]) -> Role:
    try:
        return Role(raw_role)
    except (TypeError, ValueError):
        return Role.USER
