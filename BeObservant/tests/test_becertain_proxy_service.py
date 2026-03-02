"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

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
