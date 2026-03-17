"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import pytest

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from services.common import ttl_cache as ttl_mod


class _FakeRedisClient:
    def __init__(self, *, ping_result=True, get_value=None, set_error=None, get_error=None, delete_error=None):
        self.ping_result = ping_result
        self.get_value = get_value
        self.set_error = set_error
        self.get_error = get_error
        self.delete_error = delete_error
        self.set_calls = []
        self.deleted = []
        self.closed = []
        self.keys_result = [b"watchdog:ttl:key1"]

    async def ping(self):
        if isinstance(self.ping_result, Exception):
            raise self.ping_result
        return self.ping_result

    async def set(self, key, value, ex):
        if self.set_error is not None:
            raise self.set_error
        self.set_calls.append((key, value, ex))
        return True

    async def get(self, key):
        if self.get_error is not None:
            raise self.get_error
        return self.get_value

    async def keys(self, pattern):
        return self.keys_result

    async def delete(self, *keys):
        if self.delete_error is not None:
            raise self.delete_error
        self.deleted.append(keys)
        return len(keys)

    async def aclose(self):
        self.closed.append("aclose")

    async def close(self):
        self.closed.append("close")


@pytest.mark.asyncio
async def test_memory_cache_and_serialization_paths(monkeypatch):
    warnings = []
    monkeypatch.setattr(ttl_mod.config, "TTL_CACHE_REDIS_URL", "")
    monkeypatch.setattr(ttl_mod.config, "RATE_LIMIT_REDIS_URL", "")
    monkeypatch.setattr(ttl_mod.config, "TTL_CACHE_KEY_PREFIX", "prefix")
    monkeypatch.setattr(ttl_mod, "_redis_asyncio", None)
    monkeypatch.setattr(ttl_mod.logger, "warning", lambda *args, **kwargs: warnings.append(args))

    cache = ttl_mod.TTLCache()
    assert cache._redis_key("abc") == "prefix:abc"
    assert cache._serialize_value({"a": [1, True]}) == b'j:{"a":[1,true]}'
    with pytest.raises(ValueError, match="JSON-serializable"):
        cache._serialize_value({"bad": object()})

    assert cache._deserialize_value(b'j:{"a":1}') == {"a": 1}
    assert cache._deserialize_value(b"j:{") is None
    assert cache._deserialize_value(b"legacy") is None
    assert warnings

    now = {"value": 10.0}
    monkeypatch.setattr(ttl_mod.time, "monotonic", lambda: now["value"])

    await cache.set("k1", {"ok": True}, 5)
    now["value"] = 11.0
    assert await cache.get("k1") == {"ok": True}
    now["value"] = 16.0
    assert await cache.get("k1") is None

    calls = []

    async def factory():
        calls.append("factory")
        return {"built": True}

    assert await cache.get_or_set("k2", factory, 5) == {"built": True}
    assert calls == ["factory"]
    await cache.clear()
    assert cache._data == {}


@pytest.mark.asyncio
async def test_close_redis_client_and_init_failures(monkeypatch):
    warnings = []
    monkeypatch.setattr(ttl_mod.logger, "warning", lambda *args, **kwargs: warnings.append(args))
    monkeypatch.setattr(ttl_mod.config, "TTL_CACHE_REDIS_URL", "redis://example")
    monkeypatch.setattr(ttl_mod.config, "RATE_LIMIT_REDIS_URL", "")
    monkeypatch.setattr(ttl_mod.config, "TTL_CACHE_KEY_PREFIX", "watchdog")

    class BadNamespace:
        @staticmethod
        def from_url(*args, **kwargs):
            raise ValueError("bad config")

    cache = ttl_mod.TTLCache()
    cache._redis_client = _FakeRedisClient()
    await cache._close_redis_client()
    assert cache._redis_client is None

    monkeypatch.setattr(ttl_mod, "_redis_asyncio", BadNamespace)
    assert await cache._ensure_redis() is False
    assert warnings


@pytest.mark.asyncio
async def test_ensure_redis_flushes_memory_and_handles_ping_failure(monkeypatch):
    info_calls = []
    warnings = []
    client = _FakeRedisClient(ping_result=True)

    class Namespace:
        @staticmethod
        def from_url(*args, **kwargs):
            return client

    monkeypatch.setattr(ttl_mod.config, "TTL_CACHE_REDIS_URL", "redis://example")
    monkeypatch.setattr(ttl_mod.config, "RATE_LIMIT_REDIS_URL", "")
    monkeypatch.setattr(ttl_mod.config, "TTL_CACHE_KEY_PREFIX", "watchdog")
    monkeypatch.setattr(ttl_mod, "_redis_asyncio", Namespace)
    monkeypatch.setattr(ttl_mod.logger, "info", lambda *args, **kwargs: info_calls.append(args))
    monkeypatch.setattr(ttl_mod.logger, "warning", lambda *args, **kwargs: warnings.append(args))

    cache = ttl_mod.TTLCache()
    cache._data = {"alive": ({"x": 1}, 20.0), "expired": ({"y": 1}, 5.0)}
    now = {"value": 10.0}
    monkeypatch.setattr(ttl_mod.time, "monotonic", lambda: now["value"])

    assert await cache._ensure_redis() is True
    assert client.set_calls == [("watchdog:alive", b'j:{"x":1}', 10)]
    assert cache._data == {}
    assert info_calls
    assert await cache._ensure_redis() is True

    bad_client = _FakeRedisClient(ping_result=OSError("down"))

    class BadNamespace:
        @staticmethod
        def from_url(*args, **kwargs):
            return bad_client

    cache = ttl_mod.TTLCache()
    monkeypatch.setattr(ttl_mod, "_redis_asyncio", BadNamespace)
    assert await cache._ensure_redis() is False
    assert bad_client.closed == ["aclose"]
    assert warnings


@pytest.mark.asyncio
async def test_redis_get_set_and_clear_paths(monkeypatch):
    warnings = []
    client = _FakeRedisClient(get_value=b'j:{"v":1}')

    monkeypatch.setattr(ttl_mod.config, "TTL_CACHE_REDIS_URL", "redis://example")
    monkeypatch.setattr(ttl_mod.config, "RATE_LIMIT_REDIS_URL", "")
    monkeypatch.setattr(ttl_mod.config, "TTL_CACHE_KEY_PREFIX", "watchdog")
    monkeypatch.setattr(ttl_mod.logger, "warning", lambda *args, **kwargs: warnings.append(args))

    class Namespace:
        @staticmethod
        def from_url(*args, **kwargs):
            return client

    monkeypatch.setattr(ttl_mod, "_redis_asyncio", Namespace)
    cache = ttl_mod.TTLCache()
    assert await cache.get("x") == {"v": 1}

    client.get_error = RuntimeError("get failed")
    cache._data["x"] = ({"fallback": True}, 999999.0)
    monkeypatch.setattr(ttl_mod.time, "monotonic", lambda: 100.0)
    assert await cache.get("x") == {"fallback": True}

    client = _FakeRedisClient(set_error=RuntimeError("set failed"))

    class SetFailNamespace:
        @staticmethod
        def from_url(*args, **kwargs):
            return client

    monkeypatch.setattr(ttl_mod, "_redis_asyncio", SetFailNamespace)
    cache = ttl_mod.TTLCache()
    monkeypatch.setattr(ttl_mod.time, "monotonic", lambda: 200.0)
    await cache.set("k", {"v": 2}, 3)
    assert cache._data["k"][0] == {"v": 2}

    client = _FakeRedisClient(delete_error=RuntimeError("delete failed"))

    class ClearFailNamespace:
        @staticmethod
        def from_url(*args, **kwargs):
            return client

    monkeypatch.setattr(ttl_mod, "_redis_asyncio", ClearFailNamespace)
    cache = ttl_mod.TTLCache()
    cache._data["k"] = ({"v": 3}, 999999.0)
    await cache.clear()
    assert cache._data == {}
    assert warnings