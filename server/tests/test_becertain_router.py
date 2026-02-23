from tests._env import ensure_test_env

ensure_test_env()

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from models.access.auth_models import Role, TokenData
from routers.observability import becertain_router
from models.observability.becertain_models import AnalyzeJobStatus


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
    class DummyJob:
        job_id = "job-1"
        status = AnalyzeJobStatus.RUNNING
        result = None

    async def fake_get_job(**_kwargs):
        return DummyJob()

    monkeypatch.setattr("routers.observability.becertain_router.becertain_analyze_job_service.get_job", fake_get_job)

    with pytest.raises(HTTPException) as exc:
        await becertain_router.get_analyze_job_result(
            job_id="job-1",
            request=_request(),
            current_user=_user(),
        )
    assert exc.value.status_code == 409
