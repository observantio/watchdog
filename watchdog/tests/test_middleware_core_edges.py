"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio
import json
import types

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from tests._env import ensure_test_env

ensure_test_env()

from middleware import audit as audit_middleware
from middleware.concurrency_limit import ConcurrencyLimitMiddleware
from middleware.error_handlers import general_exception_handler, handle_route_errors, validation_exception_handler
from middleware.request_size_limit import RequestSizeLimitMiddleware


def _request(path: str = "/", headers: list[tuple[bytes, bytes]] | None = None, scheme: str = "http") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": path,
            "headers": headers or [],
            "client": ("127.0.0.1", 1234),
            "scheme": scheme,
            "query_string": b"token=abc&plain=1",
        }
    )


@pytest.mark.asyncio
async def test_error_handlers_and_json_safe_paths():
    @handle_route_errors(bad_request_detail="bad")
    async def bad_request() -> str:
        raise ValueError("ignored")

    @handle_route_errors(bad_gateway_detail="upstream")
    async def bad_gateway() -> str:
        raise httpx.ReadError("boom")

    @handle_route_errors(internal_detail=None)
    async def raw_internal() -> str:
        raise RuntimeError("raw")

    with pytest.raises(HTTPException) as bad_req_exc:
        await bad_request()
    assert bad_req_exc.value.status_code == 400

    with pytest.raises(HTTPException) as bad_gateway_exc:
        await bad_gateway()
    assert bad_gateway_exc.value.status_code == 502

    with pytest.raises(RuntimeError):
        await raw_internal()

    validation_response = validation_exception_handler(
        _request("/invalid"),
        type("Exc", (), {"errors": lambda self=None: [{"err": ValueError("bad")}]})(),
    )
    assert validation_response.status_code == 422
    detail = json.loads(validation_response.body.decode("utf-8"))["detail"]
    assert detail[0]["err"] == "bad"

    general_response = general_exception_handler(_request("/boom"), RuntimeError("boom"))
    assert general_response.status_code == 500


@pytest.mark.asyncio
async def test_audit_helpers_and_security_headers(monkeypatch):
    assert audit_middleware._skip_resource_view_audit("/api/auth/me") is True
    assert audit_middleware._skip_resource_view_audit("/api/auth/audit-logs/export") is True
    assert audit_middleware._skip_resource_view_audit("/api/tempo/query") is False
    assert audit_middleware._is_sensitive_audit_key("access_token") is True
    assert audit_middleware._is_sensitive_audit_key("status_code") is False
    assert audit_middleware._sanitize_query_string("token=abc&plain=1") == "token=%5BREDACTED%5D&plain=1"

    request = _request(
        "/api/tempo/query",
        headers=[(b"authorization", b"Bearer jwt-token"), (b"x-forwarded-proto", b"https"), (b"user-agent", b"ua")],
    )

    class TokenData:
        tenant_id = "tenant-a"
        user_id = "user-1"

    writes = []
    monkeypatch.setattr(audit_middleware, "client_ip", lambda request: "203.0.113.10")
    monkeypatch.setattr(audit_middleware, "set_request_audit_context", lambda ip, ua: ("ctx",))
    monkeypatch.setattr(audit_middleware, "reset_request_audit_context", lambda token: writes.append(("reset", token)))
    monkeypatch.setattr(audit_middleware.auth_service, "decode_token", lambda token: TokenData())

    async def fake_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(audit_middleware, "run_in_threadpool", fake_run_in_threadpool)
    monkeypatch.setattr(
        audit_middleware,
        "_write_resource_view_audit",
        lambda **kwargs: writes.append(("write", kwargs)),
    )

    async def call_next(_request: Request) -> Response:
        return PlainTextResponse("ok")

    response = await audit_middleware.security_headers_middleware(request, call_next)
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Strict-Transport-Security"].startswith("max-age=")
    assert "script-src" not in response.headers["Content-Security-Policy"]
    assert any(item[0] == "write" for item in writes)
    assert audit_middleware._extract_request_token(request) == "jwt-token"

    monkeypatch.setattr(audit_middleware.auth_service, "decode_token", lambda token: (_ for _ in ()).throw(ValueError("bad token")))
    writes.clear()
    response = await audit_middleware.security_headers_middleware(request, call_next)
    assert response.status_code == 200
    assert all(item[0] != "write" for item in writes)


@pytest.mark.asyncio
async def test_docs_security_headers_allow_swagger_assets(monkeypatch):
    request = _request("/docs")

    monkeypatch.setattr(audit_middleware, "client_ip", lambda request: "203.0.113.10")
    monkeypatch.setattr(audit_middleware, "set_request_audit_context", lambda ip, ua: ("ctx",))
    monkeypatch.setattr(audit_middleware, "reset_request_audit_context", lambda token: None)

    async def call_next(_request: Request) -> Response:
        return PlainTextResponse("ok")

    response = await audit_middleware.security_headers_middleware(request, call_next)
    csp = response.headers["Content-Security-Policy"]
    assert "https://cdn.jsdelivr.net" in csp
    assert "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net" in csp


@pytest.mark.asyncio
async def test_security_headers_skip_audit_when_request_has_no_token(monkeypatch):
    request = _request("/api/tempo/query")
    writes = []

    monkeypatch.setattr(audit_middleware, "client_ip", lambda request: "203.0.113.10")
    monkeypatch.setattr(audit_middleware, "set_request_audit_context", lambda ip, ua: ("ctx",))
    monkeypatch.setattr(audit_middleware, "reset_request_audit_context", lambda token: writes.append(("reset", token)))

    async def fake_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(audit_middleware, "run_in_threadpool", fake_run_in_threadpool)
    monkeypatch.setattr(
        audit_middleware,
        "_write_resource_view_audit",
        lambda **kwargs: writes.append(("write", kwargs)),
    )

    async def call_next(_request: Request) -> Response:
        return PlainTextResponse("ok")

    response = await audit_middleware.security_headers_middleware(request, call_next)
    assert response.status_code == 200
    assert "Strict-Transport-Security" not in response.headers
    assert all(item[0] != "write" for item in writes)


@pytest.mark.asyncio
async def test_security_headers_skip_audit_when_decoded_token_is_empty(monkeypatch):
    request = _request("/api/tempo/query", headers=[(b"authorization", b"Bearer jwt-token")])
    writes = []

    monkeypatch.setattr(audit_middleware, "client_ip", lambda request: "203.0.113.10")
    monkeypatch.setattr(audit_middleware, "set_request_audit_context", lambda ip, ua: ("ctx",))
    monkeypatch.setattr(audit_middleware, "reset_request_audit_context", lambda token: writes.append(("reset", token)))
    monkeypatch.setattr(audit_middleware.auth_service, "decode_token", lambda token: None)

    async def fake_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(audit_middleware, "run_in_threadpool", fake_run_in_threadpool)
    monkeypatch.setattr(
        audit_middleware,
        "_write_resource_view_audit",
        lambda **kwargs: writes.append(("write", kwargs)),
    )

    async def call_next(_request: Request) -> Response:
        return PlainTextResponse("ok")

    response = await audit_middleware.security_headers_middleware(request, call_next)
    assert response.status_code == 200
    assert all(item[0] != "write" for item in writes)


@pytest.mark.asyncio
async def test_request_size_and_concurrency_middleware_paths(monkeypatch):
    sent_messages = []

    async def send(message):
        sent_messages.append(message)

    async def app(scope, receive, send):
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    size_middleware = RequestSizeLimitMiddleware(app, max_bytes=4)

    async def receive_small():
        return {"type": "http.request", "body": b"ok", "more_body": False}

    await size_middleware({"type": "http", "headers": []}, receive_small, send)
    assert sent_messages[0]["status"] == 200

    sent_messages.clear()
    await size_middleware({"type": "http", "headers": [(b"content-length", b"10")]}, receive_small, send)
    assert sent_messages[0]["status"] == 413

    sent_messages.clear()
    body_chunks = iter(
        [
            {"type": "http.request", "body": b"abc", "more_body": True},
            {"type": "http.request", "body": b"de", "more_body": False},
        ]
    )

    async def receive_large():
        return next(body_chunks)

    await size_middleware({"type": "http", "headers": []}, receive_large, send)
    assert sent_messages[0]["status"] == 413

    sent_messages.clear()
    concurrency_middleware = ConcurrencyLimitMiddleware(app, max_concurrent=1, acquire_timeout=0.01)
    await concurrency_middleware({"type": "http", "headers": []}, receive_small, send)
    assert concurrency_middleware._sem is not None

    sent_messages.clear()

    async def timeout_wait_for(awaitable, timeout):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(asyncio, "wait_for", timeout_wait_for)
    await concurrency_middleware({"type": "http", "headers": []}, receive_small, send)
    assert sent_messages[0]["status"] == 503
