import asyncio

import pytest
from fastapi import HTTPException

from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Role, TokenData
from models.observability.becertain_models import AnalyzeJobStatus, AnalyzeRequestPayload
from services.becertain_job_service import BeCertainAnalyzeJobService


def _user(user_id: str) -> TokenData:
    return TokenData(
        user_id=user_id,
        username=f"user-{user_id}",
        tenant_id="tenant-a",
        org_id="tenant-a",
        role=Role.USER,
        permissions=["read:rca", "create:rca"],
        group_ids=[],
        is_superuser=False,
        is_mfa_setup=False,
    )


@pytest.mark.asyncio
async def test_analyze_job_success(monkeypatch, tmp_path):
    service = BeCertainAnalyzeJobService(storage_path=str(tmp_path / "jobs"))

    async def fake_request_json(**_kwargs):
        return {"summary": "analysis complete"}

    monkeypatch.setattr("services.becertain_job_service.becertain_proxy_service.request_json", fake_request_json)
    monkeypatch.setattr("services.becertain_job_service.becertain_proxy_service.write_audit", lambda **_kwargs: None)

    created = await service.create_job(
        current_user=_user("u1"),
        tenant_id="tenant-a",
        payload=AnalyzeRequestPayload(start=1, end=2),
    )
    await asyncio.wait_for(created.task, timeout=2)

    job = await service.get_job(job_id=created.job_id, user_id="u1", tenant_id="tenant-a")
    assert job.status == AnalyzeJobStatus.COMPLETED
    assert job.result == {"summary": "analysis complete"}
    assert job.summary_preview == "analysis complete"


@pytest.mark.asyncio
async def test_analyze_job_failure(monkeypatch, tmp_path):
    service = BeCertainAnalyzeJobService(storage_path=str(tmp_path / "jobs"))

    async def fake_request_json(**_kwargs):
        raise HTTPException(status_code=504, detail="timeout")

    monkeypatch.setattr("services.becertain_job_service.becertain_proxy_service.request_json", fake_request_json)
    monkeypatch.setattr("services.becertain_job_service.becertain_proxy_service.write_audit", lambda **_kwargs: None)

    created = await service.create_job(
        current_user=_user("u1"),
        tenant_id="tenant-a",
        payload=AnalyzeRequestPayload(start=1, end=2),
    )
    await asyncio.wait_for(created.task, timeout=2)

    job = await service.get_job(job_id=created.job_id, user_id="u1", tenant_id="tenant-a")
    assert job.status == AnalyzeJobStatus.FAILED
    assert "timeout" in (job.error or "")


@pytest.mark.asyncio
async def test_analyze_job_owner_enforced(monkeypatch, tmp_path):
    service = BeCertainAnalyzeJobService(storage_path=str(tmp_path / "jobs"))

    async def fake_request_json(**_kwargs):
        return {"summary": "done"}

    monkeypatch.setattr("services.becertain_job_service.becertain_proxy_service.request_json", fake_request_json)
    monkeypatch.setattr("services.becertain_job_service.becertain_proxy_service.write_audit", lambda **_kwargs: None)

    created = await service.create_job(
        current_user=_user("u1"),
        tenant_id="tenant-a",
        payload=AnalyzeRequestPayload(start=1, end=2),
    )
    await asyncio.wait_for(created.task, timeout=2)

    with pytest.raises(HTTPException) as exc:
        await service.get_job(job_id=created.job_id, user_id="u2", tenant_id="tenant-a")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_analyze_job_result_persists_on_disk(monkeypatch, tmp_path):
    storage_path = str(tmp_path / "jobs")
    service = BeCertainAnalyzeJobService(storage_path=storage_path)

    async def fake_request_json(**_kwargs):
        return {"summary": "persisted report", "overall_severity": "medium"}

    monkeypatch.setattr("services.becertain_job_service.becertain_proxy_service.request_json", fake_request_json)
    monkeypatch.setattr("services.becertain_job_service.becertain_proxy_service.write_audit", lambda **_kwargs: None)

    created = await service.create_job(
        current_user=_user("u1"),
        tenant_id="tenant-a",
        payload=AnalyzeRequestPayload(start=1, end=2),
    )
    await asyncio.wait_for(created.task, timeout=2)

    # Simulate process restart by creating a fresh service instance over the same storage path.
    reloaded = BeCertainAnalyzeJobService(storage_path=storage_path)
    result = await reloaded.get_job_result(job_id=created.job_id, user_id="u1", tenant_id="tenant-a")
    assert result["summary"] == "persisted report"
