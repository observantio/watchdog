"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from tests._env import ensure_test_env
ensure_test_env()
import pytest
from starlette.requests import Request

from models.access.auth_models import Role, TokenData
from routers.observability import becertain_router


def _request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/becertain/anomalies/metrics",
        "headers": [],
    }
    return Request(scope)


def _user() -> TokenData:
    return TokenData(
        user_id="u1",
        username="user-1",
        tenant_id="tenant-a",
        org_id="tenant-a",
        role=Role.USER,
        permissions=["read:rca", "create:rca"],
        group_ids=[],
        is_superuser=False,
        is_mfa_setup=False,
    )


@pytest.mark.asyncio
async def test_proxy_post_overrides_payload_tenant(monkeypatch):
    captured = {}

    async def fake_request_json(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr("routers.observability.becertain_router.becertain_proxy_service.request_json", fake_request_json)

    result = await becertain_router.anomalies_metrics(
        request=_request(),
        payload={"tenant_id": "spoofed", "query": "up"},
        current_user=_user(),
    )
    assert result == {"ok": True}
    assert captured["payload"]["tenant_id"] == "tenant-a"


@pytest.mark.asyncio
async def test_job_result_requires_completed_status(monkeypatch):
    captured = {}

    async def fake_request_json(**kwargs):
        captured.update(kwargs)
        return {
            "job_id": "job-1",
            "report_id": "rep-1",
            "status": "completed",
            "tenant_id": "tenant-a",
            "requested_by": "u1",
            "result": {"summary": "ok"},
        }

    monkeypatch.setattr("routers.observability.becertain_router.becertain_proxy_service.request_json", fake_request_json)

    result = await becertain_router.get_analyze_job_result(
        job_id="job-1",
        request=_request(),
        current_user=_user(),
    )
    assert result.job_id == "job-1"
    assert result.report_id == "rep-1"
    assert captured["upstream_path"] == "/api/v1/jobs/job-1/result"


@pytest.mark.asyncio
async def test_get_report_by_id_proxies(monkeypatch):
    captured = {}

    async def fake_request_json(**kwargs):
        captured.update(kwargs)
        return {
            "job_id": "job-1",
            "report_id": "rep-1",
            "status": "completed",
            "tenant_id": "tenant-a",
            "requested_by": "u1",
            "result": {"summary": "ok"},
        }

    monkeypatch.setattr("routers.observability.becertain_router.becertain_proxy_service.request_json", fake_request_json)
    result = await becertain_router.get_report_by_id("rep-1", _request(), _user())
    assert result.report_id == "rep-1"
    assert captured["upstream_path"] == "/api/v1/reports/rep-1"


@pytest.mark.asyncio
async def test_delete_report_by_id_proxies(monkeypatch):
    captured = {}

    async def fake_request_json(**kwargs):
        captured.update(kwargs)
        return {"report_id": "rep-1", "status": "deleted", "deleted": True}

    monkeypatch.setattr("routers.observability.becertain_router.becertain_proxy_service.request_json", fake_request_json)
    result = await becertain_router.delete_report_by_id("rep-1", _request(), _user())
    assert result.deleted is True
    assert captured["upstream_path"] == "/api/v1/reports/rep-1"


@pytest.mark.asyncio
async def test_get_analyze_job_result_tolerates_unknown_running_status(monkeypatch):
    async def fake_request_json(**kwargs):
        return {
            "job_id": "job-2",
            "report_id": "rep-2",
            "status": "in_progress",
            "tenant_id": "tenant-a",
            "requested_by": "u1",
            "result": None,
        }

    monkeypatch.setattr("routers.observability.becertain_router.becertain_proxy_service.request_json", fake_request_json)
    result = await becertain_router.get_analyze_job_result(
        job_id="job-2",
        request=_request(),
        current_user=_user(),
    )
    assert result.status.value == "running"


@pytest.mark.asyncio
async def test_get_analyze_job_result_maps_succeeded_status_to_completed(monkeypatch):
    async def fake_request_json(**kwargs):
        return {
            "job_id": "job-2b",
            "report_id": "rep-2b",
            "status": "succeeded",
            "tenant_id": "tenant-a",
            "requested_by": "u1",
            "result": {"summary": "ok"},
        }

    monkeypatch.setattr("routers.observability.becertain_router.becertain_proxy_service.request_json", fake_request_json)
    result = await becertain_router.get_analyze_job_result(
        job_id="job-2b",
        request=_request(),
        current_user=_user(),
    )
    assert result.status.value == "completed"
    assert result.result == {"summary": "ok"}


@pytest.mark.asyncio
async def test_get_analyze_job_result_maps_conflict_to_job_summary(monkeypatch):
    calls = []

    async def fake_request_json(**kwargs):
        calls.append(kwargs["upstream_path"])
        if kwargs["upstream_path"] == "/api/v1/jobs/job-3/result":
            raise becertain_router.HTTPException(status_code=409, detail="result not ready")
        return {
            "job_id": "job-3",
            "report_id": "rep-3",
            "status": "completed",
            "created_at": "2026-03-08T00:00:00Z",
            "tenant_id": "tenant-a",
            "requested_by": "u1",
            "result": None,
        }

    monkeypatch.setattr("routers.observability.becertain_router.becertain_proxy_service.request_json", fake_request_json)
    result = await becertain_router.get_analyze_job_result(
        job_id="job-3",
        request=_request(),
        current_user=_user(),
    )
    assert result.job_id == "job-3"
    assert result.report_id == "rep-3"
    assert result.status.value == "completed"
    assert result.result is None
    assert calls == ["/api/v1/jobs/job-3/result", "/api/v1/jobs/job-3"]


@pytest.mark.asyncio
async def test_ml_weights_feedback_proxies(monkeypatch):
    captured = {}

    async def fake_request_json(**kwargs):
        captured.update(kwargs)
        return {"updated_weights": {"metrics": 0.5}, "update_count": 1}

    monkeypatch.setattr("routers.observability.becertain_router.becertain_proxy_service.request_json", fake_request_json)
    result = await becertain_router.ml_weights_feedback(
        request=_request(),
        signal="metrics",
        was_correct=True,
        current_user=_user(),
    )
    assert result["update_count"] == 1
    assert captured["upstream_path"] == "/api/v1/ml/weights/feedback"
    assert captured["params"]["tenant_id"] == "tenant-a"
    assert captured["params"]["signal"] == "metrics"
    assert captured["params"]["was_correct"] == "true"


@pytest.mark.asyncio
async def test_ml_weights_reset_proxies(monkeypatch):
    captured = {}

    async def fake_request_json(**kwargs):
        captured.update(kwargs)
        return {"weights": {"metrics": 0.3, "logs": 0.35, "traces": 0.35}, "update_count": 0}

    monkeypatch.setattr("routers.observability.becertain_router.becertain_proxy_service.request_json", fake_request_json)
    user = TokenData(
        user_id="u1",
        username="user-1",
        tenant_id="tenant-a",
        org_id="tenant-a",
        role=Role.USER,
        permissions=["delete:rca", "read:rca", "create:rca"],
        group_ids=[],
        is_superuser=False,
        is_mfa_setup=False,
    )
    result = await becertain_router.ml_weights_reset(
        request=_request(),
        current_user=user,
    )
    assert result["update_count"] == 0
    assert captured["upstream_path"] == "/api/v1/ml/weights/reset"
    assert captured["params"]["tenant_id"] == "tenant-a"
