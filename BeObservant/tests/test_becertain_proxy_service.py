"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import asyncio
import httpx
import pytest
from fastapi import HTTPException
from tests._env import ensure_test_env
ensure_test_env()
from config import config
from models.access.auth_models import Role, TokenData
from services.becertain_proxy_service import BeCertainProxyService


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


def test_becertain_proxy_helper_methods(monkeypatch):
    service = BeCertainProxyService()
    monkeypatch.setattr(config, "BECERTAIN_PROXY_CACHE_TTL_SECONDS", 15)

    assert service._is_volatile_read("/api/v1/jobs/1") is True
    assert service._is_volatile_read("/api/v1/reports/1") is True
    assert service._is_volatile_read("/api/v1/weights") is False
    assert service._resolve_cache_ttl(method="GET", upstream_path="/api/v1/jobs/1", cache_ttl_seconds=30) == 0
    assert service._resolve_cache_ttl(method="POST", upstream_path="/api/v1/jobs/1", cache_ttl_seconds=30) == 30
    assert service._cache_key(
        method="get",
        upstream_path="/x",
        tenant_id="tenant-a",
        params={"a": 1},
        payload={"b": True},
    ) == '{"b":{"b":true},"m":"GET","p":"/x","q":{"a":1},"t":"tenant-a"}'.replace('"b":{', '"b":{')

    monkeypatch.setattr(config, "get_secret", lambda key: None)
    with pytest.raises(HTTPException, match="Missing BeCertain signing key"):
        service._sign_context_token(current_user=_user(), tenant_id="tenant-a")


def test_becertain_proxy_inflight_error_resolution():
    service = BeCertainProxyService()
    future = service._client._transport = None  # keep the instance referenced without affecting behavior
    loop = __import__("asyncio").new_event_loop()
    try:
        inflight = loop.create_future()
        err = HTTPException(status_code=502, detail="bad")
        service._resolve_inflight_error(True, inflight, err)
        assert inflight.done() is True
        assert inflight.exception() is err

        inflight = loop.create_future()
        service._resolve_inflight_error(False, inflight, err)
        assert inflight.done() is False
    finally:
        loop.close()


@pytest.mark.asyncio
async def test_becertain_proxy_timeout_maps_to_504(monkeypatch):
    service = BeCertainProxyService()
    monkeypatch.setattr(service, "write_audit", lambda **_kwargs: None)
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_ALGORITHM", "HS256")
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_ISSUER", "beobservant-main")
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_AUDIENCE", "becertain")
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_TTL_SECONDS", 120)
    monkeypatch.setattr(
        config,
        "get_secret",
        lambda key: {
            "BECERTAIN_SERVICE_TOKEN": "service-token",
            "BECERTAIN_CONTEXT_SIGNING_KEY": "signing-key",
        }.get(key),
    )

    class DummyClient:
        async def request(self, **_kwargs):
            raise httpx.TimeoutException("timeout")

    service._client = DummyClient()

    with pytest.raises(HTTPException) as exc:
        await service.request_json(
            method="GET",
            upstream_path="/api/v1/ml/weights",
            current_user=_user(),
            tenant_id="tenant-a",
        )
    assert exc.value.status_code == 504


@pytest.mark.asyncio
async def test_becertain_proxy_missing_service_token_and_generic_error(monkeypatch):
    service = BeCertainProxyService()
    audits = []
    monkeypatch.setattr(service, "write_audit", lambda **kwargs: audits.append(kwargs))
    monkeypatch.setattr(config, "get_secret", lambda key: {"BECERTAIN_CONTEXT_SIGNING_KEY": "signing-key"}.get(key))

    with pytest.raises(HTTPException, match="service token not configured"):
        await service.request_json(
            method="GET",
            upstream_path="/api/v1/ml/weights",
            current_user=_user(),
            tenant_id="tenant-a",
        )

    monkeypatch.setattr(
        config,
        "get_secret",
        lambda key: {
            "BECERTAIN_SERVICE_TOKEN": "service-token",
            "BECERTAIN_CONTEXT_SIGNING_KEY": "signing-key",
        }.get(key),
    )

    class DummyClient:
        async def request(self, **_kwargs):
            raise RuntimeError("boom")

    service._client = DummyClient()
    with pytest.raises(HTTPException, match="Failed to contact BeCertain"):
        await service.request_json(
            method="POST",
            upstream_path="/api/v1/ml/weights",
            current_user=_user(),
            tenant_id="tenant-a",
            payload={"a": 1},
            audit_action="becertain.proxy",
        )
    assert audits[-1]["action"] == "becertain.proxy.error"


@pytest.mark.asyncio
async def test_becertain_proxy_upstream_error_passthrough(monkeypatch):
    service = BeCertainProxyService()
    monkeypatch.setattr(service, "write_audit", lambda **_kwargs: None)
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_ALGORITHM", "HS256")
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_ISSUER", "beobservant-main")
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_AUDIENCE", "becertain")
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_TTL_SECONDS", 120)
    monkeypatch.setattr(
        config,
        "get_secret",
        lambda key: {
            "BECERTAIN_SERVICE_TOKEN": "service-token",
            "BECERTAIN_CONTEXT_SIGNING_KEY": "signing-key",
        }.get(key),
    )

    class DummyResponse:
        status_code = 502
        reason_phrase = "Bad Gateway"
        text = '{"detail":"upstream failed"}'

        def json(self):
            return {"detail": "upstream failed"}

    class DummyClient:
        async def request(self, **_kwargs):
            return DummyResponse()

    service._client = DummyClient()

    with pytest.raises(HTTPException) as exc:
        await service.request_json(
            method="GET",
            upstream_path="/api/v1/ml/weights",
            current_user=_user(),
            tenant_id="tenant-a",
        )
    assert exc.value.status_code == 502
    assert "upstream failed" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_becertain_proxy_does_not_cache_job_reads(monkeypatch):
    service = BeCertainProxyService()
    monkeypatch.setattr(service, "write_audit", lambda **_kwargs: None)
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_ALGORITHM", "HS256")
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_ISSUER", "beobservant-main")
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_AUDIENCE", "becertain")
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_TTL_SECONDS", 120)
    monkeypatch.setattr(
        config,
        "get_secret",
        lambda key: {
            "BECERTAIN_SERVICE_TOKEN": "service-token",
            "BECERTAIN_CONTEXT_SIGNING_KEY": "signing-key",
        }.get(key),
    )

    calls = {"count": 0}

    class DummyResponse:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class DummyClient:
        async def request(self, **_kwargs):
            calls["count"] += 1
            return DummyResponse(
                {
                    "job_id": "job-1",
                    "report_id": "rep-1",
                    "status": "completed",
                    "tenant_id": "tenant-a",
                    "requested_by": "u1",
                    "result": None,
                }
            )

    service._client = DummyClient()

    first = await service.request_json(
        method="GET",
        upstream_path="/api/v1/jobs/job-1/result",
        current_user=_user(),
        tenant_id="tenant-a",
    )
    second = await service.request_json(
        method="GET",
        upstream_path="/api/v1/jobs/job-1/result",
        current_user=_user(),
        tenant_id="tenant-a",
    )

    assert first == second
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_becertain_proxy_cache_hit_and_invalid_json(monkeypatch):
    service = BeCertainProxyService()
    monkeypatch.setattr(service, "write_audit", lambda **_kwargs: None)
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_ALGORITHM", "HS256")
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_ISSUER", "beobservant-main")
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_AUDIENCE", "becertain")
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_TTL_SECONDS", 120)
    monkeypatch.setattr(
        config,
        "get_secret",
        lambda key: {
            "BECERTAIN_SERVICE_TOKEN": "service-token",
            "BECERTAIN_CONTEXT_SIGNING_KEY": "signing-key",
        }.get(key),
    )

    cache_key = service._cache_key(
        method="GET",
        upstream_path="/api/v1/ml/weights",
        tenant_id="tenant-a",
        params=None,
        payload=None,
    )
    await service._read_cache.set(cache_key, {"cached": True}, 10)
    assert await service.request_json(
        method="GET",
        upstream_path="/api/v1/ml/weights",
        current_user=_user(),
        tenant_id="tenant-a",
    ) == {"cached": True}

    class DummyResponse:
        status_code = 200
        reason_phrase = "OK"
        text = "not-json"

        def json(self):
            return object()

    class DummyClient:
        async def request(self, **_kwargs):
            return DummyResponse()

    service = BeCertainProxyService()
    monkeypatch.setattr(service, "write_audit", lambda **_kwargs: None)
    service._client = DummyClient()
    with pytest.raises(HTTPException, match="invalid JSON"):
        await service.request_json(
            method="GET",
            upstream_path="/api/v1/ml/weights/fresh",
            current_user=_user(),
            tenant_id="tenant-a",
        )


@pytest.mark.asyncio
async def test_becertain_proxy_collapses_inflight_reads(monkeypatch):
    service = BeCertainProxyService()
    monkeypatch.setattr(service, "write_audit", lambda **_kwargs: None)
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_ALGORITHM", "HS256")
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_ISSUER", "beobservant-main")
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_AUDIENCE", "becertain")
    monkeypatch.setattr(config, "BECERTAIN_CONTEXT_TTL_SECONDS", 120)
    monkeypatch.setattr(
        config,
        "get_secret",
        lambda key: {
            "BECERTAIN_SERVICE_TOKEN": "service-token",
            "BECERTAIN_CONTEXT_SIGNING_KEY": "signing-key",
        }.get(key),
    )

    started = asyncio.Event()
    release = asyncio.Event()
    calls = []

    class DummyResponse:
        status_code = 200

        def json(self):
            return {"shared": True}

    class DummyClient:
        async def request(self, **_kwargs):
            calls.append(_kwargs["url"])
            started.set()
            await release.wait()
            return DummyResponse()

    service._client = DummyClient()

    first = asyncio.create_task(
        service.request_json(
            method="GET",
            upstream_path="/api/v1/ml/weights/shared",
            current_user=_user(),
            tenant_id="tenant-a",
        )
    )
    await started.wait()
    second = asyncio.create_task(
        service.request_json(
            method="GET",
            upstream_path="/api/v1/ml/weights/shared",
            current_user=_user(),
            tenant_id="tenant-a",
        )
    )
    release.set()

    assert await first == {"shared": True}
    assert await second == {"shared": True}
    assert len(calls) == 1
    assert service._read_inflight == {}


@pytest.mark.asyncio
async def test_becertain_proxy_uses_existing_inflight_future_and_locked_cache(monkeypatch):
    service = BeCertainProxyService()
    monkeypatch.setattr(config, "get_secret", lambda key: "service-token" if key == "BECERTAIN_SERVICE_TOKEN" else "signing-key")
    monkeypatch.setattr(service, "_sign_context_token", lambda **_: "ctx")
    monkeypatch.setattr(service, "write_audit", lambda **_kwargs: None)

    cache_key = service._cache_key(
        method="GET",
        upstream_path="/api/v1/ml/weights/shared",
        tenant_id="tenant-a",
        params=None,
        payload=None,
    )

    inflight = asyncio.get_running_loop().create_future()
    inflight.set_result({"from": "future"})
    service._read_inflight[cache_key] = inflight

    assert await service.request_json(
        method="GET",
        upstream_path="/api/v1/ml/weights/shared",
        current_user=_user(),
        tenant_id="tenant-a",
    ) == {"from": "future"}

    service = BeCertainProxyService()
    monkeypatch.setattr(service, "_sign_context_token", lambda **_: "ctx")
    monkeypatch.setattr(service, "write_audit", lambda **_kwargs: None)

    cache_reads = iter([None, {"from": "late-cache"}])

    async def fake_get(_key):
        return next(cache_reads)

    monkeypatch.setattr(service._read_cache, "get", fake_get)
    assert await service.request_json(
        method="GET",
        upstream_path="/api/v1/ml/weights/shared",
        current_user=_user(),
        tenant_id="tenant-a",
    ) == {"from": "late-cache"}
