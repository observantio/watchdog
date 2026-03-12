"""
BeCertain proxy router and RCA analysis job endpoints for secure multi-tenant access to BeCertain features with comprehensive permission checks.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status

from config import config
from middleware.dependencies import require_permission_with_scope, resolve_tenant_id
from models.access.auth_models import Permission, TokenData
from models.observability.becertain_models import (
    AnalyzeConfigTemplateResponse,
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
from services.becertain_proxy_service import becertain_proxy_service
from services.aiops.helpers import inject_tenant, correlation_id
from custom_types.json import JSONDict

QueryParams = dict[str, str | int | float | bool]


def _json_dict(value: object) -> JSONDict:
    return value if isinstance(value, dict) else {}


def _job_result_response_from_summary(summary: AnalyzeJobSummary) -> AnalyzeJobResultResponse:
    return AnalyzeJobResultResponse(
        job_id=summary.job_id,
        report_id=summary.report_id,
        status=summary.status,
        tenant_id=summary.tenant_id,
        requested_by=summary.requested_by,
        result=None,
    )

router = APIRouter(prefix="/api/becertain", tags=["becertain"])


@router.get("/analyze/config-template", response_model=AnalyzeConfigTemplateResponse)
async def get_analyze_config_template(
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.CREATE_RCA, "becertain")),
) -> AnalyzeConfigTemplateResponse:
    tenant_id = await resolve_tenant_id(request, current_user)
    upstream = await becertain_proxy_service.request_json(
        method="GET",
        upstream_path="/api/v1/analyze/config-template",
        current_user=current_user,
        tenant_id=tenant_id,
        audit_action="becertain.analyze_job.template",
        correlation_id=correlation_id(request),
    )
    return AnalyzeConfigTemplateResponse.model_validate(_json_dict(upstream))

@router.post("/analyze/jobs", response_model=AnalyzeJobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_analyze_job(
    request: Request,
    payload: AnalyzeRequestPayload,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.CREATE_RCA, "becertain")),
) -> AnalyzeJobCreateResponse:
    tenant_id = await resolve_tenant_id(request, current_user)
    upstream = await becertain_proxy_service.request_json(
        method="POST",
        upstream_path="/api/v1/jobs/analyze",
        current_user=current_user,
        tenant_id=tenant_id,
        payload=inject_tenant(payload.model_dump(), tenant_id),
        audit_action="becertain.analyze_job.create",
        correlation_id=correlation_id(request),
    )
    return AnalyzeJobCreateResponse.model_validate(_json_dict(upstream))


@router.get("/analyze/jobs", response_model=AnalyzeJobListResponse)
async def list_analyze_jobs(
    request: Request,
    status_filter: Optional[AnalyzeJobStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: Optional[str] = Query(default=None),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
) -> AnalyzeJobListResponse:
    tenant_id = await resolve_tenant_id(request, current_user)
    params: QueryParams = {"limit": limit}
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
        correlation_id=correlation_id(request),
    )
    return AnalyzeJobListResponse.model_validate(_json_dict(upstream))


@router.get("/analyze/jobs/{job_id}", response_model=AnalyzeJobSummary)
async def get_analyze_job(
    job_id: str,
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
) -> AnalyzeJobSummary:
    tenant_id = await resolve_tenant_id(request, current_user)
    upstream = await becertain_proxy_service.request_json(
        method="GET",
        upstream_path=f"/api/v1/jobs/{job_id}",
        current_user=current_user,
        tenant_id=tenant_id,
        audit_action="becertain.analyze_job.get",
        correlation_id=correlation_id(request),
    )
    return AnalyzeJobSummary.model_validate(_json_dict(upstream))


@router.get("/analyze/jobs/{job_id}/result", response_model=AnalyzeJobResultResponse)
async def get_analyze_job_result(
    job_id: str,
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
) -> AnalyzeJobResultResponse:
    tenant_id = await resolve_tenant_id(request, current_user)
    corr_id = correlation_id(request)
    try:
        upstream = await becertain_proxy_service.request_json(
            method="GET",
            upstream_path=f"/api/v1/jobs/{job_id}/result",
            current_user=current_user,
            tenant_id=tenant_id,
            audit_action="becertain.analyze_job.result",
            correlation_id=corr_id,
        )
        return AnalyzeJobResultResponse.model_validate(_json_dict(upstream))
    except HTTPException as exc:
        if exc.status_code != status.HTTP_409_CONFLICT:
            raise
        # BeCertain can briefly return 409 for a just-completed job before the
        # result payload is committed. Surface the job summary instead of
        # failing the UI poll loop.
        upstream = await becertain_proxy_service.request_json(
            method="GET",
            upstream_path=f"/api/v1/jobs/{job_id}",
            current_user=current_user,
            tenant_id=tenant_id,
            audit_action="becertain.analyze_job.get",
            correlation_id=corr_id,
        )
        summary = AnalyzeJobSummary.model_validate(_json_dict(upstream))
        return _job_result_response_from_summary(summary)


@router.get("/reports/{report_id}", response_model=AnalyzeReportResponse)
async def get_report_by_id(
    report_id: str,
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
) -> AnalyzeReportResponse:
    tenant_id = await resolve_tenant_id(request, current_user)
    upstream = await becertain_proxy_service.request_json(
        method="GET",
        upstream_path=f"/api/v1/reports/{report_id}",
        current_user=current_user,
        tenant_id=tenant_id,
        audit_action="becertain.report.get",
        correlation_id=correlation_id(request),
    )
    return AnalyzeReportResponse.model_validate(_json_dict(upstream))


@router.delete("/reports/{report_id}", response_model=AnalyzeReportDeleteResponse)
async def delete_report_by_id(
    report_id: str,
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.DELETE_RCA, "becertain")),
) -> AnalyzeReportDeleteResponse:
    tenant_id = await resolve_tenant_id(request, current_user)
    upstream = await becertain_proxy_service.request_json(
        method="DELETE",
        upstream_path=f"/api/v1/reports/{report_id}",
        current_user=current_user,
        tenant_id=tenant_id,
        audit_action="becertain.report.delete",
        correlation_id=correlation_id(request),
    )
    return AnalyzeReportDeleteResponse.model_validate(_json_dict(upstream))


async def _proxy_post(
    *,
    request: Request,
    current_user: TokenData,
    upstream_path: str,
    payload: AnalyzeProxyPayload | JSONDict,
    audit_action: str,
) -> JSONDict:
    tenant_id = await resolve_tenant_id(request, current_user)
    payload_data = (
        payload.model_dump(exclude_none=True)
        if isinstance(payload, AnalyzeProxyPayload)
        else dict(payload)
    )
    result = await becertain_proxy_service.request_json(
        method="POST",
        upstream_path=upstream_path,
        current_user=current_user,
        tenant_id=tenant_id,
        payload=inject_tenant(payload_data, tenant_id),
        audit_action=audit_action,
        correlation_id=correlation_id(request),
    )
    return result if isinstance(result, dict) else {}


@router.post("/anomalies/metrics")
async def anomalies_metrics(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
) -> JSONDict:
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/anomalies/metrics", payload=payload, audit_action="becertain.proxy.metrics")


@router.post("/anomalies/logs/patterns")
async def anomalies_log_patterns(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
) -> JSONDict:
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/anomalies/logs/patterns", payload=payload, audit_action="becertain.proxy.logs.patterns")


@router.post("/anomalies/logs/bursts")
async def anomalies_log_bursts(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
) -> JSONDict:
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/anomalies/logs/bursts", payload=payload, audit_action="becertain.proxy.logs.bursts")


@router.post("/anomalies/traces")
async def anomalies_traces(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
) -> JSONDict:
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/anomalies/traces", payload=payload, audit_action="becertain.proxy.traces")


@router.post("/correlate")
async def correlate_signals(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
) -> JSONDict:
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/correlate", payload=payload, audit_action="becertain.proxy.correlate")


@router.post("/topology/blast-radius")
async def topology_blast_radius(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
) -> JSONDict:
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/topology/blast-radius", payload=payload, audit_action="becertain.proxy.topology")


@router.post("/slo/burn")
async def slo_burn(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
) -> JSONDict:
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/slo/burn", payload=payload, audit_action="becertain.proxy.slo")


@router.post("/forecast/trajectory")
async def forecast_trajectory(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
) -> JSONDict:
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/forecast/trajectory", payload=payload, audit_action="becertain.proxy.forecast")


@router.post("/causal/granger")
async def causal_granger(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
) -> JSONDict:
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/causal/granger", payload=payload, audit_action="becertain.proxy.causal.granger")


@router.post("/causal/bayesian")
async def causal_bayesian(
    request: Request,
    payload: AnalyzeProxyPayload = Body(default_factory=AnalyzeProxyPayload),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
) -> JSONDict:
    return await _proxy_post(request=request, current_user=current_user, upstream_path="/api/v1/causal/bayesian", payload=payload, audit_action="becertain.proxy.causal.bayesian")


@router.get("/ml/weights")
async def ml_weights(
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
) -> JSONDict:
    tenant_id = await resolve_tenant_id(request, current_user)
    result = await becertain_proxy_service.request_json(
        method="GET",
        upstream_path="/api/v1/ml/weights",
        current_user=current_user,
        tenant_id=tenant_id,
        params={"tenant_id": tenant_id},
        audit_action="becertain.proxy.ml.weights",
        correlation_id=correlation_id(request),
        cache_ttl_seconds=getattr(config, "BECERTAIN_PROXY_CACHE_TTL_SECONDS", 15),
    )
    return result if isinstance(result, dict) else {}


@router.post("/ml/weights/feedback")
async def ml_weights_feedback(
    request: Request,
    signal: str = Query(..., min_length=1),
    was_correct: bool = Query(...),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.CREATE_RCA, "becertain")),
) -> JSONDict:
    tenant_id = await resolve_tenant_id(request, current_user)
    result = await becertain_proxy_service.request_json(
        method="POST",
        upstream_path="/api/v1/ml/weights/feedback",
        current_user=current_user,
        tenant_id=tenant_id,
        params={
            "tenant_id": tenant_id,
            "signal": signal,
            "was_correct": str(bool(was_correct)).lower(),
        },
        audit_action="becertain.proxy.ml.weights.feedback",
        correlation_id=correlation_id(request),
    )
    return result if isinstance(result, dict) else {}


@router.post("/ml/weights/reset")
async def ml_weights_reset(
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.DELETE_RCA, "becertain")),
) -> JSONDict:
    tenant_id = await resolve_tenant_id(request, current_user)
    result = await becertain_proxy_service.request_json(
        method="POST",
        upstream_path="/api/v1/ml/weights/reset",
        current_user=current_user,
        tenant_id=tenant_id,
        params={"tenant_id": tenant_id},
        audit_action="becertain.proxy.ml.weights.reset",
        correlation_id=correlation_id(request),
    )
    return result if isinstance(result, dict) else {}


@router.get("/events/deployments")
async def events_deployments(
    request: Request,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RCA, "becertain")),
) -> JSONDict:
    tenant_id = await resolve_tenant_id(request, current_user)
    result = await becertain_proxy_service.request_json(
        method="GET",
        upstream_path="/api/v1/events/deployments",
        current_user=current_user,
        tenant_id=tenant_id,
        params={"tenant_id": tenant_id},
        audit_action="becertain.proxy.events.deployments",
        correlation_id=correlation_id(request),
        cache_ttl_seconds=getattr(config, "BECERTAIN_PROXY_CACHE_TTL_SECONDS", 15),
    )
    return result if isinstance(result, dict) else {}
