"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio
import builtins
import importlib

import pytest

from tests._env import ensure_test_env

ensure_test_env()

from services.common import ttl_cache as ttl_mod


@pytest.mark.asyncio
async def test_ttl_cache_remaining_memory_and_pending_paths(monkeypatch):
    cache = ttl_mod.TTLCache()
    # ttl<=0 path
    await cache.set("k", {"v": 1}, 0)
    assert await cache.get("k") is None

    # get_or_set returns cached value path
    await cache.set("cached", {"ok": True}, 5)
    async def factory():
        return {"new": True}
    assert await cache.get_or_set("cached", factory, 5) == {"ok": True}

    # owner path with None value (pending.set_result(None))
    async def none_factory():
        return None
    assert await cache.get_or_set("none", none_factory, 5) is None


@pytest.mark.asyncio
async def test_ttl_cache_redis_falsey_ping_and_none_client_paths(monkeypatch):
    class _ClientFalse:
        async def ping(self):
            return False

    class _NS:
        @staticmethod
        def from_url(*_args, **_kwargs):
            return _ClientFalse()

    monkeypatch.setattr(ttl_mod, "_redis_asyncio", _NS)
    monkeypatch.setattr(ttl_mod.config, "TTL_CACHE_REDIS_URL", "redis://x", raising=False)
    monkeypatch.setattr(ttl_mod.config, "RATE_LIMIT_REDIS_URL", "", raising=False)
    cache = ttl_mod.TTLCache()
    assert await cache._ensure_redis() is False

    # clear early return when ensure_redis true but client is None
    async def ensure_true():
        return True
    cache2 = ttl_mod.TTLCache()
    cache2._ensure_redis = ensure_true  # type: ignore[assignment]
    cache2._redis_client = None
    await cache2.clear()
    assert cache2._data == {}


def test_ttl_cache_importerror_branch(monkeypatch):
    # Re-import module with redis import failing to hit ImportError initialization branch.
    import services.common.ttl_cache as module_ref

    orig_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "redis":
            raise ImportError("forced")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    reloaded = importlib.reload(module_ref)
    assert getattr(reloaded, "_redis_asyncio") is None
    importlib.reload(module_ref)
