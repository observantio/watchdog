"""
BeCertain proxy router and RCA analysis job endpoints.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query, Request, status

from config import config
from middleware.dependencies import require_permission_with_scope, resolve_tenant_id
from models.access.auth_models import Permission, TokenData
from models.observability.becertain_models import (
    AnalyzeJobCreateResponse,
    AnalyzeJobListResponse,
    AnalyzeJobResultResponse,
    AnalyzeReportDeleteResponse,
    AnalyzeReportResponse,
    AnalyzeJobStatus,
    AnalyzeJobSummary,
    AnalyzeRequestPayload,
    AnalyzeProxyPayload,
)
from services.becertain_proxy_service import BeCertainProxyService

router = APIRouter(prefix="/api/becertain", tags=["becertain"])

becertain_proxy_service = BeCertainProxyService()

def _inject_tenant(payload: Optional[Dict[str, Any]], tenant_id: str) -> Dict[str, Any]:
    data: Dict[str, Any] = dict(payload or {})
    data["tenant_id"] = tenant_id
    return data


def _correlation_id(request: Request) -> Optional[str]:
    return request.headers.get("x-correlation-id") or request.headers.get("X-Correlation-ID")


@router.post("/analyze/jobs", response_model=AnalyzeJobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_analyze_job(
    request: Request,
    payload: AnalyzeRequestPayload,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.CREATE_RCA, "becertain")),
):
    tenant_id = await resolve_tenant_id(request, current_user)
    upstream = await becertain_proxy_service.request_json(
        method="POST",
        upstream_path="/api/v1/jobs/analyze",
        current_user=current_user,
        tenant_id=tenant_id,
        payload=_inject_tenant(payload.model_dump(), tenant_id),
        audit_action="becertain.analyze_job.create",
        correlation_id=_correlation_id(request),
    )
    return AnalyzeJobCreateResponse(**upstream)


@router.get("/analyze/jobs", response_model=AnalyzeJobListResponse)
async def list_analyze_jobs(
    request: Request,
    status_filter: Optional[AnalyzeJobStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: Optional[str] = Query(default=None),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    tenant_id = await resolve_tenant_id(request, current_user)
    params: Dict[str, Any] = {"limit": limit}
    if status_filter:
        params["status"] = status_filter.value
    if cursor:
        params["cursor"] = cursor
    upstream = await becertain_proxy_service.request_json(
        method="GET",
        upstream_path="/api/v1/jobs",
        current_user=current_user,
        tenant_id=tenant_id,
        params=params,
        audit_action="becertain.analyze_job.list",
        correlation_id=_correlation_id(request),
    )
    return AnalyzeJobListResponse(**upstream)


@router.get("/analyze/jobs/{job_id}", response_model=AnalyzeJobSummary)
async def get_analyze_job(
    job_id: str,
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    tenant_id = await resolve_tenant_id(request, current_user)
    upstream = await becertain_proxy_service.request_json(
        method="GET",
        upstream_path=f"/api/v1/jobs/{job_id}",
        current_user=current_user,
        tenant_id=tenant_id,
        audit_action="becertain.analyze_job.get",
        correlation_id=_correlation_id(request),
    )
    return AnalyzeJobSummary(**upstream)


@router.get("/analyze/jobs/{job_id}/result", response_model=AnalyzeJobResultResponse)
async def get_analyze_job_result(
    job_id: str,
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    tenant_id = await resolve_tenant_id(request, current_user)
    upstream = await becertain_proxy_service.request_json(
        method="GET",
        upstream_path=f"/api/v1/jobs/{job_id}/result",
        current_user=current_user,
        tenant_id=tenant_id,
        audit_action="becertain.analyze_job.result",
        correlation_id=_correlation_id(request),
    )
    return AnalyzeJobResultResponse(**upstream)


@router.get("/reports/{report_id}", response_model=AnalyzeReportResponse)
async def get_report_by_id(
    report_id: str,
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    tenant_id = await resolve_tenant_id(request, current_user)
    upstream = await becertain_proxy_service.request_json(
        method="GET",
        upstream_path=f"/api/v1/reports/{report_id}",
        current_user=current_user,
        tenant_id=tenant_id,
        audit_action="becertain.report.get",
        correlation_id=_correlation_id(request),
    )
    return AnalyzeReportResponse(**upstream)


@router.delete("/reports/{report_id}", response_model=AnalyzeReportDeleteResponse)
async def delete_report_by_id(
    report_id: str,
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.DELETE_RCA, "becertain")),
):
    tenant_id = await resolve_tenant_id(request, current_user)
    upstream = await becertain_proxy_service.request_json(
        method="DELETE",
        upstream_path=f"/api/v1/reports/{report_id}",
        current_user=current_user,
        tenant_id=tenant_id,
        audit_action="becertain.report.delete",
        correlation_id=_correlation_id(request),
    )
    return AnalyzeReportDeleteResponse(**upstream)


async def _proxy_post(
    *,
    request: Request,
    current_user: TokenData,
    upstream_path: str,
    payload: AnalyzeProxyPayload | Dict[str, Any],
    audit_action: str,
):
    tenant_id = await resolve_tenant_id(request, current_user)
    payload_data = (
        payload.model_dump(exclude_none=True)
        if isinstance(payload, AnalyzeProxyPayload)
        else dict(payload)
    )
    return await becertain_proxy_service.request_json(
        method="POST",
        upstream_path=upstream_path,
        current_user=current_user,
        tenant_id=tenant_id,
        payload=_inject_tenant(payload_data, tenant_id),
        audit_action=audit_action,
        correlation_id=_correlation_id(request),
    )


@router.post("/anomalies/metrics")
async def anomalies_metrics(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/anomalies/metrics", payload=payload, audit_action="becertain.proxy.metrics")


@router.post("/anomalies/logs/patterns")
async def anomalies_log_patterns(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/anomalies/logs/patterns", payload=payload, audit_action="becertain.proxy.logs.patterns")


@router.post("/anomalies/logs/bursts")
async def anomalies_log_bursts(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/anomalies/logs/bursts", payload=payload, audit_action="becertain.proxy.logs.bursts")


@router.post("/anomalies/traces")
async def anomalies_traces(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/anomalies/traces", payload=payload, audit_action="becertain.proxy.traces")


@router.post("/correlate")
async def correlate_signals(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/correlate", payload=payload, audit_action="becertain.proxy.correlate")


@router.post("/topology/blast-radius")
async def topology_blast_radius(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/topology/blast-radius", payload=payload, audit_action="becertain.proxy.topology")


@router.post("/slo/burn")
async def slo_burn(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/slo/burn", payload=payload, audit_action="becertain.proxy.slo")


@router.post("/forecast/trajectory")
async def forecast_trajectory(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/forecast/trajectory", payload=payload, audit_action="becertain.proxy.forecast")


@router.post("/causal/granger")
async def causal_granger(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/causal/granger", payload=payload, audit_action="becertain.proxy.causal.granger")


@router.post("/causal/bayesian")
async def causal_bayesian(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/causal/bayesian", payload=payload, audit_action="becertain.proxy.causal.bayesian")


@router.get("/ml/weights")
async def ml_weights(
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    tenant_id = await resolve_tenant_id(request, current_user)
    return await becertain_proxy_service.request_json(
        method="GET",
        upstream_path="/api/v1/ml/weights",
        current_user=current_user,
        tenant_id=tenant_id,
        params={"tenant_id": tenant_id},
        audit_action="becertain.proxy.ml.weights",
        correlation_id=_correlation_id(request),
        cache_ttl_seconds=getattr(config, "BECERTAIN_PROXY_CACHE_TTL_SECONDS", 15),
    )


@router.get("/events/deployments")
async def events_deployments(
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    tenant_id = await resolve_tenant_id(request, current_user)
    return await becertain_proxy_service.request_json(
        method="GET",
        upstream_path="/api/v1/events/deployments",
        current_user=current_user,
        tenant_id=tenant_id,
        params={"tenant_id": tenant_id},
        audit_action="becertain.proxy.events.deployments",
        correlation_id=_correlation_id(request),
        cache_ttl_seconds=getattr(config, "BECERTAIN_PROXY_CACHE_TTL_SECONDS", 15),
    )
