"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from tests._env import ensure_test_env

ensure_test_env()

import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request
from types import SimpleNamespace

from models.access.auth_models import TokenData, Role
from services.benotified_proxy_service import BeNotifiedProxyService
from config import config


def _user(tenant_id: str = "tenant-a", user_id: str = "u1") -> TokenData:
    return TokenData(
        user_id=user_id,
        username=f"user-{user_id}",
        tenant_id=tenant_id,
        org_id=tenant_id,
        role=Role.USER,
        permissions=["update:incidents"],
        group_ids=["g1"],
        is_superuser=False,
        is_mfa_setup=False,
    )


def _request(
    *,
    method: str = "POST",
    path: str = "/api/alertmanager/incidents/inc-1/jira",
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"{}",
) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "query_string": b"",
    }
    req = Request(scope)
    req._body = body
    return req


class _DummyResponse:
    status_code = 200
    content = b'{"ok":true}'
    headers = {"content-type": "application/json"}


@pytest.mark.asyncio
async def test_forward_removes_scope_header_when_user(monkeypatch):
    svc = BeNotifiedProxyService()
    captured = {}

    async def fake_request(*, method, url, params, content, headers):
        captured["headers"] = dict(headers)
        return _DummyResponse()

    monkeypatch.setattr(svc, "write_audit", lambda **_: None)
    monkeypatch.setattr(svc, "_resolve_actor_api_key_id", lambda u: None)
    monkeypatch.setattr(svc, "_sign_context_token", lambda **_: "tok")
    monkeypatch.setattr(config, "get_secret", lambda key: "service-token")
    svc._client.request = fake_request

    req = _request(headers=[(b"x-scope-orgid", b"tenant-b")])
    resp = await svc.forward(
        request=req,
        upstream_path="/foo",
        current_user=_user(),
        require_api_key=False,
        audit_action="a",
    )
    assert isinstance(resp, Response)
    assert "x-scope-orgid" not in {k.lower(): v for k, v in captured["headers"].items()}


@pytest.mark.asyncio
async def test_forward_preserves_scope_header_for_anonymous(monkeypatch):
    svc = BeNotifiedProxyService()
    captured = {}

    async def fake_request(*, method, url, params, content, headers):
        captured["headers"] = dict(headers)
        return _DummyResponse()

    monkeypatch.setattr(svc, "write_audit", lambda **_: None)
    monkeypatch.setattr(config, "get_secret", lambda key: "service-token")
    svc._client.request = fake_request

    req = _request(headers=[(b"x-scope-orgid", b"tenant-b")])
    resp = await svc.forward(
        request=req,
        upstream_path="/foo",
        current_user=None,
        require_api_key=False,
        audit_action="a",
    )
    assert isinstance(resp, Response)
    assert "x-scope-orgid" in {k.lower(): v for k, v in captured["headers"].items()}

