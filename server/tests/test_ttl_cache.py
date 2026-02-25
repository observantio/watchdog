import asyncio
import time
import sys
import types
import pickle
import logging

from services.common.ttl_cache import TTLCache


def test_ttl_cache_get_set_and_expiry():
    async def _inner():
        cache = TTLCache()
        await cache.set('k', 'v', ttl_seconds=1)
        assert await cache.get('k') == 'v'
        await asyncio.sleep(1.05)
        assert await cache.get('k') is None

    asyncio.run(_inner())


def test_get_or_set_serialises_factory_calls():
    async def _inner():
        cache = TTLCache()
        calls = 0

        async def factory():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.02)
            return 'value'

        results = await asyncio.gather(*[cache.get_or_set('x', factory, 5) for _ in range(8)])
        assert all(r == 'value' for r in results)
        assert calls == 1

    asyncio.run(_inner())


def test_ttl_cache_uses_redis_and_logs_on_success(caplog, monkeypatch):
    class _FakeRedis:
        def __init__(self):
            self.store = {}

        async def ping(self):
            return True

        async def get(self, key):
            return self.store.get(key)

        async def set(self, key, value, ex=None):
            self.store[key] = value
            return True

        async def keys(self, pattern):
            prefix = pattern.rstrip("*")
            return [k for k in self.store.keys() if k.startswith(prefix)]

        async def delete(self, *keys):
            for k in keys:
                self.store.pop(k, None)
            return len(keys)

    fake_mod = types.SimpleNamespace(asyncio=types.SimpleNamespace(from_url=lambda url, **kwargs: _FakeRedis()))
    monkeypatch.setenv("TTL_CACHE_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setitem(sys.modules, "redis", fake_mod)

    caplog.set_level(logging.INFO)

    async def _inner():
        cache = TTLCache()
        # first operation will trigger ping/connect logging
        await cache.set("rkey", {"a": 1}, ttl_seconds=2)
        val = await cache.get("rkey")
        assert val == {"a": 1}
        await cache.clear()
        assert await cache.get("rkey") is None

    asyncio.run(_inner())

    assert any("Connected to Redis for TTL cache" in rec.message or "TTL cache" in rec.message for rec in caplog.records)


def test_ttl_cache_falls_back_to_memory_when_redis_unavailable(monkeypatch):
    # ensure redis import will not expose asyncio client
    monkeypatch.setenv("TTL_CACHE_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setitem(sys.modules, "redis", types.SimpleNamespace(asyncio=None))

    async def _inner():
        cache = TTLCache()
        await cache.set('m', 123, ttl_seconds=1)
        assert await cache.get('m') == 123
        await asyncio.sleep(1.05)
        assert await cache.get('m') is None

    asyncio.run(_inner())
