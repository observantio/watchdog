"""
Router for system-level operations such as retrieving system metrics, health status, and performing maintenance tasks.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.system_service import SystemService
from models.access.auth_models import Permission, TokenData
from models.access.quota_models import QuotasResponse
from middleware.dependencies import auth_service, require_permission_with_scope
from middleware.error_handlers import handle_route_errors
from custom_types.json import JSONDict
from services.quota_service import quota_service

router = APIRouter(prefix="/api/system", tags=["system"])
system_service = SystemService()


@router.get("/metrics", response_model=JSONDict)
@handle_route_errors(internal_detail="Failed to retrieve system metrics")
async def get_system_metrics(
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_AGENTS, "system"))
) -> JSONDict:
    return system_service.get_all_metrics()


@router.get("/quotas", response_model=QuotasResponse)
@handle_route_errors(internal_detail="Failed to retrieve system quotas")
async def get_system_quotas(
    org_id: Optional[str] = Query(default=None, alias="orgId"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_AGENTS, "system"))
) -> QuotasResponse:
    requested_org = org_id if isinstance(org_id, str) else None
    selected_org = str(requested_org or current_user.org_id or "").strip()
    if not selected_org:
        selected_org = str(current_user.tenant_id)

    if requested_org:
        visible_keys = auth_service.list_api_keys(current_user.user_id, show_hidden=False)
        allowed_org_ids = {
            str(getattr(k, "key", "") or "")
            for k in visible_keys
            if (not bool(getattr(k, "is_shared", False)) or bool(getattr(k, "can_use", False)))
        }
        if selected_org not in allowed_org_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized for requested API key scope",
            )

    return await quota_service.get_quotas(current_user, tenant_scope=selected_org)
