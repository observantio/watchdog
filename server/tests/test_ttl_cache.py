import asyncio
import time
import sys
import types
import pickle
import logging

# ensure environment/config are initialized before importing modules that
# read config at import time
from tests._env import ensure_test_env
ensure_test_env()

from config import config
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
    # ensure TTLCache will pick up our fake redis backend
    from services.common import ttl_cache as _ttlmod
    _ttlmod._redis_asyncio = fake_mod.asyncio

    # configure both env and config for the module under test
    monkeypatch.setenv("TTL_CACHE_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setattr(config, "TTL_CACHE_REDIS_URL", "redis://redis:6379/0")
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
    # ensure redis import will not expose asyncio client and config has no url
    monkeypatch.setenv("TTL_CACHE_REDIS_URL", "")
    monkeypatch.setattr(config, "TTL_CACHE_REDIS_URL", "")
    from services.common import ttl_cache as _ttlmod
    _ttlmod._redis_asyncio = None
    monkeypatch.setitem(sys.modules, "redis", types.SimpleNamespace(asyncio=None))

    async def _inner():
        cache = TTLCache()
        await cache.set('m', 123, ttl_seconds=1)
        assert await cache.get('m') == 123
        await asyncio.sleep(1.05)
        assert await cache.get('m') is None

    asyncio.run(_inner())




async def _wait_short():
    # tiny helper so we don't sleep for real in tests
    await asyncio.sleep(0.001)


def test_ttl_cache_reconnects_and_flushes(monkeypatch, caplog):
    """Verify cache recovers when Redis disconnects and pushes in-memory data back.

    We simulate a flaky backend that fails on demand and ensure that
    TTLCache will drop the client, fall back to memory, then re-create a new
    client when Redis comes back and eventually flush any cached items.
    """
    created = []

    class FlakyRedis:
        def __init__(self):
            self.store = {}
            self.fail = False

        async def ping(self):
            if self.fail:
                raise Exception("unreachable")
            return True

        async def get(self, key):
            if self.fail:
                raise Exception("closed")
            return self.store.get(key)

        async def set(self, key, value, ex=None):
            if self.fail:
                raise Exception("closed")
            self.store[key] = value
            return True

        async def keys(self, pattern):
            prefix = pattern.rstrip("*")
            return [k for k in self.store.keys() if k.startswith(prefix)]

        async def delete(self, *keys):
            for k in keys:
                self.store.pop(k, None)
            return len(keys)

    def make():
        inst = FlakyRedis()
        created.append(inst)
        return inst

    fake_mod = types.SimpleNamespace(
        asyncio=types.SimpleNamespace(from_url=lambda url, **kw: make())
    )

    # configure environment and module to use our fake redis
    from services.common import ttl_cache as _ttlmod
    _ttlmod._redis_asyncio = fake_mod.asyncio
    monkeypatch.setenv("TTL_CACHE_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setattr(config, "TTL_CACHE_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setitem(sys.modules, "redis", fake_mod)

    caplog.set_level(logging.INFO)

    async def _inner():
        cache = TTLCache()

        # initial set should succeed and be readable via get()
        await cache.set("a", 1, ttl_seconds=5)
        assert await cache.get("a") == 1

        # make backend throw on next operation, forcing fallback
        created[0].fail = True
        await cache.set("a", 2, ttl_seconds=5)
        # value should now be in the in-memory store
        assert cache._data.get("a")[0] == 2
        # get() still returns the memory value while redis is down
        assert await cache.get("a") == 2

        # restore Redis; next operation will recreate the client
        created[0].fail = False
        await cache.set("a", 3, ttl_seconds=5)

        # cache should now be able to read from redis again
        assert await cache.get("a") == 3
        # memory store should have been cleared by the reconnect flush
        assert "a" not in cache._data

    asyncio.run(_inner())

    assert any("Connected to Redis for TTL cache" in rec.message for rec in caplog.records)


def test_ttl_cache_custom_prefix(monkeypatch):
    """Ensure the configured key prefix is applied when building Redis keys."""
    # patch the configuration value for prefix
    monkeypatch.setattr(config, "TTL_CACHE_KEY_PREFIX", "customprefix")

    cache = TTLCache()
    class Dummy:
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
            return [k for k in self.store if k.startswith(pattern.rstrip("*"))]
        async def delete(self, *keys):
            for k in keys:
                self.store.pop(k, None)
            return len(keys)
    fake_mod = types.SimpleNamespace(asyncio=types.SimpleNamespace(from_url=lambda url, **kwargs: Dummy()))
    monkeypatch.setitem(sys.modules, "redis", fake_mod)

    async def _inner2():
        # key generation should respect the new prefix
        assert cache._redis_key("foo").startswith("customprefix:")
    asyncio.run(_inner2())
