"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.responses import JSONResponse

import main as main_module
from routers import internal_router
from routers.observability import agents_router, alertmanager_router, becertain_router, loki_router, tempo_router
from routers.platform import system_router

from .helpers import WorkflowState, patch_auth_service


def test_root_health_ready_system_and_internal_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)

    monkeypatch.setattr(main_module, "connection_test", lambda: True)

    async def fake_upstream_reachable(_url: str) -> bool:
        return True

    monkeypatch.setattr(main_module, "_upstream_reachable", fake_upstream_reachable)
    monkeypatch.setattr(system_router.system_service, "get_all_metrics", lambda: {"uptime": 123, "agents": 2})
    monkeypatch.setattr(internal_router.internal_service, "_get_internal_token", lambda: "internal-token")
    monkeypatch.setattr(internal_router.internal_service._auth_service, "validate_otlp_token", state.validate_otlp_token)

    api_key = state.create_api_key("u-admin", state.tenant_id, SimpleNamespace(name="gateway", key="scope-gateway"))

    root_response = client.get("/")
    assert root_response.status_code == 200
    assert root_response.json()["service"]

    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["status"] == "Healthy"

    ready_response = client.get("/ready")
    assert ready_response.status_code == 200
    assert ready_response.json()["status"] == "ready"

    system_response = client.get("/api/system/metrics", headers=state.auth_header("token-u-admin"))
    assert system_response.status_code == 200
    assert system_response.json()["uptime"] == 123

    internal_get_response = client.get(
        "/api/internal/otlp/validate",
        params={"token": api_key.otlp_token},
        headers={"X-Internal-Token": "internal-token"},
    )
    assert internal_get_response.status_code == 410

    internal_post_response = client.post(
        "/api/internal/otlp/validate",
        headers={"X-Internal-Token": "internal-token"},
        json={"token": api_key.otlp_token},
    )
    assert internal_post_response.status_code == 200
    assert internal_post_response.json() == {"org_id": "scope-gateway"}


def test_tempo_and_loki_advanced_filter_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)

    tempo_calls: list[dict[str, Any]] = []
    loki_calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_search_traces(query: Any, tenant_id: str | None = None, fetch_full_traces: bool = False) -> dict[str, Any]:
        tempo_calls.append({
            "service": query.service,
            "operation": query.operation,
            "min": query.min_duration,
            "max": query.max_duration,
            "start": query.start,
            "end": query.end,
            "limit": query.limit,
            "tenant_id": tenant_id,
            "fetch_full": fetch_full_traces,
        })
        return {
            "data": [{"traceID": "trace-1", "spans": [{"spanID": "span-1", "traceID": "trace-1", "operationName": "GET /cart", "startTime": 1, "duration": 20, "tags": [], "serviceName": query.service or "cart"}]}],
            "total": 1,
            "limit": query.limit,
            "offset": 0,
        }

    async def fake_get_trace(trace_id: str, tenant_id: str | None = None) -> dict[str, Any]:
        tempo_calls.append({"trace_id": trace_id, "tenant_id": tenant_id})
        return {"traceID": trace_id, "spans": [{"spanID": "span-1", "traceID": trace_id, "operationName": "GET /cart", "startTime": 1, "duration": 20, "tags": [], "serviceName": "cart"}]}

    async def fake_get_services(tenant_id: str | None = None) -> list[str]:
        tempo_calls.append({"services": True, "tenant_id": tenant_id})
        return ["cart", "checkout"]

    async def fake_get_operations(service: str, tenant_id: str | None = None) -> list[str]:
        tempo_calls.append({"operations_for": service, "tenant_id": tenant_id})
        return ["GET /cart", "POST /cart"]

    async def fake_query_logs(log_query: Any, tenant_id: str | None = None) -> dict[str, Any]:
        loki_calls.append(("query", {"query": log_query.query, "start": log_query.start, "end": log_query.end, "direction": log_query.direction.value, "step": log_query.step, "tenant_id": tenant_id}))
        return {"status": "success", "data": {"result": []}}

    async def fake_query_logs_instant(query: str, time: int | None, tenant_id: str | None = None, limit: int | None = None) -> dict[str, Any]:
        loki_calls.append(("query_instant", {"query": query, "time": time, "tenant_id": tenant_id, "limit": limit}))
        return {"status": "success", "data": {"result": []}}

    async def fake_get_labels(start: int | None, end: int | None, tenant_id: str | None = None) -> dict[str, Any]:
        loki_calls.append(("labels", {"start": start, "end": end, "tenant_id": tenant_id}))
        return {"status": "success", "data": ["service", "level"]}

    async def fake_get_label_values(label: str, start: int | None, end: int | None, query: str | None, tenant_id: str | None = None) -> dict[str, Any]:
        loki_calls.append(("label_values", {"label": label, "start": start, "end": end, "query": query, "tenant_id": tenant_id}))
        return {"status": "success", "data": ["checkout"]}

    async def fake_search_logs_by_pattern(**kwargs: Any) -> dict[str, Any]:
        loki_calls.append(("search", kwargs))
        return {"status": "success", "data": {"result": []}}

    async def fake_filter_logs(**kwargs: Any) -> dict[str, Any]:
        loki_calls.append(("filter", kwargs))
        return {"status": "success", "data": {"result": []}}

    async def fake_aggregate_logs(query: str, start: int | None, end: int | None, step: int, tenant_id: str | None = None) -> dict[str, Any]:
        loki_calls.append(("aggregate", {"query": query, "start": start, "end": end, "step": step, "tenant_id": tenant_id}))
        return {"query": query, "step": step, "tenant_id": tenant_id}

    async def fake_get_log_volume(query: str, start: int | None, end: int | None, step: int, tenant_id: str | None = None) -> dict[str, Any]:
        loki_calls.append(("volume", {"query": query, "start": start, "end": end, "step": step, "tenant_id": tenant_id}))
        return {"query": query, "step": step, "tenant_id": tenant_id}

    monkeypatch.setattr(tempo_router.tempo_service, "search_traces", fake_search_traces)
    monkeypatch.setattr(tempo_router.tempo_service, "get_trace", fake_get_trace)
    monkeypatch.setattr(tempo_router.tempo_service, "get_services", fake_get_services)
    monkeypatch.setattr(tempo_router.tempo_service, "get_operations", fake_get_operations)
    monkeypatch.setattr(loki_router.loki_service, "query_logs", fake_query_logs)
    monkeypatch.setattr(loki_router.loki_service, "query_logs_instant", fake_query_logs_instant)
    monkeypatch.setattr(loki_router.loki_service, "get_labels", fake_get_labels)
    monkeypatch.setattr(loki_router.loki_service, "get_label_values", fake_get_label_values)
    monkeypatch.setattr(loki_router.loki_service, "search_logs_by_pattern", fake_search_logs_by_pattern)
    monkeypatch.setattr(loki_router.loki_service, "filter_logs", fake_filter_logs)
    monkeypatch.setattr(loki_router.loki_service, "aggregate_logs", fake_aggregate_logs)
    monkeypatch.setattr(loki_router.loki_service, "get_log_volume", fake_get_log_volume)

    headers = state.auth_header("token-u-admin")

    assert client.get(
        "/api/tempo/traces/search",
        headers=headers,
        params={"service": "checkout", "operation": "POST /cart", "minDuration": "10ms", "maxDuration": "500ms", "start": 10, "end": 20, "limit": 5, "fetchFull": True},
    ).status_code == 200
    assert client.get("/api/tempo/traces/trace-1", headers=headers).status_code == 200
    assert client.get("/api/tempo/services", headers=headers).status_code == 200
    assert client.get("/api/tempo/services/cart/operations", headers=headers).status_code == 200

    assert client.get("/api/loki/query", headers=headers, params={"query": "{service=\"checkout\"}", "start": 1, "end": 2, "direction": "forward", "step": 30}).status_code == 200
    assert client.get("/api/loki/query_instant", headers=headers, params={"query": "sum(rate(errors[5m]))", "time": 3, "limit": 2}).status_code == 200
    assert client.get("/api/loki/labels", headers=headers, params={"start": 1, "end": 2}).status_code == 200
    assert client.get("/api/loki/label/service/values", headers=headers, params={"start": 1, "end": 2, "query": "{service=\"checkout\"}"}).status_code == 200
    assert client.post("/api/loki/search", headers=headers, json={"pattern": "timeout|error", "labels": {"service": "checkout"}, "start": 1, "end": 2, "limit": 10}).status_code == 200
    assert client.post("/api/loki/filter", headers=headers, json={"labels": {"service": "checkout", "level": "error"}, "filters": ["timeout", "db"], "start": 1, "end": 2, "limit": 10}).status_code == 200
    assert client.get("/api/loki/aggregate", headers=headers, params={"query": "sum(rate({service=\"checkout\"}[5m]))", "start": 1, "end": 2, "step": 60}).status_code == 200
    assert client.get("/api/loki/volume", headers=headers, params={"query": "{service=\"checkout\"}", "start": 1, "end": 2, "step": 300}).status_code == 200

    assert tempo_calls[0]["tenant_id"] == "org-a"
    assert any(call[0] == "filter" and call[1]["tenant_id"] == "org-a" for call in loki_calls)


def test_becertain_alertmanager_and_agents_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)

    viewer = state.create_user(SimpleNamespace(username="viewer", email="viewer@example.com", password="password123", role="viewer"), state.tenant_id)
    viewer_id = viewer.id
    agent_key = state.create_api_key("u-admin", state.tenant_id, SimpleNamespace(name="tenant-scope", key="tenant-scope"))

    becertain_calls: list[dict[str, Any]] = []
    forward_calls: list[dict[str, Any]] = []
    heartbeats: list[dict[str, Any]] = []

    async def fake_request_json(**kwargs: Any) -> dict[str, Any]:
        becertain_calls.append(kwargs)
        path = kwargs["upstream_path"]
        if path == "/api/v1/jobs/analyze":
            return {"job_id": "job-1", "report_id": "report-1", "status": "accepted", "created_at": "2024-01-01T00:00:00Z", "tenant_id": kwargs["payload"]["tenant_id"], "requested_by": kwargs["current_user"].user_id}
        if path == "/api/v1/jobs":
            return {"items": [{"job_id": "job-1", "report_id": "report-1", "status": "running", "created_at": "2024-01-01T00:00:00Z", "tenant_id": kwargs["tenant_id"], "requested_by": kwargs["current_user"].user_id}], "next_cursor": "cursor-1"}
        if path == "/api/v1/jobs/job-1":
            return {"job_id": "job-1", "report_id": "report-1", "status": "completed", "created_at": "2024-01-01T00:00:00Z", "tenant_id": kwargs["tenant_id"], "requested_by": kwargs["current_user"].user_id}
        if path == "/api/v1/jobs/job-1/result":
            return {"job_id": "job-1", "report_id": "report-1", "status": "completed", "tenant_id": kwargs["tenant_id"], "requested_by": kwargs["current_user"].user_id, "result": {"quality": {"gating_profile": "strict"}}}
        if path == "/api/v1/reports/report-1":
            return {"job_id": "job-1", "report_id": "report-1", "status": "completed", "tenant_id": kwargs["tenant_id"], "requested_by": kwargs["current_user"].user_id, "result": {"summary": "ok"}}
        if path == "/api/v1/reports/report-1" and kwargs["method"] == "DELETE":
            return {"report_id": "report-1", "status": "deleted", "deleted": True}
        return {"ok": True, "path": path, "tenant_id": kwargs.get("tenant_id"), "params": kwargs.get("params")}

    async def fake_forward(**kwargs: Any):
        forward_calls.append(kwargs)
        return JSONResponse({"ok": True, "path": kwargs["upstream_path"], "method": kwargs["request"].method})

    async def fake_find_silence_for_mutation(**kwargs: Any) -> dict[str, Any]:
        return {"id": kwargs["silence_id"], "created_by": kwargs["current_user"].user_id}

    async def fake_key_activity(key_value: str, _client: object) -> dict[str, Any]:
        return {"metrics_active": key_value == agent_key.key, "metrics_count": 4}

    monkeypatch.setattr(becertain_router.becertain_proxy_service, "request_json", fake_request_json)
    monkeypatch.setattr(alertmanager_router, "enforce_public_endpoint_security", lambda *args, **kwargs: None)
    monkeypatch.setattr(alertmanager_router.benotified_proxy_service, "forward", fake_forward)
    monkeypatch.setattr(alertmanager_router, "validate_and_normalize_silence_payload", lambda payload, _user: {"id": payload.get("id", "sil-1"), "visibility": payload.get("visibility", "private")})
    monkeypatch.setattr(alertmanager_router, "extract_silence_id", lambda path, payload: (payload or {}).get("id") or path.split("/")[-1])
    monkeypatch.setattr(alertmanager_router, "find_silence_for_mutation", fake_find_silence_for_mutation)
    monkeypatch.setattr(alertmanager_router, "assert_silence_owner", lambda current_user, silence: None)
    monkeypatch.setattr(agents_router, "enforce_public_endpoint_security", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents_router, "enforce_header_token", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents_router.agent_service, "list_agents", lambda: [SimpleNamespace(model_dump=lambda: {"id": "agent-1", "name": "edge", "tenant_id": agent_key.key}, tenant_id=agent_key.key, host_name="edge-1")])
    monkeypatch.setattr(agents_router.agent_service, "key_activity", fake_key_activity)
    monkeypatch.setattr(agents_router.agent_service, "update_from_heartbeat", lambda payload: heartbeats.append(payload.model_dump()))

    admin_headers = state.auth_header("token-u-admin")
    viewer_headers = state.auth_header(f"token-{viewer_id}")

    assert client.post("/api/becertain/analyze/jobs", headers=admin_headers, json={"start": 1, "end": 2, "services": ["api"], "log_query": "{service=\"api\"}"}).status_code == 202
    assert client.get("/api/becertain/analyze/jobs", headers=admin_headers, params={"status": "running", "limit": 5, "cursor": "cursor-0"}).status_code == 200
    assert client.get("/api/becertain/analyze/jobs/job-1", headers=admin_headers).status_code == 200
    assert client.get("/api/becertain/analyze/jobs/job-1/result", headers=admin_headers).status_code == 200
    assert client.get("/api/becertain/reports/report-1", headers=admin_headers).status_code == 200
    assert client.delete("/api/becertain/reports/report-1", headers=admin_headers).status_code == 200

    for path in [
        "/api/becertain/anomalies/metrics",
        "/api/becertain/anomalies/logs/patterns",
        "/api/becertain/anomalies/logs/bursts",
        "/api/becertain/anomalies/traces",
        "/api/becertain/correlate",
        "/api/becertain/topology/blast-radius",
        "/api/becertain/slo/burn",
        "/api/becertain/forecast/trajectory",
        "/api/becertain/causal/granger",
        "/api/becertain/causal/bayesian",
    ]:
        assert client.post(path, headers=admin_headers, json={"service": "api", "window": "15m"}).status_code == 200

    assert client.get("/api/becertain/ml/weights", headers=admin_headers).status_code == 200
    assert client.post("/api/becertain/ml/weights/feedback", headers=admin_headers, params={"signal": "traces", "was_correct": "true"}).status_code == 200
    assert client.post("/api/becertain/ml/weights/reset", headers=admin_headers).status_code == 200
    assert client.get("/api/becertain/events/deployments", headers=admin_headers).status_code == 200

    assert client.get("/api/alertmanager/public/rules").status_code == 200
    assert client.get("/api/alertmanager/rules", headers=viewer_headers).status_code == 200
    assert client.get("/api/alertmanager/silences", headers=viewer_headers).status_code == 200
    assert client.post("/api/alertmanager/alerts", headers=viewer_headers, json={"alerts": []}).status_code == 403
    assert client.post("/api/alertmanager/silences", headers=admin_headers, json={"id": "sil-1", "visibility": "private"}).status_code == 200
    assert client.put("/api/alertmanager/silences/sil-1", headers=admin_headers, json={"id": "sil-1", "visibility": "private"}).status_code == 200
    assert client.delete("/api/alertmanager/silences/sil-1", headers=admin_headers).status_code == 200
    assert client.post("/api/alertmanager/channels", headers=admin_headers, json={"name": "email"}).status_code == 200
    assert client.put("/api/alertmanager/channels/chan-1", headers=admin_headers, json={"name": "pagerduty"}).status_code == 200
    assert client.delete("/api/alertmanager/channels/chan-1", headers=admin_headers).status_code == 200
    assert client.get("/api/alertmanager/jira/config", headers=admin_headers).status_code == 200
    assert client.post("/api/alertmanager/jira/issues", headers=admin_headers, json={"summary": "Issue"}).status_code == 200
    assert client.post("/api/alertmanager/integrations/slack", headers=admin_headers, json={"method": "webhook"}).status_code == 200
    assert client.post("/api/alertmanager/integrations/teams", headers=admin_headers, json={"method": "oauth"}).status_code == 200
    assert client.patch("/api/alertmanager/incidents/inc-1", headers=admin_headers, json={"status": "acknowledged"}).status_code == 200

    assert client.get("/api/agents/", headers=admin_headers).status_code == 200
    active_agents_response = client.get("/api/agents/active", headers=admin_headers)
    assert active_agents_response.status_code == 200
    assert active_agents_response.json()[0]["active"] is True
    heartbeat_response = client.post(
        "/api/agents/heartbeat",
        json={"name": "edge", "tenant_id": agent_key.key, "signal": "logs", "timestamp": datetime.now(timezone.utc).isoformat()},
    )
    assert heartbeat_response.status_code == 200
    assert heartbeats[0]["tenant_id"] == agent_key.key

    assert becertain_calls[0]["payload"]["tenant_id"] == "org-a"
    assert any(call["upstream_path"] == "/internal/v1/api/alertmanager/channels" for call in forward_calls)