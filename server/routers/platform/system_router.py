"""
Router for system-level operations such as retrieving system metrics, health status, and performing maintenance tasks.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
import logging

from services.system_service import SystemService
from models.access.auth_models import Permission, TokenData
from middleware.dependencies import require_permission_with_scope
from middleware.error_handlers import handle_route_errors

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])
system_service = SystemService()


@router.get("/metrics", response_model=Dict[str, Any])
@handle_route_errors(internal_detail="Failed to retrieve system metrics")
async def get_system_metrics(
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_AGENTS, "system"))
) -> Dict[str, Any]:
    return system_service.get_all_metrics()
