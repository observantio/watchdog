"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import importlib
import time
import types

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from services import gateway_service as gateway_service_module
from services.gateway_service import DatabaseUnavailable, GatewayAuthService
from services.rate_limit import make_default_rate_limiter
from services.rate_limits import redis_token_rate_limiter as redis_rate_module
from services.rate_limits import token_rate_limiter as token_rate_module
from services.rate_limits.token_rate_limiter import TokenRateLimiter
from services.token_cache import make_token_cache
from services.token_cache import redis as token_cache_redis_module
from services.token_cache.redis import RedisTokenCache
from services.secrets import vault_client as vault_module


def _request(client_host: str, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/api/gateway/validate",
            "headers": headers or [],
            "client": (client_host, 1234),
            "scheme": "http",
            "query_string": b"",
        }
    )


def test_gateway_service_proxy_and_allowlist_edge_cases(monkeypatch):
    monkeypatch.setattr(gateway_service_module.gw_config, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(gateway_service_module.gw_config, "TRUSTED_PROXY_CIDRS", ["bad-cidr"])
    request = _request("127.0.0.1")
    assert GatewayAuthService._trusted_proxy_peer(request) is False

    monkeypatch.setattr(gateway_service_module.gw_config, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(gateway_service_module.gw_config, "TRUSTED_PROXY_CIDRS", [])
    service = GatewayAuthService(rate_limit_per_minute=10, ip_allowlist="127.0.0.1")
    invalid_ip_request = _request("127.0.0.1", headers=[(b"x-forwarded-for", b"not-an-ip")])
    with pytest.raises(HTTPException) as exc:
        service.enforce_ip_allowlist(invalid_ip_request)
    assert exc.value.detail == "Invalid client IP"

    blank_proxy_request = _request("198.51.100.20", headers=[(b"x-forwarded-for", b"   ")])
    assert GatewayAuthService._client_ip(blank_proxy_request) == "198.51.100.20"


def test_validate_otlp_token_reraises_database_unavailable(monkeypatch):
    service = GatewayAuthService(rate_limit_per_minute=10, ip_allowlist="127.0.0.1")
    assert service.validate_otlp_token("") is None
    monkeypatch.setattr(GatewayAuthService, "_fetch_org_from_api", lambda self, token: (_ for _ in ()).throw(DatabaseUnavailable("down")))
    with pytest.raises(DatabaseUnavailable):
        service.validate_otlp_token("tok")


def test_fetch_org_from_api_returns_none_for_empty_token():
    service = GatewayAuthService(rate_limit_per_minute=10, ip_allowlist="127.0.0.1")
    assert service._fetch_org_from_api("") is None


def test_rate_limiter_factory_warning_and_fallback_paths(monkeypatch):
    import services.rate_limit as rate_limit_module

    monkeypatch.setattr(rate_limit_module.gw_config, "GATEWAY_RATE_LIMIT_STRICT", False)
    memory_limiter = make_default_rate_limiter(2, backend="redis", redis_url=None)
    assert isinstance(memory_limiter, TokenRateLimiter)

    class FailingRedisLimiter:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("no redis")

    monkeypatch.setattr(rate_limit_module, "RedisTokenRateLimiter", FailingRedisLimiter)
    fallback = make_default_rate_limiter(2, backend="auto", redis_url="redis://localhost")
    assert isinstance(fallback, TokenRateLimiter)

    class WorkingRedisLimiter:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(rate_limit_module, "RedisTokenRateLimiter", WorkingRedisLimiter)
    hybrid = make_default_rate_limiter(2, backend="auto", redis_url="redis://localhost")
    from services.rate_limits.hybrid_token_rate_limiter import HybridTokenRateLimiter

    assert isinstance(hybrid, HybridTokenRateLimiter)


def test_token_rate_limiter_gc_and_eviction(monkeypatch):
    now = time.time()
    monkeypatch.setattr(token_rate_module, "MAX_IN_MEMORY_KEYS", 1)

    gc_limiter = TokenRateLimiter(3)
    gc_limiter._ops = 1023
    gc_limiter._hits = {"stale": (now - 130, 1)}
    gc_limiter.enforce("fresh")
    assert "stale" not in gc_limiter._hits
    assert "fresh" in gc_limiter._hits

    evict_limiter = TokenRateLimiter(3)
    evict_limiter._hits = {"old": (now, 1)}
    evict_limiter.enforce("new")
    assert "old" not in evict_limiter._hits
    assert "new" in evict_limiter._hits


def test_redis_backends_raise_when_library_missing(monkeypatch):
    monkeypatch.setattr(redis_rate_module, "redis", None)
    monkeypatch.setattr(token_cache_redis_module, "redis", None)
    with pytest.raises(RuntimeError):
        redis_rate_module.RedisTokenRateLimiter(1, "redis://localhost")
    with pytest.raises(RuntimeError):
        RedisTokenCache(30, "redis://localhost")


def test_token_cache_factory_returns_redis_backend(monkeypatch):
    import services.token_cache as token_cache_module

    class FakeRedisTokenCache:
        def __init__(self, ttl, url):
            self.ttl = ttl
            self.url = url

    monkeypatch.setattr(token_cache_module, "RedisTokenCache", FakeRedisTokenCache)
    cache = make_token_cache(5, "redis://cache")
    assert isinstance(cache, FakeRedisTokenCache)
    assert cache.ttl == 5
    assert cache.url == "redis://cache"


def test_reload_optional_redis_and_vault_import_fallbacks(monkeypatch):
    import importlib as importlib_module
    original_import_module = importlib_module.import_module

    redis_compat_module = importlib.import_module("services.token_cache._redis_compat")
    original_redis = redis_compat_module.redis
    monkeypatch.setattr(importlib_module, "import_module", lambda name, package=None: (_ for _ in ()).throw(ImportError("missing")))
    importlib.reload(redis_compat_module)
    assert redis_compat_module.redis is None
    monkeypatch.setattr(importlib_module, "import_module", original_import_module)
    importlib.reload(redis_compat_module)
    redis_compat_module.redis = original_redis

    original_hvac = vault_module.hvac
    original_forbidden = vault_module.Forbidden
    original_invalid_path = vault_module.InvalidPath
    original_vault_error = vault_module.VaultError

    def fake_import(name: str):
        raise ImportError(name)

    monkeypatch.setattr(importlib_module, "import_module", lambda name, package=None: fake_import(name))
    importlib.reload(vault_module)
    assert vault_module.hvac is None
    assert issubclass(vault_module.Forbidden, Exception)
    assert issubclass(vault_module.InvalidPath, Exception)
    assert issubclass(vault_module.VaultError, Exception)
    monkeypatch.setattr(importlib_module, "import_module", original_import_module)
    importlib.reload(vault_module)
    vault_module.hvac = original_hvac
    vault_module.Forbidden = original_forbidden
    vault_module.InvalidPath = original_invalid_path
    vault_module.VaultError = original_vault_error


def test_redis_rate_limiter_sanitize_fallback():
    assert redis_rate_module._sanitize_redis_url(types.SimpleNamespace()) == "<redis-url>"


def test_hybrid_rate_limiter_reraises_http_exception():
    from services.rate_limits.hybrid_token_rate_limiter import HybridTokenRateLimiter

    class Primary:
        def enforce(self, key):
            raise HTTPException(status_code=429, detail="stop")

    class Fallback:
        def enforce(self, key):
            raise AssertionError("fallback should not run")  # pragma: no cover

    limiter = HybridTokenRateLimiter(Primary(), Fallback())
    with pytest.raises(HTTPException) as exc:
        limiter.enforce("ip")
    assert exc.value.status_code == 429


def test_redis_rate_limiter_constructor_and_error_branches(monkeypatch):
    class FakeRedisError(Exception):
        pass

    class FakeClient:
        def __init__(self, ping_error=None):
            self.ping_error = ping_error

        def ping(self):
            if self.ping_error:
                raise self.ping_error
            return True  # pragma: no cover

        def pipeline(self, transaction=False):  # pragma: no cover
            return types.SimpleNamespace(
                incr=lambda bucket: None,
                expire=lambda bucket, ttl: None,
                execute=lambda: (1, True),
            )

    class FakeRedisModule:
        RedisError = FakeRedisError  # pragma: no cover

        def __init__(self, client):
            self._client = client

        def from_url(self, *args, **kwargs):
            return self._client

    assert redis_rate_module._sanitize_redis_url("redis://user:pass@host:6379/0") == "redis://host:6379/0"
    monkeypatch.setattr(redis_rate_module, "redis", FakeRedisModule(FakeClient(ping_error=FakeRedisError("boom"))))
    with pytest.raises(RuntimeError) as exc:
        redis_rate_module.RedisTokenRateLimiter(1, "redis://user:pass@host:6379/0")
    assert "host:6379" in str(exc.value)


def test_vault_client_auth_and_payload_edge_branches(monkeypatch):
    class FakeAppRole:
        def login(self, role_id=None, secret_id=None):
            return {"auth": {"client_token": "role-token"}}  # pragma: no cover

    class FakeKV:
        def __init__(self, response):
            self.v2 = self
            self._response = response

        def read_secret_version(self, **kwargs):
            return self._response

        def read_secret(self, **kwargs):
            return self._response  # pragma: no cover

    class FakeClient:
        authenticated = True  # pragma: no cover
        response = {"data": {"data": {}}}

        def __init__(self, *args, **kwargs):
            self.auth = types.SimpleNamespace(approle=FakeAppRole())
            self.secrets = types.SimpleNamespace(kv=FakeKV(self.response))
            self.token = None

        def is_authenticated(self):
            return self.authenticated

    monkeypatch.setattr(vault_module, "hvac", types.SimpleNamespace(Client=FakeClient))
    with pytest.raises(vault_module.VaultClientError):
        vault_module.VaultSecretProvider(address="https://vault")

    provider = vault_module.VaultSecretProvider(address="https://vault", token="token", cache_ttl=100)
    assert provider.get("missing") is None


def test_reload_vault_import_with_non_exception_symbols(monkeypatch):
    import importlib as importlib_module

    original_import_module = importlib_module.import_module

    fake_hvac_module = types.SimpleNamespace()
    fake_exceptions_module = types.SimpleNamespace(Forbidden="bad", InvalidPath=object(), VaultError=None)

    def fake_import(name, package=None):
        if name == "hvac":
            return fake_hvac_module
        if name == "hvac.exceptions":
            return fake_exceptions_module
        return original_import_module(name, package)  # pragma: no cover

    monkeypatch.setattr(importlib_module, "import_module", fake_import)
    importlib.reload(vault_module)
    assert vault_module.hvac is fake_hvac_module
    assert vault_module.Forbidden is not fake_exceptions_module.Forbidden
    assert vault_module.InvalidPath is not fake_exceptions_module.InvalidPath
    assert vault_module.VaultError is not fake_exceptions_module.VaultError
    monkeypatch.setattr(importlib_module, "import_module", original_import_module)
    importlib.reload(vault_module)


def test_reload_redis_rate_module_without_redis(monkeypatch):
    import importlib as importlib_module

    original_import_module = importlib_module.import_module

    def fake_import(name, package=None):
        if name == "redis":
            raise ImportError(name)  # pragma: no cover
        return original_import_module(name, package)  # pragma: no cover

    monkeypatch.setattr(importlib_module, "import_module", fake_import)
    importlib.reload(redis_rate_module)
    assert redis_rate_module.redis is None
    monkeypatch.setattr(importlib_module, "import_module", original_import_module)
    importlib.reload(redis_rate_module)