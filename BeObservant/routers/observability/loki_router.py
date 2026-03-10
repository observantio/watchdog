"""
Router for Loki log querying, label exploration, and log searching/filtering with multi-tenant access control and query validation.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
import asyncio
from typing import Awaitable, Optional, TypeVar

from fastapi import APIRouter, Query, Body, Depends, Request, HTTPException, status
from custom_types.json import JSONDict
from models.observability.loki_models import (
    LogQuery, LogResponse, LogLabelsResponse,
    LogLabelValuesResponse, LogDirection, LogFilterRequest, LogSearchRequest
)
from services.loki_service import LokiService
from config import config
from models.access.auth_models import Permission, TokenData
from middleware.dependencies import resolve_tenant_id, require_permission_with_scope

START_TIME_DESC = "Start time in nanoseconds"
END_TIME_DESC = "End time in nanoseconds"

router = APIRouter(prefix="/api/loki", tags=["loki"])

loki_service = LokiService()

ResponseT = TypeVar("ResponseT")


async def _handle_timeout(coro: Awaitable[ResponseT], detail: str) -> ResponseT:
    try:
        return await coro
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=detail,
        ) from exc

@router.get("/query", response_model=LogResponse)
async def query_logs(
    request: Request,
    query: str = Query(..., description="LogQL query string"),
    limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT, description="Maximum log lines to return"),
    start: Optional[int] = Query(None, description=START_TIME_DESC),
    end: Optional[int] = Query(None, description=END_TIME_DESC),
    direction: LogDirection = Query(LogDirection.BACKWARD, description="Query direction"),
    step: Optional[int] = Query(None, description="Query resolution step in seconds"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_LOGS, "loki"))
) -> LogResponse:
    log_query = LogQuery(
        query=query,
        limit=limit,
        start=start,
        end=end,
        direction=direction,
        step=step
    )
    tenant_id =  await resolve_tenant_id(request, current_user)
    return await _handle_timeout(
        loki_service.query_logs(log_query, tenant_id=tenant_id),
        "Loki query timed out",
    )


@router.get("/query_instant", response_model=LogResponse)
async def query_logs_instant(
    request: Request,
    query: str = Query(..., description="LogQL query string"),
    time: Optional[int] = Query(None, description="Query time in nanoseconds"),
    limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT, description="Maximum log lines to return"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_LOGS, "loki"))
) -> LogResponse:
    tenant_id = await resolve_tenant_id(request, current_user)
    return await _handle_timeout(
        loki_service.query_logs_instant(query, time, tenant_id=tenant_id, limit=limit),
        "Loki instant query timed out",
    )


@router.get("/labels", response_model=LogLabelsResponse)
async def get_labels(
    request: Request,
    start: Optional[int] = Query(None, description=START_TIME_DESC),
    end: Optional[int] = Query(None, description=END_TIME_DESC),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_LOGS, "loki"))
) -> LogLabelsResponse:
    tenant_id = await resolve_tenant_id(request, current_user)
    return await _handle_timeout(
        loki_service.get_labels(start, end, tenant_id=tenant_id),
        "Loki labels lookup timed out",
    )


@router.get("/label/{label}/values", response_model=LogLabelValuesResponse)
async def get_label_values(
    request: Request,
    label: str,
    start: Optional[int] = Query(None, description=START_TIME_DESC),
    end: Optional[int] = Query(None, description=END_TIME_DESC),
    query: Optional[str] = Query(None, description="Optional LogQL query filter"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_LOGS, "loki"))
) -> LogLabelValuesResponse:
    tenant_id = await resolve_tenant_id(request, current_user)
    return await _handle_timeout(
        loki_service.get_label_values(label, start, end, query, tenant_id=tenant_id),
        f"Loki label values lookup timed out for {label}",
    )


@router.post("/search")
async def search_logs(
    request: Request,
    payload: LogSearchRequest = Body(..., description="Log search request"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_LOGS, "loki"))
) -> LogResponse:
    tenant_id = await resolve_tenant_id(request, current_user)
    return await _handle_timeout(
        loki_service.search_logs_by_pattern(
            pattern=payload.pattern,
            labels=payload.labels or {},
            start=payload.start,
            end=payload.end,
            limit=payload.limit,
            tenant_id=tenant_id
        ),
        "Loki search timed out",
    )


@router.post("/filter")
async def filter_logs(
    request: Request,
    payload: LogFilterRequest = Body(..., description="Log filtering request"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_LOGS, "loki"))
) -> LogResponse:
    tenant_id = await resolve_tenant_id(request, current_user)
    return await _handle_timeout(
        loki_service.filter_logs(
            labels=payload.labels or {},
            filters=payload.filters,
            start=payload.start,
            end=payload.end,
            limit=payload.limit,
            tenant_id=tenant_id
        ),
        "Loki filter query timed out",
    )


@router.get("/aggregate")
async def aggregate_logs(
    request: Request,
    query: str = Query(..., description="LogQL aggregation query"),
    start: Optional[int] = Query(None, description=START_TIME_DESC),
    end: Optional[int] = Query(None, description=END_TIME_DESC),
    step: int = Query(60, ge=1, description="Query resolution step in seconds"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_LOGS, "loki"))
) -> JSONDict:
    tenant_id = await resolve_tenant_id(request, current_user)
    return await _handle_timeout(
        loki_service.aggregate_logs(query, start, end, step, tenant_id=tenant_id),
        "Loki aggregation timed out",
    )


@router.get("/volume")
async def get_log_volume(
    request: Request,
    query: str = Query(..., description="LogQL selector query"),
    start: Optional[int] = Query(None, description=START_TIME_DESC),
    end: Optional[int] = Query(None, description=END_TIME_DESC),
    step: int = Query(300, ge=1, description="Time step in seconds"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_LOGS, "loki"))
) -> JSONDict:
    tenant_id = await resolve_tenant_id(request, current_user)
    return await _handle_timeout(
        loki_service.get_log_volume(query, start, end, step, tenant_id=tenant_id),
        "Loki volume query timed out",
    )
