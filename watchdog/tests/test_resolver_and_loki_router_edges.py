"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Permission, Role, TokenData
from models.observability.resolver_models import AnalyzeJobStatus, AnalyzeJobSummary, AnalyzeProxyPayload, AnalyzeRequestPayload
from models.observability.loki_models import LogDirection, LogFilterRequest, LogSearchRequest
from routers.observability import resolver_router, loki_router


def _request(path: str = "/") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
            "http_version": "1.1",
        }
    )


def _user() -> TokenData:
    return TokenData(
        user_id="u1",
        username="user",
        tenant_id="tenant",
        org_id="org",
        role=Role.ADMIN,
        permissions=[permission.value for permission in Permission],
        group_ids=["g1"],
        is_superuser=True,
    )


@pytest.mark.asyncio
async def test_loki_router_endpoints_and_timeout_wrapper(monkeypatch):
    current_user = _user()

    async def fake_resolve_tenant_id(_request, _user):
        return "tenant"

    monkeypatch.setattr(loki_router, "resolve_tenant_id", fake_resolve_tenant_id)

    async def fake_query_logs(log_query, tenant_id=None):
        return {"status": "success", "data": {"query": log_query.query, "tenant": tenant_id}}

    async def fake_query_logs_instant(query, time, tenant_id=None, limit=None):
        return {"status": "success", "data": {"query": query, "time": time, "tenant": tenant_id, "limit": limit}}

    async def fake_get_labels(start, end, tenant_id=None):
        return {"status": "success", "data": [str(start), str(end), tenant_id]}

    async def fake_get_label_values(label, start, end, query, tenant_id=None):
        return {"status": "success", "data": [label, str(start), str(end), query or "", tenant_id]}

    async def fake_search_logs_by_pattern(**kwargs):
        return {"status": "success", "data": kwargs}

    async def fake_filter_logs(**kwargs):
        return {"status": "success", "data": kwargs}

    async def fake_aggregate_logs(query, start, end, step, tenant_id=None):
        return {"query": query, "step": step, "tenant": tenant_id}

    async def fake_get_log_volume(query, start, end, step, tenant_id=None):
        return {"query": query, "step": step, "tenant": tenant_id}

    monkeypatch.setattr(loki_router.loki_service, "query_logs", fake_query_logs)
    monkeypatch.setattr(loki_router.loki_service, "query_logs_instant", fake_query_logs_instant)
    monkeypatch.setattr(loki_router.loki_service, "get_labels", fake_get_labels)
    monkeypatch.setattr(loki_router.loki_service, "get_label_values", fake_get_label_values)
    monkeypatch.setattr(loki_router.loki_service, "search_logs_by_pattern", fake_search_logs_by_pattern)
    monkeypatch.setattr(loki_router.loki_service, "filter_logs", fake_filter_logs)
    monkeypatch.setattr(loki_router.loki_service, "aggregate_logs", fake_aggregate_logs)
    monkeypatch.setattr(loki_router.loki_service, "get_log_volume", fake_get_log_volume)

    assert (await loki_router.query_logs(_request(), query="{app=\"api\"}", limit=5, start=1, end=2, direction=LogDirection.FORWARD, step=15, current_user=current_user))["data"]["tenant"] == "tenant"
    assert (await loki_router.query_logs_instant(_request(), query="rate", time=1, limit=2, current_user=current_user))["data"]["limit"] == 2
    assert (await loki_router.get_labels(_request(), start=1, end=2, current_user=current_user))["data"][2] == "tenant"
    assert (await loki_router.get_label_values(_request(), label="service", start=1, end=2, query="{job=\"api\"}", current_user=current_user))["data"][0] == "service"
    assert (await loki_router.search_logs(_request(), LogSearchRequest(pattern="error", labels={"job": "api"}, start=1, end=2, limit=5), current_user=current_user))["data"]["pattern"] == "error"
    assert (await loki_router.filter_logs(_request(), LogFilterRequest(labels={"job": "api"}, filters=["error"], start=1, end=2, limit=5), current_user=current_user))["data"]["filters"] == ["error"]
    assert (await loki_router.aggregate_logs(_request(), query="sum(rate())", start=1, end=2, step=60, current_user=current_user))["step"] == 60
    assert (await loki_router.get_log_volume(_request(), query="{job=\"api\"}", start=1, end=2, step=300, current_user=current_user))["tenant"] == "tenant"

    async def timeout_coro():
        raise asyncio.TimeoutError()

    with pytest.raises(HTTPException) as exc:
        await loki_router._handle_timeout(timeout_coro(), "timed out")
    assert exc.value.status_code == 504


@pytest.mark.asyncio
async def test_resolver_router_remaining_wrappers_and_helpers(monkeypatch):
    current_user = _user()
    calls = []

    async def fake_resolve_tenant_id(_request, _user):
        return "tenant"

    monkeypatch.setattr(resolver_router, "resolve_tenant_id", fake_resolve_tenant_id)
    monkeypatch.setattr(resolver_router, "correlation_id", lambda _request: "corr-1")
    monkeypatch.setattr(resolver_router, "inject_tenant", lambda payload, tenant_id: {**payload, "tenant_id": tenant_id})

    async def fake_request_json(**kwargs):
        calls.append(kwargs)
        path = kwargs["upstream_path"]
        if path == "/api/v1/jobs/analyze":
            return {
                "job_id": "job-1",
                "report_id": "rep-1",
                "status": "accepted",
                "created_at": "2024-01-01T00:00:00Z",
                "tenant_id": "tenant",
                "requested_by": "u1",
            }
        if path == "/api/v1/jobs":
            return {
                "items": [
                    {
                        "job_id": "job-1",
                        "report_id": "rep-1",
                        "status": "running",
                        "created_at": "2024-01-01T00:00:00Z",
                        "tenant_id": "tenant",
                        "requested_by": "u1",
                    }
                ],
                "next_cursor": "cursor-1",
            }
        if path == "/api/v1/jobs/job-1":
            return {
                "job_id": "job-1",
                "report_id": "rep-1",
                "status": "completed",
                "created_at": "2024-01-01T00:00:00Z",
                "tenant_id": "tenant",
                "requested_by": "u1",
            }
        return {"ok": True, "path": path, "params": kwargs.get("params")}

    monkeypatch.setattr(resolver_router.resolver_proxy_service, "request_json", fake_request_json)

    assert resolver_router._json_dict({"ok": True}) == {"ok": True}
    assert resolver_router._json_dict("x") == {}

    summary = AnalyzeJobSummary(
        job_id="job-1",
        report_id="rep-1",
        status=AnalyzeJobStatus.COMPLETED,
        created_at=datetime.fromisoformat("2024-01-01T00:00:00+00:00"),
        tenant_id="tenant",
        requested_by="u1",
    )
    result = resolver_router._job_result_response_from_summary(summary)
    assert result.result is None
    assert result.status == AnalyzeJobStatus.COMPLETED

    created = await resolver_router.create_analyze_job(
        _request("/api/resolver/analyze/jobs"),
        AnalyzeRequestPayload(start=1, end=2, services=["api"]),
        current_user,
    )
    assert created.job_id == "job-1"

    listed = await resolver_router.list_analyze_jobs(
        _request("/api/resolver/analyze/jobs"),
        status_filter=AnalyzeJobStatus.RUNNING,
        limit=10,
        cursor="next",
        current_user=current_user,
    )
    assert listed.next_cursor == "cursor-1"

    fetched = await resolver_router.get_analyze_job("job-1", _request(), current_user)
    assert fetched.status == AnalyzeJobStatus.COMPLETED

    payload = AnalyzeProxyPayload.model_validate({"service": "api"})
    wrappers = [
        (resolver_router.anomalies_log_patterns, "/api/v1/anomalies/logs/patterns"),
        (resolver_router.anomalies_log_bursts, "/api/v1/anomalies/logs/bursts"),
        (resolver_router.anomalies_traces, "/api/v1/anomalies/traces"),
        (resolver_router.correlate_signals, "/api/v1/correlate"),
        (resolver_router.topology_blast_radius, "/api/v1/topology/blast-radius"),
        (resolver_router.slo_burn, "/api/v1/slo/burn"),
        (resolver_router.forecast_trajectory, "/api/v1/forecast/trajectory"),
        (resolver_router.causal_granger, "/api/v1/causal/granger"),
        (resolver_router.causal_bayesian, "/api/v1/causal/bayesian"),
    ]
    for handler, path in wrappers:
        proxied = await handler(_request(path), payload, current_user)
        assert proxied["path"] == path

    assert (await resolver_router.ml_weights(_request("/api/resolver/ml/weights"), current_user))["path"] == "/api/v1/ml/weights"
    assert (await resolver_router.events_deployments(_request("/api/resolver/events/deployments"), current_user))["path"] == "/api/v1/events/deployments"

    async def fake_request_json_non_dict(**_kwargs):
        return SimpleNamespace()

    monkeypatch.setattr(resolver_router.resolver_proxy_service, "request_json", fake_request_json_non_dict)
    assert await resolver_router._proxy_post(
        request=_request(),
        current_user=current_user,
        upstream_path="/api/v1/test",
        payload={"raw": True},
        audit_action="audit.test",
    ) == {}