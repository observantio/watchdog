"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from tests._env import ensure_test_env

ensure_test_env()

import pytest
import httpx
from fastapi import Response
from fastapi import HTTPException
from starlette.requests import Request

from models.access.auth_models import TokenData, Role
from services.notifier_proxy_service import NotifierProxyService
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


class _DummyTimeout(httpx.TimeoutException):
    pass


class _DummyHttpError(httpx.HTTPError):
    pass


@pytest.mark.asyncio
async def test_forward_removes_scope_header_when_user(monkeypatch):
    svc = NotifierProxyService()
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
    svc = NotifierProxyService()
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


def test_resolve_actor_api_key_id_prefers_default_enabled(monkeypatch):
    svc = NotifierProxyService()
    user = _user()
    keys = [
        type("Key", (), {"id": "disabled", "is_enabled": False, "is_default": True})(),
        type("Key", (), {"id": "fallback", "is_enabled": True, "is_default": False})(),
        type("Key", (), {"id": "default", "is_enabled": True, "is_default": True})(),
    ]
    monkeypatch.setattr("services.notifier_proxy_service.auth_service.list_api_keys", lambda *_: keys)

    assert svc._resolve_actor_api_key_id(user) == "default"


def test_resolve_actor_api_key_id_handles_errors(monkeypatch):
    svc = NotifierProxyService()
    user = _user()

    def boom(*_args):
        raise Exception("unused")

    def db_boom(*_args):
        from sqlalchemy.exc import SQLAlchemyError

        raise SQLAlchemyError("db down")

    monkeypatch.setattr("services.notifier_proxy_service.auth_service.list_api_keys", db_boom)
    assert svc._resolve_actor_api_key_id(user) is None

    monkeypatch.setattr("services.notifier_proxy_service.auth_service.list_api_keys", lambda *_: [])
    assert svc._resolve_actor_api_key_id(user) is None


def test_sign_context_token_uses_live_group_ids_and_falls_back(monkeypatch):
    svc = NotifierProxyService()
    user = _user()
    encoded = {}

    def fake_encode(claims, key, algorithm):
        encoded["claims"] = claims
        return "jwt"

    monkeypatch.setattr(config, "get_secret", lambda key: "signing-key")
    monkeypatch.setattr(
        "services.notifier_proxy_service.auth_service.get_user_by_id_in_tenant",
        lambda *_: type("LiveUser", (), {"group_ids": ["g2", " ", "g3"]})(),
    )
    monkeypatch.setattr(svc, "_encode_jwt", fake_encode)

    token = svc._sign_context_token(current_user=user, api_key_id="key-1")
    assert token == "jwt"
    assert encoded["claims"]["group_ids"] == ["g2", "g3"]
    assert encoded["claims"]["api_key_id"] == "key-1"


def test_sign_context_token_handles_missing_key_and_sql_errors(monkeypatch):
    svc = NotifierProxyService()
    user = _user()

    def fake_encode(claims, key, algorithm):
        captured["claims"] = claims
        return "jwt"

    monkeypatch.setattr(config, "get_secret", lambda key: None)
    with pytest.raises(HTTPException, match="Missing Notifier signing key"):
        svc._sign_context_token(current_user=user, api_key_id=None)

    monkeypatch.setattr(config, "get_secret", lambda key: "signing-key")

    def db_boom(*_args):
        from sqlalchemy.exc import SQLAlchemyError

        raise SQLAlchemyError("db down")

    captured = {}
    monkeypatch.setattr("services.notifier_proxy_service.auth_service.get_user_by_id_in_tenant", db_boom)
    monkeypatch.setattr(svc, "_encode_jwt", fake_encode)

    assert svc._sign_context_token(current_user=user, api_key_id=None) == "jwt"
    assert captured["claims"]["group_ids"] == ["g1"]


def test_forwardable_response_headers_filters_values():
    headers = httpx.Headers(
        {
            "content-type": "application/json",
            "cache-control": "no-cache",
            "etag": "abc",
            "x-request-id": "req-1",
            "server": "ignored",
        }
    )

    assert NotifierProxyService._forwardable_response_headers(headers) == {
        "content-type": "application/json",
        "cache-control": "no-cache",
        "etag": "abc",
        "x-request-id": "req-1",
    }


@pytest.mark.asyncio
async def test_forward_requires_api_key_and_records_timeout(monkeypatch):
    svc = NotifierProxyService()
    audits = []
    monkeypatch.setattr(svc, "write_audit", lambda **kwargs: audits.append(kwargs))
    monkeypatch.setattr(config, "get_secret", lambda key: "service-token")
    monkeypatch.setattr(svc, "_resolve_actor_api_key_id", lambda user: None)

    req = _request()
    with pytest.raises(HTTPException, match="No active API key"):
        await svc.forward(
            request=req,
            upstream_path="/foo",
            current_user=_user(),
            require_api_key=True,
            audit_action="jira",
        )

    monkeypatch.setattr(svc, "_resolve_actor_api_key_id", lambda user: "key-1")
    monkeypatch.setattr(svc, "_sign_context_token", lambda **_: "ctx")

    async def raise_timeout(**_kwargs):
        raise _DummyTimeout("slow")

    svc._client.request = raise_timeout
    with pytest.raises(HTTPException, match="timed out"):
        await svc.forward(
            request=req,
            upstream_path="/foo",
            current_user=_user(),
            require_api_key=True,
            audit_action="jira",
        )
    assert audits[-1]["action"] == "jira.timeout"


@pytest.mark.asyncio
async def test_forward_records_http_errors_and_passes_webhook_header(monkeypatch):
    svc = NotifierProxyService()
    audits = []
    captured = {}
    monkeypatch.setattr(svc, "write_audit", lambda **kwargs: audits.append(kwargs))
    monkeypatch.setattr(config, "get_secret", lambda key: "service-token")
    monkeypatch.setattr(svc, "_resolve_actor_api_key_id", lambda user: "key-1")
    monkeypatch.setattr(svc, "_sign_context_token", lambda **_: "ctx")

    async def raise_http_error(*, method, url, params, content, headers):
        captured["headers"] = dict(headers)
        raise _DummyHttpError("bad gateway")

    svc._client.request = raise_http_error
    req = _request(headers=[(b"x-watchdog-webhook-token", b"hook-1")])

    with pytest.raises(HTTPException, match="Failed to contact Notifier"):
        await svc.forward(
            request=req,
            upstream_path="/foo",
            current_user=_user(),
            require_api_key=False,
            audit_action="jira",
            correlation_id="corr-1",
        )

    assert captured["headers"]["x-watchdog-webhook-token"] == "hook-1"
    assert captured["headers"]["Authorization"] == "Bearer ctx"
    assert audits[-1]["action"] == "jira.error"


@pytest.mark.asyncio
async def test_forward_requires_service_token_and_preserves_scope_header(monkeypatch):
    svc = NotifierProxyService()
    monkeypatch.setattr(config, "get_secret", lambda key: None)

    with pytest.raises(HTTPException, match="service token not configured"):
        await svc.forward(
            request=_request(),
            upstream_path="/foo",
            current_user=None,
            require_api_key=False,
            audit_action="jira",
        )

    captured = {}
    monkeypatch.setattr(config, "get_secret", lambda key: "service-token")
    monkeypatch.setattr(svc, "write_audit", lambda **_: None)

    async def fake_request(*, method, url, params, content, headers):
        captured["headers"] = dict(headers)
        return _DummyResponse()

    svc._client.request = fake_request
    req = _request(headers=[(b"x-scope-orgid", b"tenant-uppercase")])
    req.scope["client"] = None
    response = await svc.forward(
        request=req,
        upstream_path="/foo",
        current_user=None,
        require_api_key=False,
        audit_action="jira",
    )

    assert response.status_code == 200
    normalized_headers = {key.lower(): value for key, value in captured["headers"].items()}
    assert normalized_headers["x-scope-orgid"] == "tenant-uppercase"
    assert captured["headers"]["X-Forwarded-For"] == "unknown"
