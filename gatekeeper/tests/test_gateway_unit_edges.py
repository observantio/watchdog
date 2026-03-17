"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import importlib
import itertools
import os
import runpy
import sys
import types

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

import config as gw_config
import main as gateway_main
from routers import gateway_router
from services import gateway_service as gateway_service_module
from services.gateway_service import DatabaseUnavailable, GatewayAuthService
from services.rate_limit import make_default_rate_limiter
from services.rate_limits.hybrid_token_rate_limiter import HybridTokenRateLimiter
from services.rate_limits.redis_token_rate_limiter import RedisTokenRateLimiter
from services.rate_limits.token_rate_limiter import TokenRateLimiter
from services.secrets.provider import EnvSecretProvider
from services.token_cache.memory import GC_INTERVAL, TokenCache
from services.token_cache.redis import RedisTokenCache
from services.secrets import vault_client as vault_module


def _request(
    client_host: str = "127.0.0.1",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/api/gateway/validate",
        "headers": headers or [],
        "client": (client_host, 1234),
        "scheme": "http",
        "query_string": b"",
    }
    return Request(scope)


def test_config_helpers_and_env_provider(tmp_path):
    assert gw_config._to_bool(None, default=True) is True
    assert gw_config._to_bool("yes") is True
    assert gw_config._to_bool("off") is False
    assert gw_config._is_weak_secret("") is True
    assert gw_config._is_weak_secret("replace_with_token") is True
    assert gw_config._is_weak_secret("strong-token-123") is False
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("value-from-file\n", encoding="utf-8")
    assert gw_config._read_secret_id_file(str(secret_file)) == "value-from-file"
    os.environ["TEST_SECRET"] = "abc"
    assert EnvSecretProvider().get("TEST_SECRET") == "abc"
    assert EnvSecretProvider().get_many(["TEST_SECRET", "MISSING"]) == {
        "TEST_SECRET": "abc",
        "MISSING": None,
    }


def test_build_secret_provider_defaults_to_env(monkeypatch):
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    provider = gw_config.build_secret_provider()
    assert isinstance(provider, EnvSecretProvider)


def test_build_secret_provider_uses_secret_id_file(monkeypatch, tmp_path):
    secret_file = tmp_path / "sid.txt"
    secret_file.write_text("sid-123\n", encoding="utf-8")
    captured = {}

    class FakeProvider:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("VAULT_ADDR", "https://vault")
    monkeypatch.setenv("VAULT_ROLE_ID", "role-1")
    monkeypatch.setenv("VAULT_SECRET_ID_FILE", str(secret_file))
    monkeypatch.delenv("VAULT_SECRET_ID", raising=False)
    monkeypatch.setattr(gw_config, "VaultSecretProvider", FakeProvider)
    provider = gw_config.build_secret_provider()
    assert isinstance(provider, FakeProvider)
    assert captured["address"] == "https://vault"
    assert captured["role_id"] == "role-1"
    assert captured["secret_id_fn"]() == "sid-123"


def test_build_secret_provider_uses_secret_id_env(monkeypatch):
    captured = {}

    class FakeProvider:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("VAULT_ADDR", "https://vault")
    monkeypatch.setenv("VAULT_ROLE_ID", "role-1")
    monkeypatch.setenv("VAULT_SECRET_ID", "secret-1")
    monkeypatch.delenv("VAULT_SECRET_ID_FILE", raising=False)
    monkeypatch.setattr(gw_config, "VaultSecretProvider", FakeProvider)
    provider = gw_config.build_secret_provider()
    assert isinstance(provider, FakeProvider)
    assert captured["secret_id_fn"]() == "secret-1"


def test_build_secret_provider_rejects_missing_secret_id(monkeypatch):
    monkeypatch.setenv("VAULT_ADDR", "https://vault")
    monkeypatch.setenv("VAULT_ROLE_ID", "role-1")
    monkeypatch.delenv("VAULT_SECRET_ID", raising=False)
    monkeypatch.delenv("VAULT_SECRET_ID_FILE", raising=False)
    with pytest.raises(gw_config.VaultClientError):
        gw_config.build_secret_provider()


def test_parse_networks_and_http_verify(monkeypatch):
    assert [str(net) for net in gateway_service_module._parse_networks("127.0.0.1,2001:db8::1")]
    monkeypatch.setattr(gateway_service_module.gw_config, "AUTH_API_URL", "http://auth")
    assert gateway_service_module._http_verify_setting() is False
    monkeypatch.setattr(gateway_service_module.gw_config, "AUTH_API_URL", "https://auth")
    monkeypatch.setattr(gateway_service_module.gw_config, "SSL_CA_CERTS", "/tmp/ca.pem")
    assert gateway_service_module._http_verify_setting() == "/tmp/ca.pem"
    monkeypatch.setattr(gateway_service_module.gw_config, "SSL_CA_CERTS", "")
    monkeypatch.setattr(gateway_service_module.gw_config, "SSL_VERIFY", False)
    assert gateway_service_module._http_verify_setting() is False


def test_trusted_proxy_helpers(monkeypatch):
    monkeypatch.setattr(gateway_service_module.gw_config, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(gateway_service_module.gw_config, "TRUSTED_PROXY_CIDRS", ["127.0.0.0/8"])
    proxied = _request(
        headers=[(b"x-forwarded-for", b"198.51.100.10, 127.0.0.1")],
    )
    assert GatewayAuthService._trusted_proxy_peer(proxied) is True
    assert GatewayAuthService._client_ip(proxied) == "198.51.100.10"
    proxied_real_ip = _request(
        headers=[(b"x-real-ip", b"198.51.100.11")],
    )
    assert GatewayAuthService._client_ip(proxied_real_ip) == "198.51.100.11"
    untrusted = _request(client_host="not-an-ip")
    assert GatewayAuthService._trusted_proxy_peer(untrusted) is False
    monkeypatch.setattr(gateway_service_module.gw_config, "TRUST_PROXY_HEADERS", False)
    assert GatewayAuthService._client_ip(_request(client_host="198.51.100.12")) == "198.51.100.12"


def test_extract_otlp_token_and_headers(monkeypatch):
    monkeypatch.setattr(gateway_service_module.gw_config, "INTERNAL_SERVICE_TOKEN", "internal-token")
    assert GatewayAuthService.extract_otlp_token("  abc  ") == "abc"
    assert GatewayAuthService.extract_otlp_token(None) == ""
    assert GatewayAuthService._auth_request_headers() == {"X-Internal-Token": "internal-token"}
    assert GatewayAuthService._auth_request_headers("tok") == {
        "X-Internal-Token": "internal-token",
        "X-OTLP-Token": "tok",
        "Content-Type": "application/json",
    }


def test_extract_org_id_handles_invalid_payloads():
    class Response:
        def __init__(self, payload=None, error=False):
            self._payload = payload
            self._error = error

        def json(self):
            if self._error:
                raise ValueError("bad json")
            return self._payload

    assert GatewayAuthService._extract_org_id(Response(error=True)) is None
    assert GatewayAuthService._extract_org_id(Response(["not-dict"])) is None
    assert GatewayAuthService._extract_org_id(Response({"org_id": "  org-1  "})) == "org-1"
    assert GatewayAuthService._extract_org_id(Response({"org_id": ""})) is None


def test_fetch_org_from_api_variants(monkeypatch):
    service = GatewayAuthService(rate_limit_per_minute=10, ip_allowlist="127.0.0.1")
    calls = []

    class FakeResponse:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self._payload = payload if payload is not None else {}

        def json(self):
            return self._payload

    class FakeClient:
        response = FakeResponse(200, {"org_id": "org-1"})
        error = None

        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers=None, json=None):
            if self.error is not None:
                raise self.error
            self.last_post = (url, headers, json)
            return self.response

        def get(self, url, headers=None):  # pragma: no cover
            if self.error is not None:
                raise self.error  # pragma: no cover
            self.last_get = (url, headers)  # pragma: no cover
            return self.response  # pragma: no cover

    monkeypatch.setattr(gateway_service_module.httpx, "Client", FakeClient)
    assert service._fetch_org_from_api("tok") == "org-1"
    FakeClient.response = FakeResponse(404)
    assert service._fetch_org_from_api("tok") is None
    FakeClient.response = FakeResponse(405)
    monkeypatch.setattr(GatewayAuthService, "_fetch_org_from_api_legacy_query", lambda self, token: f"legacy:{token}")
    assert service._fetch_org_from_api("tok") == "legacy:tok"
    FakeClient.response = FakeResponse(500)
    with pytest.raises(DatabaseUnavailable):
        service._fetch_org_from_api("tok")
    FakeClient.error = httpx.ReadTimeout("timeout")
    with pytest.raises(DatabaseUnavailable):
        service._fetch_org_from_api("tok")
    assert calls


def test_fetch_org_from_api_legacy_query_variants(monkeypatch):
    service = GatewayAuthService(rate_limit_per_minute=10, ip_allowlist="127.0.0.1")

    class FakeResponse:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self._payload = payload if payload is not None else {}

        def json(self):
            return self._payload

    class FakeClient:
        response = FakeResponse(200, {"org_id": "org-2"})
        error = None

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers=None):
            if self.error is not None:
                raise self.error
            self.url = url
            self.headers = headers
            return self.response

    monkeypatch.setattr(gateway_service_module.httpx, "Client", FakeClient)
    assert service._fetch_org_from_api_legacy_query("t ok") == "org-2"
    FakeClient.response = FakeResponse(410)
    assert service._fetch_org_from_api_legacy_query("tok") is None
    FakeClient.response = FakeResponse(500)
    with pytest.raises(DatabaseUnavailable):
        service._fetch_org_from_api_legacy_query("tok")
    FakeClient.error = httpx.ConnectError("boom")
    with pytest.raises(DatabaseUnavailable):
        service._fetch_org_from_api_legacy_query("tok")


def test_validate_otlp_token_handles_empty_and_unexpected_exceptions(monkeypatch):
    service = GatewayAuthService(rate_limit_per_minute=10, ip_allowlist="127.0.0.1")
    assert service.validate_otlp_token("") is None

    class WeirdFailure(Exception):
        pass

    def boom(self, token):
        raise WeirdFailure("nope")

    monkeypatch.setattr(GatewayAuthService, "_fetch_org_from_api", boom)
    with pytest.raises(DatabaseUnavailable):
        service.validate_otlp_token("tok")


@pytest.mark.asyncio
async def test_gateway_router_paths(monkeypatch):
    monkeypatch.setattr(GatewayAuthService, "enforce_ip_allowlist", lambda self, request: None)
    monkeypatch.setattr(GatewayAuthService, "enforce_rate_limit", lambda self, request: None)
    monkeypatch.setattr(GatewayAuthService, "validate_otlp_token", lambda self, token: "tenant-1")
    request = _request(headers=[(b"x-otlp-token", b"tok")])
    response = await gateway_router.validate_otlp_token(request)
    assert response.status_code == 200
    assert response.headers["X-Scope-OrgID"] == "tenant-1"
    assert await gateway_router.health() == gateway_router.service.health()

    monkeypatch.setattr(GatewayAuthService, "validate_otlp_token", lambda self, token: None)
    with pytest.raises(HTTPException) as exc:
        await gateway_router.validate_otlp_token(request)
    assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as missing:
        await gateway_router.validate_otlp_token(_request())
    assert missing.value.status_code == 401


@pytest.mark.asyncio
async def test_gateway_main_health_and_main_entrypoint(monkeypatch):
    assert await gateway_main.health_root() == {"status": "healthy", "service": "gateway-auth-service"}

    captured = {}
    fake_uvicorn = types.SimpleNamespace(run=lambda **kwargs: captured.update(kwargs))
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.setenv("GATEWAY_SSL_CERTFILE", "/tmp/cert.pem")
    monkeypatch.setenv("GATEWAY_SSL_KEYFILE", "/tmp/key.pem")
    monkeypatch.setenv("GATEWAY_SSL_CA_CERTS", "/tmp/ca.pem")
    monkeypatch.setenv("GATEWAY_HOST", "0.0.0.0")
    monkeypatch.setenv("GATEWAY_PORT", "4321")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    config_module = importlib.import_module("config")
    importlib.reload(config_module)
    runpy.run_module("main", run_name="__main__")
    assert captured["host"] == "0.0.0.0"
    assert captured["ssl_certfile"] == "/tmp/cert.pem"
    assert captured["ssl_keyfile"] == "/tmp/key.pem"
    assert captured["ssl_ca_certs"] == "/tmp/ca.pem"


def test_gateway_service_remaining_branches(monkeypatch):
    monkeypatch.setattr(gateway_service_module.gw_config, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(gateway_service_module.gw_config, "TRUSTED_PROXY_CIDRS", [])
    proxied = _request(headers=[(b"x-forwarded-for", b"  "), (b"x-real-ip", b"198.51.100.20")])
    assert GatewayAuthService._trusted_proxy_peer(proxied) is True
    assert GatewayAuthService._client_ip(proxied) == "198.51.100.20"
    assert GatewayAuthService._client_ip(Request({"type": "http", "headers": [], "scheme": "http", "path": "/", "query_string": b""})) == "unknown"

    service = GatewayAuthService(rate_limit_per_minute=10, ip_allowlist="127.0.0.1")
    class FakeNamedDatabaseUnavailable(Exception):
        pass
    FakeNamedDatabaseUnavailable.__name__ = "DatabaseUnavailable"

    monkeypatch.setattr(GatewayAuthService, "_fetch_org_from_api", lambda self, token: (_ for _ in ()).throw(FakeNamedDatabaseUnavailable("same-name")))
    with pytest.raises(FakeNamedDatabaseUnavailable):
        service.validate_otlp_token("tok")


def test_rate_limit_remaining_branches(monkeypatch):
    import services.rate_limit as rate_limit_module
    import services.rate_limits.hybrid_token_rate_limiter as hybrid_module

    monkeypatch.setattr(rate_limit_module.gw_config, "GATEWAY_RATE_LIMIT_STRICT", True)

    class WorkingRedisLimiter:
        def __init__(self, *args, **kwargs):
            self.args = args

    monkeypatch.setattr(rate_limit_module, "RedisTokenRateLimiter", WorkingRedisLimiter)
    limiter = rate_limit_module.make_default_rate_limiter(5, backend="redis", redis_url="redis://localhost")
    assert isinstance(limiter, WorkingRedisLimiter)

    class ExplodingPrimary:
        def enforce(self, key):
            raise RuntimeError("boom")

    class RecordingFallback:
        def __init__(self):
            self.calls = 0

        def enforce(self, key):
            self.calls += 1

    fallback = RecordingFallback()
    limiter = HybridTokenRateLimiter(ExplodingPrimary(), fallback)
    monkeypatch.setattr(hybrid_module.time, "monotonic", lambda: 31.0)
    limiter.enforce("x")
    assert fallback.calls == 1


def test_vault_provider_remaining_branches(monkeypatch):
    class FakeAppRole:
        def login(self, role_id=None, secret_id=None):
            return {"auth": {"client_token": "role-token"}}  # pragma: no cover

    class FakeKV:
        def __init__(self):
            self.v2 = self

        def read_secret_version(self, **kwargs):
            return {"data": {"data": {"value": "ok"}}}  # pragma: no cover

        def read_secret(self, **kwargs):
            return {"data": {"key": "value"}}  # pragma: no cover

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.auth = types.SimpleNamespace(approle=FakeAppRole())
            self.secrets = types.SimpleNamespace(kv=FakeKV())
            self.token = None
            self.authenticated = True

        def is_authenticated(self):
            return self.authenticated

    monkeypatch.setattr(vault_module, "hvac", types.SimpleNamespace(Client=FakeClient))
    provider = vault_module.VaultSecretProvider(address="https://vault", token="token", cache_ttl=100)
    provider._cache["bad"] = "invalid"
    assert provider._from_cache("bad") is vault_module.SENTINEL
    provider._cache["expired"] = (0.0, "x")
    monkeypatch.setattr(vault_module.time, "monotonic", lambda: 999.0)
    assert provider._from_cache("expired") is vault_module.SENTINEL
    provider._cache["obj"] = (999.0, object())
    assert provider.get("obj") is None

    provider = vault_module.VaultSecretProvider(address="https://vault", token="token", cache_ttl=100)
    provider._approle_credentials = (None, None)
    with pytest.raises(vault_module.VaultClientError):
        provider._approle_login()


def test_reloadable_config_remaining_validation(monkeypatch):
    with monkeypatch.context() as ctx:
        ctx.setenv("APP_ENV", "production")
        ctx.setenv("GATEWAY_AUTH_API_URL", "https://watchdog:4319/api/internal/otlp/validate")
        ctx.setenv("GATEWAY_SSL_VERIFY", "true")
        ctx.setenv("GATEWAY_ALLOWLIST_FAIL_OPEN", "false")
        ctx.setenv("GATEWAY_INTERNAL_SERVICE_TOKEN", "strong_internal_token_123")
        ctx.setenv("GATEWAY_STATUS_OTLP_TOKEN", "startup_probe_token_123")
        ctx.setenv("GATEWAY_STARTUP_CHECK_MODE", "invalid")
        if "config" in sys.modules:
            del sys.modules["config"]
        with pytest.raises(ValueError):
            importlib.import_module("config")


def test_make_default_rate_limiter_and_sanitize(monkeypatch):
    import services.rate_limit as rate_limit_module

    assert rate_limit_module._sanitize_redis_url("redis://user:pass@host:6379/0") == "redis://host:6379/0"
    assert rate_limit_module._sanitize_redis_url(object()) == "<redis-url>"

    monkeypatch.setattr(rate_limit_module.gw_config, "GATEWAY_RATE_LIMIT_STRICT", False)
    limiter = make_default_rate_limiter(2, backend="memory", redis_url="redis://unused")
    assert isinstance(limiter, TokenRateLimiter)
    monkeypatch.setattr(rate_limit_module.gw_config, "GATEWAY_RATE_LIMIT_STRICT", False)

    class FailingRedisLimiter:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("no redis")

    monkeypatch.setattr(rate_limit_module, "RedisTokenRateLimiter", FailingRedisLimiter)
    limiter = make_default_rate_limiter(2, backend="redis", redis_url="redis://bad")
    assert isinstance(limiter, TokenRateLimiter)


def test_hybrid_rate_limiter_warns_once(monkeypatch):
    class BrokenPrimary:
        def __init__(self):
            self.calls = 0

        def enforce(self, key):
            self.calls += 1
            raise RuntimeError("boom")

    fallback = TokenRateLimiter(2)
    limiter = HybridTokenRateLimiter(BrokenPrimary(), fallback)
    times = iter([100.0, 101.0, 150.5])
    monkeypatch.setattr(importlib.import_module("services.rate_limits.hybrid_token_rate_limiter").time, "monotonic", lambda: next(times))
    limiter.enforce("a")
    limiter.enforce("b")
    limiter.enforce("c")


def test_token_rate_limiter_and_token_cache_eviction(monkeypatch):
    limiter = TokenRateLimiter(1)
    times = iter([0.0, 0.0, 61.0])
    monkeypatch.setattr(importlib.import_module("services.rate_limits.token_rate_limiter").time, "time", lambda: next(times))
    limiter.enforce("ip")
    with pytest.raises(HTTPException):
        limiter.enforce("ip")
    limiter.enforce("ip")

    cache = TokenCache(ttl=10, max_size=256)
    cache.set("tok-1", "org-1")
    assert cache.get("tok-1") == (True, "org-1")
    monotonic_values = itertools.count(start=0.0, step=11.0)
    monkeypatch.setattr(importlib.import_module("services.token_cache.memory").time, "monotonic", lambda: next(monotonic_values))
    cache = TokenCache(ttl=10, max_size=256)
    cache.set("tok-2", "org-2")
    assert cache.get("tok-2") == (False, None)
    cache = TokenCache(ttl=100, max_size=256)
    cache._ops = GC_INTERVAL - 1
    cache.set("tok-3", "org-3")
    assert cache.get("tok-3") == (True, "org-3")
    cache = TokenCache(ttl=100, max_size=256)
    for index in range(257):
        cache.set(f"tok-{index}", str(index))
    assert len(cache._cache) <= 256


def test_redis_token_cache_and_rate_limiter(monkeypatch):
    class FakeRedisError(Exception):
        pass

    class FakePipeline:
        def __init__(self, count):
            self.count = count
            self.calls = []

        def incr(self, bucket):
            self.calls.append(("incr", bucket))

        def expire(self, bucket, ttl):
            self.calls.append(("expire", bucket, ttl))

        def execute(self):
            return self.count, True

    class FakeClient:
        def __init__(self, ping=True, get_value=None, count=1):
            self._ping = ping
            self._get_value = get_value
            self._count = count
            self.setex_calls = []

        def ping(self):
            return self._ping

        def get(self, key):
            return self._get_value

        def setex(self, key, ttl, value):
            self.setex_calls.append((key, ttl, value))

        def pipeline(self, transaction=False):
            return FakePipeline(self._count)

    class FakeRedisModule:
        RedisError = FakeRedisError

        def __init__(self):
            self.client = FakeClient()

        def from_url(self, *args, **kwargs):
            return self.client

    fake_redis = FakeRedisModule()
    monkeypatch.setattr(importlib.import_module("services.token_cache.redis"), "redis", fake_redis)
    cache = RedisTokenCache(30, "redis://localhost")
    cache.set("tok", "org")
    assert cache.get("tok") == (False, None)
    fake_redis.client._get_value = "org"
    assert cache.get("tok") == (True, "org")

    rate_module = importlib.import_module("services.rate_limits.redis_token_rate_limiter")
    monkeypatch.setattr(rate_module, "redis", fake_redis)
    limiter = RedisTokenRateLimiter(1, "redis://user:pass@localhost:6379/0")
    limiter.enforce("ip")
    fake_redis.client._count = 2
    with pytest.raises(HTTPException):
        limiter.enforce("ip")

    fake_redis.client = FakeClient(ping=False)
    with pytest.raises(RuntimeError):
        RedisTokenCache(30, "redis://localhost")
    with pytest.raises(RuntimeError):
        RedisTokenRateLimiter(1, "redis://localhost")


def test_vault_provider_paths(monkeypatch):
    original_hvac = vault_module.hvac
    monkeypatch.setattr(vault_module, "hvac", None)
    with pytest.raises(vault_module.VaultClientError):
        vault_module.VaultSecretProvider(address="https://vault", token="token")
    monkeypatch.setattr(vault_module, "hvac", original_hvac)

    class FakeKVv2:
        def __init__(self, response=None, error=None):
            self.response = response
            self.error = error

        def read_secret_version(self, **kwargs):
            if self.error:
                raise self.error
            return self.response

    class FakeKV:
        def __init__(self, response=None, error=None):
            self.v2 = FakeKVv2(response=response, error=error)
            self._response = response
            self._error = error

        def read_secret(self, **kwargs):
            if self._error:
                raise self._error  # pragma: no cover
            return self._response

    class FakeAppRole:
        def __init__(self, token="role-token"):
            self.token = token

        def login(self, role_id=None, secret_id=None):
            return {"auth": {"client_token": self.token}}

    class FakeClient:
        authenticated = True
        kv_response = {"data": {"data": {"value": "secret-value"}}}
        kv_error = None
        token = None

        def __init__(self, url=None, timeout=None, verify=None):
            self.url = url
            self.timeout = timeout
            self.verify = verify
            self.auth = types.SimpleNamespace(approle=FakeAppRole())
            self.secrets = types.SimpleNamespace(kv=FakeKV(self.kv_response, self.kv_error))

        def is_authenticated(self):
            return self.authenticated

    fake_hvac = types.SimpleNamespace(Client=FakeClient)
    monkeypatch.setattr(vault_module, "hvac", fake_hvac)

    with pytest.raises(vault_module.VaultClientError):
        vault_module.VaultSecretProvider(address="", token="token")
    with pytest.raises(vault_module.VaultClientError):
        vault_module.VaultSecretProvider(address="https://vault", token="token", kv_version=3)

    provider = vault_module.VaultSecretProvider(address="https://vault", token="token", cache_ttl=100)
    assert provider.get("a") == "secret-value"
    assert provider.get_many(["a"]) == {"a": "secret-value"}

    FakeClient.kv_response = {"data": {"data": {"a": 7}}}
    provider = vault_module.VaultSecretProvider(address="https://vault", token="token", cache_ttl=100)
    assert provider.get("a") == "7"

    FakeClient.kv_response = {"data": {"data": {"only": "x"}}}
    provider = vault_module.VaultSecretProvider(address="https://vault", token="token", cache_ttl=100)
    assert provider.get("another") == "x"

    FakeClient.kv_response = {"data": {"data": {"a": {}, "b": {}}}}
    provider = vault_module.VaultSecretProvider(address="https://vault", token="token", cache_ttl=100)
    assert provider.get("a") is None

    FakeClient.kv_error = vault_module.InvalidPath()
    provider = vault_module.VaultSecretProvider(address="https://vault", token="token", cache_ttl=100)
    assert provider.get("missing") is None

    FakeClient.kv_error = vault_module.Forbidden()
    provider = vault_module.VaultSecretProvider(address="https://vault", token="token", cache_ttl=100)
    with pytest.raises(vault_module.VaultClientError):
        provider.get("blocked")

    FakeClient.kv_error = None
    FakeClient.kv_response = {"data": {"plain": "v1-value"}}
    provider = vault_module.VaultSecretProvider(address="https://vault", token="token", kv_version=1, cache_ttl=100)
    assert provider.get("plain") == "v1-value"

    FakeClient.authenticated = False
    with pytest.raises(vault_module.VaultClientError):
        vault_module.VaultSecretProvider(address="https://vault", token="token")

    FakeClient.authenticated = True
    provider = vault_module.VaultSecretProvider(
        address="https://vault",
        role_id="role",
        secret_id_fn=lambda: "secret-id",
        cache_ttl=100,
    )
    provider._client.authenticated = False
    provider._approle_credentials = ("role", lambda: "secret-id")
    provider._ensure_authenticated()

    provider._approle_credentials = (None, None)
    provider._client.authenticated = False
    with pytest.raises(vault_module.VaultClientError):
        provider._ensure_authenticated()


def test_token_cache_factory_fallback(monkeypatch):
    import services.token_cache as token_cache_module

    class FailingRedisTokenCache:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("no redis")

    monkeypatch.setattr(token_cache_module, "RedisTokenCache", FailingRedisTokenCache)
    cache = token_cache_module.make_token_cache(5, "redis://bad")
    assert isinstance(cache, token_cache_module.TokenCache)


def test_reloadable_config_validation_errors(monkeypatch):
    env = {
        "APP_ENV": "development",
        "GATEWAY_AUTH_API_URL": "ftp://invalid",
    }
    with pytest.raises(ValueError):
        with monkeypatch.context() as ctx:
            for key, value in env.items():
                ctx.setenv(key, value)
            if "config" in sys.modules:
                del sys.modules["config"]  # pragma: no cover
            importlib.import_module("config")