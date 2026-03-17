"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import importlib
import os
import sys
import types

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from tests._env import ensure_test_env

ensure_test_env()

from custom_types import json as json_types
from middleware import audit as audit_middleware
from middleware import error_handlers as error_handlers_module
from middleware import resilience as resilience_module
from middleware.concurrency_limit import ConcurrencyLimitMiddleware
from middleware.request_size_limit import RequestSizeLimitMiddleware
from middleware.rate_limit import hybrid as hybrid_module
from middleware.rate_limit import in_memory as memory_module
from middleware.rate_limit import ip as ip_module
from middleware.rate_limit import observability as observability_module
from middleware.rate_limit import redis_fixed_window as redis_module
import middleware.rate_limit as rate_limit_module
from models.internal.otlp_validate import OtlpValidateRequest
from models.observability.agent_models import AgentHeartbeat
from routers import internal_router
from routers.platform import system_router
from services.agent import helpers as agent_helpers
from services.common import cookies as cookie_helpers
from services.common import encryption as encryption_module
from services.secrets.provider import EnvSecretProvider
from services import audit_context as audit_context_service
from services import system_service as system_service_module
from services.system import helpers as system_helpers
from services.tempo import metrics as tempo_metrics
from services.tempo import params as tempo_params
from services.tempo import parsers as tempo_parsers
from services.tempo import promql as tempo_promql
from models.observability.tempo_models import TraceQuery


def _request(
    path: str = "/",
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    client: tuple[str, int] | None = ("127.0.0.1", 1234),
    scheme: str = "http",
) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": path,
            "headers": headers or [],
            "client": client,
            "scheme": scheme,
            "query_string": b"token=abc&plain=1",
        }
    )


def test_json_helpers_and_audit_utility_edges(monkeypatch):
    assert json_types.is_json_value({"items": [1, 2.5, None, {"ok": True}]}) is True
    assert json_types.is_json_value({1: "bad-key"}) is False
    assert json_types.is_json_value(b"bad") is False

    assert audit_middleware._sanitize_query_string("") == ""
    assert audit_middleware._is_https_request(_request(headers=[(b"x-forwarded-proto", b"https")])) is True
    assert audit_middleware._is_https_request(_request()) is False

    response = PlainTextResponse("ok")
    audit_middleware._set_header_if_missing(response.headers, "X-Test", "value")
    audit_middleware._set_header_if_missing(response.headers, "X-Test", "other")
    assert response.headers["X-Test"] == "value"

    cookie_request = _request(headers=[(b"cookie", b"watchdog_token=cookie-token")])
    assert audit_middleware._extract_request_token(cookie_request) == "cookie-token"

    added = []

    @contextmanager
    def fake_get_db_session():
        class FakeDb:
            def add(self, value):
                added.append(value)

        yield FakeDb()

    monkeypatch.setattr(audit_middleware, "get_db_session", fake_get_db_session)
    monkeypatch.setattr(audit_middleware, "AuditLog", lambda **kwargs: kwargs)
    audit_middleware._write_resource_view_audit(
        tenant_id="tenant-a",
        user_id="user-a",
        path="/api/tempo/query",
        method="GET",
        status_code=200,
        raw_query="token=abc&plain=1",
        ip_address="203.0.113.10",
        user_agent="ua",
    )
    assert added == [{
        "tenant_id": "tenant-a",
        "user_id": "user-a",
        "action": "resource.view",
        "resource_type": "http",
        "resource_id": "/api/tempo/query",
        "details": {"method": "GET", "status_code": 200, "query": "token=%5BREDACTED%5D&plain=1"},
        "ip_address": "203.0.113.10",
        "user_agent": "ua",
    }]


@pytest.mark.asyncio
async def test_request_size_and_concurrency_extra_branches(monkeypatch):
    sent = []

    async def send(message):
        sent.append(message)

    async def passthrough_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    concurrency = ConcurrencyLimitMiddleware(passthrough_app, max_concurrent=1, acquire_timeout=0.01)
    await concurrency({"type": "websocket"}, lambda: None, send)
    assert sent[0]["status"] == 204

    sent.clear()
    size_limit = RequestSizeLimitMiddleware(passthrough_app, max_bytes=4)
    await size_limit({"type": "websocket"}, lambda: None, send)
    assert sent[0]["status"] == 204

    warnings = []
    monkeypatch.setattr(audit_middleware.logger if False else importlib.import_module("middleware.request_size_limit").logger, "warning", lambda message, *args: warnings.append((message, args)))

    async def app_with_started_response(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await receive()

    late_limit = RequestSizeLimitMiddleware(app_with_started_response, max_bytes=4)
    chunks = iter([
        {"type": "http.request", "body": b"abcde", "more_body": False},
    ])

    async def receive_large():
        return next(chunks)

    sent.clear()
    await late_limit({"type": "http", "headers": [(b"content-length", b"bad")]}, receive_large, send)
    assert sent == [{"type": "http.response.start", "status": 200, "headers": []}]
    assert warnings[0][0] == "Invalid content-length header value: %r"


def test_rate_limit_primitives_and_ip_edges(monkeypatch):
    assert redis_module._sanitize_redis_url(types.SimpleNamespace()) == "<redis-url>"

    monkeypatch.setattr(redis_module, "import_module", lambda name: (_ for _ in ()).throw(ImportError(name)))
    with pytest.raises(RuntimeError):
        redis_module.RedisFixedWindowRateLimiter("redis://localhost")

    class FakeClient:
        def __init__(self, ping_result=True, count=1):
            self.ping_result = ping_result
            self.count = count

        def ping(self):
            return self.ping_result

        def pipeline(self, transaction=False):
            return types.SimpleNamespace(
                incr=lambda key: None,
                expire=lambda key, ttl: None,
                execute=lambda: (self.count, True),
            )

    class FakeRedisModule:
        def __init__(self, client):
            self.client = client

        def from_url(self, *args, **kwargs):
            return self.client

    monkeypatch.setattr(redis_module, "import_module", lambda name: FakeRedisModule(FakeClient(ping_result=False)))
    with pytest.raises(RuntimeError) as ping_error:
        redis_module.RedisFixedWindowRateLimiter("redis://user:pass@host:6379/0")
    assert "host:6379" in str(ping_error.value)

    monkeypatch.setattr(redis_module, "import_module", lambda name: FakeRedisModule(FakeClient(count=2)))
    limiter = redis_module.RedisFixedWindowRateLimiter("redis://host:6379/0")
    assert limiter.hit("key", limit=0, window_seconds=60).allowed is True
    assert limiter.hit("key", limit=1, window_seconds=0).allowed is True
    blocked = limiter.hit("key", limit=1, window_seconds=60)
    assert blocked.allowed is False
    assert blocked.backend == "redis"

    memory_limiter = memory_module.InMemoryRateLimiter(gc_every=1, stale_after_seconds=1, max_states=1)
    assert memory_limiter._gc_every == 100
    assert memory_limiter._stale_after_seconds == 60
    assert memory_limiter._max_states == 10000
    memory_limiter._states = {
        "stale": hybrid_module.RateLimitHitResult.__mro__ and memory_module.RateLimitState(window_start=1.0, count=1),
    }
    memory_limiter._ops = 99
    monkeypatch.setattr(memory_module.time, "time", lambda: 500.0)
    fresh = memory_limiter.hit("fresh", limit=1, window_seconds=60)
    assert fresh.allowed is True
    assert "stale" not in memory_limiter._states
    assert memory_limiter.hit("fresh", limit=0, window_seconds=60).allowed is True
    assert memory_limiter.hit("fresh", limit=1, window_seconds=0).allowed is True

    tiny = memory_module.InMemoryRateLimiter(gc_every=100, stale_after_seconds=60, max_states=10000)
    tiny._max_states = 1
    tiny._states = {
        "old": memory_module.RateLimitState(window_start=1.0, count=1),
    }
    monkeypatch.setattr(memory_module.time, "time", lambda: 10.0)
    tiny.hit("new", limit=1, window_seconds=60)
    assert "old" not in tiny._states

    fallback_hits = []

    class FallbackLimiter:
        def hit(self, key, *, limit, window_seconds):
            fallback_hits.append((key, limit, window_seconds))
            return hybrid_module.RateLimitHitResult(True, 1, 0, "memory")

    class RedisRaises:
        def __init__(self, exc):
            self.exc = exc

        def hit(self, key, *, limit, window_seconds):
            raise self.exc

    warnings = []
    monkeypatch.setattr(hybrid_module.logger, "warning", lambda message, *args: warnings.append((message, args)))
    fallback_events = []
    monkeypatch.setattr(hybrid_module, "record_fallback_event", lambda mode, reason: fallback_events.append((mode, reason)))
    monkeypatch.setattr(hybrid_module.time, "monotonic", lambda: 100.0)

    limiter = hybrid_module.HybridRateLimiter(RedisRaises(RuntimeError("down")), FallbackLimiter())
    result = limiter.hit("a", limit=2, window_seconds=60, fallback_mode="weird")
    assert result.allowed is True
    assert fallback_hits == [("a", 2, 60)]
    assert fallback_events == [("memory", "RuntimeError")]
    assert warnings[0][0] == "Redis rate limiter unavailable, falling back: %s"

    deny = hybrid_module.HybridRateLimiter(RedisRaises(RuntimeError("down")), FallbackLimiter()).hit(
        "b", limit=2, window_seconds=60, fallback_mode="deny"
    )
    assert deny.allowed is False
    allow = hybrid_module.HybridRateLimiter(RedisRaises(RuntimeError("down")), FallbackLimiter()).hit(
        "c", limit=2, window_seconds=60, fallback_mode="allow"
    )
    assert allow.allowed is True
    assert allow.fallback_used is True

    with pytest.raises(HTTPException):
        hybrid_module.HybridRateLimiter(RedisRaises(HTTPException(status_code=429, detail="stop")), FallbackLimiter()).hit(
            "d", limit=2, window_seconds=60
        )

    monkeypatch.setattr(observability_module.logger, "warning", lambda message, *args: warnings.append((message, args)))
    monkeypatch.setattr(observability_module, "_rate_limit_fallback_total", 0)
    monkeypatch.setattr(observability_module, "_rate_limit_fallback_by_mode", {"memory": 0, "deny": 0, "allow": 0})
    observability_module.record_fallback_event("custom", "manual")
    assert observability_module.get_rate_limit_observability_snapshot() == {
        "fallback_total": 1,
        "fallback_memory": 0,
        "fallback_deny": 0,
        "fallback_allow": 0,
    }

    monkeypatch.setattr(ip_module.config, "TRUST_PROXY_HEADERS", False)
    assert ip_module.client_ip(_request(client=("198.51.100.2", 1234))) == "198.51.100.2"
    assert ip_module.client_ip(_request(client=None)) == "unknown"

    monkeypatch.setattr(ip_module.config, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(ip_module.config, "TRUSTED_PROXY_CIDRS", [])
    assert ip_module.client_ip(_request(headers=[(b"x-real-ip", b"198.51.100.3")], client=("10.0.0.1", 1234))) == "198.51.100.3"

    monkeypatch.setattr(ip_module.config, "TRUSTED_PROXY_CIDRS", ["bad-cidr", "203.0.113.0/24"])
    assert ip_module.client_ip(_request(headers=[(b"x-forwarded-for", b"198.51.100.9")], client=("203.0.113.5", 1234))) == "198.51.100.9"
    assert ip_module.client_ip(_request(headers=[(b"x-forwarded-for", b"bad")], client=("203.0.113.5", 1234))) == "203.0.113.5"
    assert ip_module.client_ip(_request(client=("bad-ip", 1234))) == "unknown"


def test_rate_limit_module_builder_and_enforcers(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "memory")
    monkeypatch.delenv("RATE_LIMIT_REDIS_URL", raising=False)
    built = rate_limit_module._build_rate_limiter()
    assert built._redis_limiter is None

    warnings = []
    infos = []
    monkeypatch.setattr(rate_limit_module.logger, "warning", lambda message, *args: warnings.append((message, args)))
    monkeypatch.setattr(rate_limit_module.logger, "info", lambda message, *args: infos.append((message, args)))
    monkeypatch.setattr(rate_limit_module.config, "IS_PRODUCTION", True)

    monkeypatch.setenv("RATE_LIMIT_BACKEND", "redis")
    monkeypatch.delenv("RATE_LIMIT_REDIS_URL", raising=False)
    built = rate_limit_module._build_rate_limiter()
    assert built._redis_limiter is None

    class FakeRedisLimiter:
        def __init__(self, *args, **kwargs):
            self.args = args

    monkeypatch.setenv("RATE_LIMIT_BACKEND", "auto")
    monkeypatch.setenv("RATE_LIMIT_REDIS_URL", "redis://localhost")
    monkeypatch.setattr(rate_limit_module, "RedisFixedWindowRateLimiter", FakeRedisLimiter)
    built = rate_limit_module._build_rate_limiter()
    assert isinstance(built._redis_limiter, FakeRedisLimiter)
    assert infos[0][0] == "Using Redis-backed rate limiter"

    class FailingRedisLimiter:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("down")

    monkeypatch.setattr(rate_limit_module, "RedisFixedWindowRateLimiter", FailingRedisLimiter)
    built = rate_limit_module._build_rate_limiter()
    assert built._redis_limiter is None
    assert any(message == "Redis rate limiting failed in production; rate limiting is process-local only" for message, _ in warnings)

    class DenyLimiter:
        def hit(self, key, *, limit, window_seconds, fallback_mode=None):
            return rate_limit_module.RateLimitHitResult(False, 0, 7, "memory")

    monkeypatch.setattr(rate_limit_module, "rate_limiter", DenyLimiter())
    with pytest.raises(HTTPException) as exc:
        rate_limit_module.enforce_rate_limit(key="user", limit=1, window_seconds=60)
    assert exc.value.headers["Retry-After"] == "7"

    captured = {}
    monkeypatch.setattr(rate_limit_module, "client_ip", lambda request: "unknown")
    monkeypatch.setattr(
        rate_limit_module,
        "enforce_rate_limit",
        lambda **kwargs: captured.update(kwargs),
    )
    rate_limit_module.enforce_ip_rate_limit(
        _request(headers=[(b"user-agent", b"ua"), (b"x-forwarded-for", b"xf"), (b"x-real-ip", b"xr"), (b"host", b"example")]),
        scope="login",
        limit=3,
        window_seconds=60,
    )
    assert captured["key"].startswith("ip:unknown-")
    assert captured["key"].endswith(":login")


def test_main_startup_initializes_database_and_auth(monkeypatch):
    if "main" in sys.modules:
        del sys.modules["main"]

    import config as config_module
    import database as database_module

    calls = []
    monkeypatch.setattr(config_module.config, "SKIP_STARTUP_DB_INIT", False)
    monkeypatch.setattr(config_module.config, "DATABASE_URL", "postgresql://safeuser:safePass_123@db:5432/watchdog")
    monkeypatch.setattr(config_module.config, "LOG_LEVEL", "debug")
    monkeypatch.setattr(database_module, "init_database", lambda url, debug: calls.append(("init_database", url, debug)))
    monkeypatch.setattr(database_module, "init_db", lambda: calls.append("init_db"))

    import middleware.dependencies as dependencies_module

    fake_auth_service = types.SimpleNamespace(
        _lazy_init=lambda: calls.append("lazy_init"),
        backfill_otlp_tokens=lambda: calls.append("backfill_otlp_tokens"),
    )
    monkeypatch.setattr(dependencies_module, "auth_service", fake_auth_service)

    importlib.import_module("main")

    assert calls == [
        ("init_database", "postgresql://safeuser:safePass_123@db:5432/watchdog", True),
        "init_db",
        "lazy_init",
        "backfill_otlp_tokens",
    ]


@pytest.mark.asyncio
async def test_system_helpers_cookie_security_secret_provider_and_agent_edges(monkeypatch):
    errors = []
    warnings = []
    monkeypatch.setattr(system_helpers.logger, "error", lambda message, *args: errors.append((message, args)))
    monkeypatch.setattr(system_service_module.logger, "warning", lambda message, *args: warnings.append((message, args)))

    class BrokenProc:
        def cpu_percent(self, interval=None):
            raise RuntimeError("cpu")

        def memory_info(self):
            raise RuntimeError("mem")

        def io_counters(self):
            raise RuntimeError("io")

        def connections(self, kind="inet"):
            raise RuntimeError("net")

    assert system_helpers.cpu_metrics(BrokenProc()) == {
        "utilization": 0,
        "raw_utilization": 0,
        "count": 0,
        "threads": 0,
        "frequency_mhz": None,
    }
    assert system_helpers.memory_metrics(BrokenProc()) == {"rss_mb": 0, "vms_mb": 0, "utilization": 0}
    assert system_helpers.disk_metrics(BrokenProc()) == {
        "read_mb": 0,
        "write_mb": 0,
        "read_count": 0,
        "write_count": 0,
    }
    assert system_helpers.network_metrics(BrokenProc()) == {
        "total_connections": 0,
        "established": 0,
        "listen": 0,
        "time_wait": 0,
        "close_wait": 0,
    }
    assert len(errors) == 4

    assert system_helpers.determine_stress_status(30, 55, 60)["status"] == "moderate"
    assert system_helpers.determine_stress_status(5, 10, 1)["status"] == "healthy"

    class PrimingProcess:
        def cpu_percent(self, interval=None):
            raise system_service_module.psutil.Error("prime")

    monkeypatch.setattr(system_service_module.psutil, "Process", lambda pid: PrimingProcess())
    service = system_service_module.SystemService()
    assert warnings[0][0].startswith("Unable to prime CPU percent")
    assert system_service_module._float_value(True) == 1.0
    assert system_service_module._float_value("bad") == 0.0
    assert system_service_module._int_value(True) == 1
    assert system_service_module._int_value(2.7) == 2
    assert system_service_module._int_value("bad") == 0

    monkeypatch.setattr(service, "get_cpu_metrics", lambda: {"utilization": True})
    monkeypatch.setattr(service, "get_memory_metrics", lambda: {"utilization": "bad"})
    monkeypatch.setattr(service, "get_disk_metrics", lambda: {"io": True})
    monkeypatch.setattr(service, "get_network_metrics", lambda: {"total_connections": 2.9})
    monkeypatch.setattr(service, "determine_stress_status", lambda cpu, memory, connections: {"cpu": cpu, "memory": memory, "connections": connections})
    assert service.get_all_metrics()["stress"] == {"cpu": 1.0, "memory": 0.0, "connections": 2}

    assert cookie_helpers._parse_networks(["127.0.0.0/8"])
    assert cookie_helpers.is_secure_cookie_request(_request(), trust_proxy_headers=False) is False
    assert cookie_helpers.is_secure_cookie_request(_request(headers=[(b"x-forwarded-proto", b"https")]), trust_proxy_headers=True) is False
    assert cookie_helpers.is_secure_cookie_request(_request(client=None), trust_proxy_headers=True, trusted_proxy_cidrs=["127.0.0.0/8"]) is False
    assert cookie_helpers.is_secure_cookie_request(_request(client=("bad-ip", 1)), trust_proxy_headers=True, trusted_proxy_cidrs=["127.0.0.0/8"]) is False
    assert cookie_helpers.is_secure_cookie_request(_request(client=("203.0.113.10", 1)), trust_proxy_headers=True, trusted_proxy_cidrs=["127.0.0.0/8"]) is False
    assert cookie_helpers.is_secure_cookie_request(
        _request(headers=[(b"x-forwarded-proto", b"https")], client=("127.0.0.2", 1)),
        trust_proxy_headers=True,
        trusted_proxy_cidrs=["127.0.0.0/8"],
    ) is True
    monkeypatch.setattr(cookie_helpers.config, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(cookie_helpers.config, "TRUSTED_PROXY_CIDRS", ["127.0.0.0/8"])
    assert cookie_helpers.cookie_secure(_request(headers=[(b"x-forwarded-proto", b"https")], client=("127.0.0.2", 1))) is True

    monkeypatch.setenv("EMPTY_SECRET", "")
    monkeypatch.setenv("FILLED_SECRET", "value")
    provider = EnvSecretProvider()
    assert provider.get("EMPTY_SECRET") is None
    assert provider.get_many(["EMPTY_SECRET", "FILLED_SECRET"]) == {"EMPTY_SECRET": None, "FILLED_SECRET": "value"}

    registry = {}
    heartbeat = AgentHeartbeat(name="agent-a", tenant_id="tenant-a", attributes={"host.hostname": "host-a"}, signal=None)
    agent_helpers.update_agent_registry(registry, heartbeat)
    assert registry["tenant-a:agent-a"].host_name == "host-a"
    duplicate = AgentHeartbeat(name="agent-a", tenant_id="tenant-a", attributes={}, signal="metrics")
    agent_helpers.update_agent_registry(registry, duplicate)
    agent_helpers.update_agent_registry(registry, duplicate)
    assert registry["tenant-a:agent-a"].signals == ["metrics"]
    assert agent_helpers.make_agent_id("agent-b", "") == "agent-b"
    assert agent_helpers.extract_metrics_count({"data": {"result": [{}]}}) == 0
    assert agent_helpers.extract_metrics_count({"data": {"result": ["bad"]}}) == 0
    assert agent_helpers.extract_metrics_count({"data": {"result": [{"value": [0]}]}}) == 0
    assert agent_helpers.extract_metrics_count({"data": {"result": [{"value": [0, object()]}]}}) == 0
    assert agent_helpers.extract_metrics_count({"data": []}) == 0

    class BadResponse:
        def raise_for_status(self):
            raise httpx.HTTPError("boom")

    class BadClient:
        async def get(self, url, params=None, headers=None):
            return BadResponse()

    result = await agent_helpers.query_key_activity("tenant-a", BadClient())
    assert result == {"metrics_active": False, "metrics_count": 0}

    class BadPayloadResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return ["not-a-dict"]

    class BadPayloadClient:
        async def get(self, url, params=None, headers=None):
            return BadPayloadResponse()

    bad_payload_result = await agent_helpers.query_key_activity("tenant-a", BadPayloadClient())
    assert bad_payload_result == {"metrics_active": False, "metrics_count": 0}

    tokens = audit_context_service.set_request_audit_context("203.0.113.10", "pytest")
    assert audit_context_service.get_request_audit_context() == ("203.0.113.10", "pytest")
    audit_context_service.reset_request_audit_context(tokens)
    assert audit_context_service.get_request_audit_context() == (None, None)


@pytest.mark.asyncio
async def test_internal_and_system_router_edges(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await internal_router.validate_otlp_token_post(OtlpValidateRequest(token=" "), None)
    assert exc.value.status_code == 400

    monkeypatch.setattr(system_router, "system_service", types.SimpleNamespace(get_all_metrics=lambda: {"ok": True}))
    assert await system_router.get_system_metrics() == {"ok": True}


def test_encryption_edges(monkeypatch):
    encryption_module._get_fernet.cache_clear()
    monkeypatch.setattr(encryption_module.app_config, "DATA_ENCRYPTION_KEY", None)
    with pytest.raises(RuntimeError, match="DATA_ENCRYPTION_KEY is not configured"):
        encryption_module._get_fernet()

    encryption_module._get_fernet.cache_clear()
    monkeypatch.setattr(encryption_module.app_config, "DATA_ENCRYPTION_KEY", "bad-key")
    with pytest.raises(RuntimeError, match="Invalid DATA_ENCRYPTION_KEY format"):
        encryption_module._get_fernet()

    key = Fernet.generate_key().decode()
    encryption_module._get_fernet.cache_clear()
    monkeypatch.setattr(encryption_module.app_config, "DATA_ENCRYPTION_KEY", key)
    encrypted = encryption_module.encrypt_config({"name": "svc", "count": 2})
    assert list(encrypted) == ["__encrypted__", "__v"]
    assert encryption_module.decrypt_config(encrypted) == {"name": "svc", "count": 2}
    assert encryption_module.decrypt_config({"plain": True}) == {"plain": True}
    with pytest.raises(ValueError, match="payload must be a string"):
        encryption_module.decrypt_config({"__encrypted__": 123})

    encryption_module._get_fernet.cache_clear()
    monkeypatch.setattr(encryption_module.app_config, "DATA_ENCRYPTION_KEY", Fernet.generate_key().decode())
    with pytest.raises(ValueError, match="wrong key or corrupted data"):
        encryption_module.decrypt_config(encrypted)

    class BrokenFernet:
        def encrypt(self, payload):
            raise TypeError("boom")

        def decrypt(self, payload):
            raise TypeError("boom")

    monkeypatch.setattr(encryption_module, "_get_fernet", lambda: BrokenFernet())
    with pytest.raises(ValueError, match="Failed to encrypt channel config"):
        encryption_module.encrypt_config({"x": 1})
    with pytest.raises(ValueError, match="Failed to decrypt channel config"):
        encryption_module.decrypt_config({"__encrypted__": "value"})


@pytest.mark.asyncio
async def test_resilience_edges(monkeypatch):
    request = httpx.Request("GET", "https://example.test")
    response_404 = httpx.Response(404, request=request)
    response_429 = httpx.Response(429, request=request)
    assert resilience_module._is_retriable_httpx(httpx.HTTPStatusError("no-response", request=request, response=None)) is True
    assert resilience_module._is_retriable_httpx(httpx.HTTPStatusError("not-found", request=request, response=response_404)) is False
    assert resilience_module._is_retriable_httpx(httpx.HTTPStatusError("limited", request=request, response=response_429)) is True
    assert resilience_module._is_retriable_httpx(httpx.ReadTimeout("slow", request=request)) is True
    assert resilience_module._is_retriable_httpx(ValueError("bad")) is False

    monkeypatch.setattr(resilience_module.random, "uniform", lambda low, high: high)
    assert resilience_module._backoff_delay(2, 0.5, 1.0, 0.5) == 1.5
    assert resilience_module._backoff_delay(1, -1.0, 2.0, -0.5) == 0.0

    sleeps = []
    original_sleep = asyncio.sleep

    async def fake_sleep(delay):
        sleeps.append(delay)
        await original_sleep(0)

    monkeypatch.setattr(resilience_module.asyncio, "sleep", fake_sleep)

    attempts = {"count": 0}

    @resilience_module.with_retry(max_retries=2, backoff=0.25, max_backoff=1.0, jitter=0.0, retriable=lambda exc: True)
    async def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("retry")
        return "ok"

    assert await flaky() == "ok"
    assert sleeps == [0.25, 0.5]

    sleeps.clear()

    @resilience_module.with_retry(max_retries=1, backoff=0.1, retriable=lambda exc: False)
    async def non_retriable():
        raise RuntimeError("stop")

    with pytest.raises(RuntimeError, match="stop"):
        await non_retriable()
    assert sleeps == []

    logged = []
    monkeypatch.setattr(resilience_module.logger, "error", lambda message, *args: logged.append((message, args)))

    @resilience_module.with_retry(max_retries=1, backoff=0.1, jitter=0.0, retriable=lambda exc: True)
    async def exhausted():
        raise RuntimeError("still bad")

    with pytest.raises(RuntimeError, match="still bad"):
        await exhausted()
    assert logged[0][0] == "Retry exhausted: fn=%s attempts=%d last_error=%r"

    async def fake_wait_for(coro, timeout):
        await coro
        raise asyncio.TimeoutError()

    monkeypatch.setattr(resilience_module.asyncio, "wait_for", fake_wait_for)

    @resilience_module.with_timeout(timeout=0.01)
    async def too_slow():
        return "never"

    with pytest.raises(asyncio.TimeoutError):
        await too_slow()
    assert logged[-1][0] == "Timeout: fn=%s timeout=%.3fs"


@pytest.mark.asyncio
async def test_tempo_utility_edges(monkeypatch):
    observed = []

    class ListPayloadClient:
        async def get(self, url, params=None, headers=None):
            assert params == {"query": "sum(rate(x[5m]))", "step": 60}
            assert headers == {"X-Test": "tenant-a"}

            class Response:
                def raise_for_status(self):
                    return None

                def json(self):
                    return ["bad"]

            return Response()

    payload, enabled = await tempo_metrics.query_metrics_range(
        client=ListPayloadClient(),
        promql="sum(rate(x[5m]))",
        start_us=0,
        end_us=0,
        step_s=60,
        tenant_id="tenant-a",
        mimir_url="http://mimir/",
        get_headers=lambda tenant_id: {"X-Test": tenant_id},
        observe=lambda metric, value: observed.append((metric, value)),
        metrics_enabled=True,
    )
    assert enabled is True
    assert payload == {"status": "error", "data": {"result": []}}
    assert observed == [("tempo_metrics_queries_total", 1.0)]

    class ErrorClient:
        async def get(self, url, params=None, headers=None):
            raise httpx.ReadError("boom")

    payload, enabled = await tempo_metrics.query_metrics_range(
        client=ErrorClient(),
        promql="x",
        start_us=1,
        end_us=2,
        observe=lambda metric, value: observed.append((metric, value)),
        metrics_enabled=True,
    )
    assert enabled is False
    assert payload == {"status": "error", "data": {"result": []}}
    assert observed[-1] == ("tempo_metrics_query_errors_total", 1.0)

    assert tempo_metrics.extract_metric_values(None) == []
    assert tempo_metrics.extract_metric_values({"data": {"result": []}}) == []
    assert tempo_metrics.extract_metric_values({"data": {"result": [{"values": [["bad", "2"], [1, "3.9"], [1, "2"]]}]}}) == [[1, "5"]]

    query = TraceQuery(
        limit=5,
        service="svc name",
        operation="op",
        tags={"quoted": 'a "b"', "path": "c\\d"},
        max_duration="50ms",
    )
    built = tempo_params.build_search_params(query)
    assert built["tags"] == 'service.name="svc name" name=op quoted="a \\"b\\"" path=c\\\\d'
    assert built["maxDuration"] == "50ms"

    assert tempo_promql.build_promql_selectors(None) == ["{}"]
    assert tempo_promql.build_promql_selectors('svc"x')[-1] == '{service.name="svc\\"x"}'
    assert tempo_promql.build_count_promql("svc", 30, label_variant=99) == 'sum(count_over_time({service.name="svc"}[30s]))'

    assert tempo_parsers._json_dict([]) == {}
    assert tempo_parsers._json_dict_list({}) == []
    assert tempo_parsers._int_value(True) == 1
    assert tempo_parsers._int_value(2.8) == 2
    assert tempo_parsers._int_value("bad") == 0

    attrs = tempo_parsers.parse_attributes([
        {"key": "", "value": {"stringValue": "skip"}},
        {"key": "ok", "value": {"boolValue": True}},
        {"key": "missing", "value": "bad"},
    ])
    assert attrs == {"ok": True}

    span = tempo_parsers.parse_span(
        {"spanId": 7, "name": 8, "startTimeUnixNano": 5000.4, "endTimeUnixNano": True, "parentSpanId": "", "attributes": []},
        "trace-a",
        "proc-a",
        "svc-a",
        {"resource.attr": "x"},
    )
    assert span.span_id == ""
    assert span.operation_name == ""
    assert span.parent_span_id is None
    assert span.service_name == "svc-a"
    assert span.attributes["service.name"] == "svc-a"
    assert span.attributes["resource.attr"] == "x"
    assert span.duration == -5

    trace = tempo_parsers.parse_tempo_trace(
        "trace-b",
        {
            "batches": [
                {
                    "resource": {"attributes": [{"key": "serviceName", "value": {"intValue": 9}}]},
                    "scopeSpans": [{"spans": [{"spanId": "s", "name": "op", "startTimeUnixNano": "1000", "endTimeUnixNano": "3000"}]}],
                }
            ]
        },
    )
    assert trace.processes == {"9": {"serviceName": "9", "resource": {"attributes": [{"key": "serviceName", "value": {"intValue": 9}}]}, "attributes": {"serviceName": 9}}}

    summary = tempo_parsers.build_summary_trace({"traceID": "tx", "rootServiceName": 123, "rootTraceName": object()})
    assert summary is not None
    assert summary.spans[0].service_name == "unknown"
    assert summary.spans[0].operation_name == ""
    assert summary.spans[0].start_time == 0
    assert summary.spans[0].duration == 0


@pytest.mark.asyncio
async def test_error_handler_and_small_helper_edges(monkeypatch):
    @error_handlers_module.handle_route_errors(internal_detail="hidden")
    async def raises_http_exception():
        raise HTTPException(status_code=418, detail="teapot")

    @error_handlers_module.handle_route_errors(internal_detail="hidden")
    async def raises_internal_error():
        raise RuntimeError("boom")

    with pytest.raises(HTTPException) as passthrough:
        await raises_http_exception()
    assert passthrough.value.status_code == 418

    with pytest.raises(HTTPException) as internal:
        await raises_internal_error()
    assert internal.value.status_code == 500
    assert internal.value.detail == "hidden"

    monkeypatch.setattr(ip_module.config, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(ip_module.config, "TRUSTED_PROXY_CIDRS", ["127.0.0.0/8"])
    assert ip_module.client_ip(_request(client=("127.0.0.1", 1), headers=[(b"x-forwarded-for", b"198.51.100.4")])) == "198.51.100.4"

    monkeypatch.setattr(ip_module, "_valid_ip", lambda value: (value or "").strip() or None)
    monkeypatch.setattr(ip_module, "ip_address", lambda value: (_ for _ in ()).throw(ValueError("bad ip")))
    assert ip_module.client_ip(_request(client=("198.51.100.8", 1))) == "198.51.100.8"

    encryption_module._get_fernet.cache_clear()
    monkeypatch.setattr(encryption_module.app_config, "DATA_ENCRYPTION_KEY", None)
    with pytest.raises(RuntimeError, match="DATA_ENCRYPTION_KEY is not configured"):
        encryption_module.encrypt_config({"name": "svc"})
    with pytest.raises(RuntimeError, match="DATA_ENCRYPTION_KEY is not configured"):
        encryption_module.decrypt_config({"__encrypted__": "abc"})

    assert system_helpers.determine_stress_status(20, 85, 120)["issues"] == [
        "High memory usage (85%)",
        "High connection count (120)",
    ]

    service = system_service_module.SystemService()
    monkeypatch.setattr(system_service_module, "disk_metrics", lambda process: {"disk": process})
    monkeypatch.setattr(system_service_module, "network_metrics", lambda process: {"network": process})
    assert service.get_disk_metrics() == {"disk": service.process}
    assert service.get_network_metrics() == {"network": service.process}
    assert system_service_module._int_value(4) == 4

    class MissingKeyDict(dict):
        def get(self, key, default=None):
            if key == "startTimeUnixNano":
                return 1
            if key == "durationMs":
                return 2
            return super().get(key, default)

        def __getitem__(self, key):
            raise KeyError(key)

    assert tempo_parsers._int_value(object()) == 0
    summary = tempo_parsers.build_summary_trace(MissingKeyDict({"traceID": "tz"}))
    assert summary is not None
    assert summary.spans[0].start_time == 0
    assert summary.spans[0].duration == 0