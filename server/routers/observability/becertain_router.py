"""BeCertain proxy router and RCA analysis job endpoints."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query, Request, status

from middleware.dependencies import require_permission_with_scope, resolve_tenant_id
from models.access.auth_models import Permission, TokenData
from models.observability.becertain_models import (
    AnalyzeJobCreateResponse,
    AnalyzeJobListResponse,
    AnalyzeJobResultResponse,
    AnalyzeJobStatus,
    AnalyzeJobSummary,
    AnalyzeRequestPayload,
)
from services.becertain_job_service import becertain_analyze_job_service
from services.becertain_proxy_service import becertain_proxy_service

router = APIRouter(prefix="/api/becertain", tags=["becertain"])


def _inject_tenant(payload: Optional[Dict[str, Any]], tenant_id: str) -> Dict[str, Any]:
    data: Dict[str, Any] = dict(payload or {})
    data["tenant_id"] = tenant_id
    return data


def _job_summary(job) -> AnalyzeJobSummary:
    return AnalyzeJobSummary(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        duration_ms=job.duration_ms,
        error=job.error,
        summary_preview=job.summary_preview,
        tenant_id=job.tenant_id,
        requested_by=job.requested_by,
    )


@router.post("/analyze/jobs", response_model=AnalyzeJobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_analyze_job(
    request: Request,
    payload: AnalyzeRequestPayload,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.CREATE_RCA, "becertain")),
):
    tenant_id = resolve_tenant_id(request, current_user)
    job = await becertain_analyze_job_service.create_job(
        current_user=current_user,
        tenant_id=tenant_id,
        payload=payload,
    )
    return AnalyzeJobCreateResponse(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at,
        tenant_id=job.tenant_id,
        requested_by=job.requested_by,
    )


@router.get("/analyze/jobs", response_model=AnalyzeJobListResponse)
async def list_analyze_jobs(
    request: Request,
    status_filter: Optional[AnalyzeJobStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: Optional[str] = Query(default=None),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    tenant_id = resolve_tenant_id(request, current_user)
    jobs, next_cursor = await becertain_analyze_job_service.list_jobs(
        user_id=current_user.user_id,
        tenant_id=tenant_id,
        status_filter=status_filter,
        limit=limit,
        cursor=cursor,
    )
    return AnalyzeJobListResponse(items=[_job_summary(j) for j in jobs], next_cursor=next_cursor)


@router.get("/analyze/jobs/{job_id}", response_model=AnalyzeJobSummary)
async def get_analyze_job(
    job_id: str,
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    tenant_id = resolve_tenant_id(request, current_user)
    job = await becertain_analyze_job_service.get_job(job_id=job_id, user_id=current_user.user_id, tenant_id=tenant_id)
    return _job_summary(job)


@router.get("/analyze/jobs/{job_id}/result", response_model=AnalyzeJobResultResponse)
async def get_analyze_job_result(
    job_id: str,
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    tenant_id = resolve_tenant_id(request, current_user)
    job = await becertain_analyze_job_service.get_job(job_id=job_id, user_id=current_user.user_id, tenant_id=tenant_id)
    result = await becertain_analyze_job_service.get_job_result(
        job_id=job_id,
        user_id=current_user.user_id,
        tenant_id=tenant_id,
    )
    return AnalyzeJobResultResponse(job_id=job.job_id, status=job.status, result=result)


async def _proxy_post(
    *,
    request: Request,
    current_user: TokenData,
    upstream_path: str,
    payload: Dict[str, Any],
    audit_action: str,
):
    tenant_id = resolve_tenant_id(request, current_user)
    return await becertain_proxy_service.request_json(
        method="POST",
        upstream_path=upstream_path,
        current_user=current_user,
        tenant_id=tenant_id,
        payload=_inject_tenant(payload, tenant_id),
        audit_action=audit_action,
    )


@router.post("/anomalies/metrics")
async def anomalies_metrics(
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/anomalies/metrics", payload=payload, audit_action="becertain.proxy.metrics")


@router.post("/anomalies/logs/patterns")
async def anomalies_log_patterns(
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/anomalies/logs/patterns", payload=payload, audit_action="becertain.proxy.logs.patterns")


@router.post("/anomalies/logs/bursts")
async def anomalies_log_bursts(
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/anomalies/logs/bursts", payload=payload, audit_action="becertain.proxy.logs.bursts")


@router.post("/anomalies/traces")
async def anomalies_traces(
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/anomalies/traces", payload=payload, audit_action="becertain.proxy.traces")


@router.post("/correlate")
async def correlate_signals(
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/correlate", payload=payload, audit_action="becertain.proxy.correlate")


@router.post("/topology/blast-radius")
async def topology_blast_radius(
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/topology/blast-radius", payload=payload, audit_action="becertain.proxy.topology")


@router.post("/slo/burn")
async def slo_burn(
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/slo/burn", payload=payload, audit_action="becertain.proxy.slo")


@router.post("/forecast/trajectory")
async def forecast_trajectory(
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/forecast/trajectory", payload=payload, audit_action="becertain.proxy.forecast")


@router.post("/causal/granger")
async def causal_granger(
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/causal/granger", payload=payload, audit_action="becertain.proxy.causal.granger")


@router.post("/causal/bayesian")
async def causal_bayesian(
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/causal/bayesian", payload=payload, audit_action="becertain.proxy.causal.bayesian")


@router.get("/ml/weights")
async def ml_weights(
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    tenant_id = resolve_tenant_id(request, current_user)
    return await becertain_proxy_service.request_json(
        method="GET",
        upstream_path="/api/v1/ml/weights",
        current_user=current_user,
        tenant_id=tenant_id,
        params={"tenant_id": tenant_id},
        audit_action="becertain.proxy.ml.weights",
    )


@router.get("/events/deployments")
async def events_deployments(
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
):
    tenant_id = resolve_tenant_id(request, current_user)
    return await becertain_proxy_service.request_json(
        method="GET",
        upstream_path="/api/v1/events/deployments",
        current_user=current_user,
        tenant_id=tenant_id,
        params={"tenant_id": tenant_id},
        audit_action="becertain.proxy.events.deployments",
    )
