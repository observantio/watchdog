"""
Router for Tempo trace querying, trace retrieval by ID, and service/operation listing
with multi-tenant access control and query validation.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, List, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status

from config import config
from middleware.dependencies import require_permission_with_scope, resolve_tenant_id
from models.access.auth_models import Permission, TokenData
from models.observability.tempo_models import Trace, TraceQuery, TraceResponse
from services.tempo_service import TempoService

tempo_service = TempoService()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await tempo_service.aclose()


router = APIRouter(prefix="/api/tempo", tags=["tempo"])


@router.get("/traces/search", response_model=TraceResponse)
async def search_traces(
    request: Request,
    service: Optional[str] = Query(None),
    operation: Optional[str] = Query(None),
    min_duration: Optional[str] = Query(None, alias="minDuration"),
    max_duration: Optional[str] = Query(None, alias="maxDuration"),
    start: Optional[int] = Query(None, description="Start time in microseconds"),
    end: Optional[int] = Query(None, description="End time in microseconds"),
    limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT),
    fetch_full: bool = Query(False, alias="fetchFull"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_TRACES, "tempo")),
) -> TraceResponse:
    query = TraceQuery(
        service=service,
        operation=operation,
        minDuration=min_duration,
        maxDuration=max_duration,
        start=start,
        end=end,
        limit=limit,
    )
    tenant_id = await resolve_tenant_id(request, current_user)
    return await tempo_service.search_traces(query, tenant_id=tenant_id, fetch_full_traces=fetch_full)


@router.get("/traces/{trace_id}", response_model=Trace)
async def get_trace(
    trace_id: str,
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_TRACES, "tempo")),
) -> Trace:
    tenant_id = await resolve_tenant_id(request, current_user)
    trace = await tempo_service.get_trace(trace_id, tenant_id=tenant_id)
    if not trace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Trace {trace_id} not found")
    return trace


@router.get("/services", response_model=List[str])
async def get_services(
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_TRACES, "tempo")),
) -> List[str]:
    tenant_id = await resolve_tenant_id(request, current_user)
    return await tempo_service.get_services(tenant_id=tenant_id)


@router.get("/services/{service}/operations", response_model=List[str])
async def get_operations(
    service: str,
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_TRACES, "tempo")),
) -> List[str]:
    tenant_id = await resolve_tenant_id(request, current_user)
    return await tempo_service.get_operations(service, tenant_id=tenant_id)