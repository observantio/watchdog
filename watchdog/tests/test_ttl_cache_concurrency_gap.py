"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio

import pytest

from tests._env import ensure_test_env

ensure_test_env()

from services.common.ttl_cache import TTLCache


@pytest.mark.asyncio
async def test_get_or_set_deduplicates_concurrent_factory_calls():
    cache = TTLCache()
    calls = {"count": 0}
    gate = asyncio.Event()

    async def factory():
        calls["count"] += 1
        await gate.wait()
        return {"ok": True}

    t1 = asyncio.create_task(cache.get_or_set("k", factory, 10))
    t2 = asyncio.create_task(cache.get_or_set("k", factory, 10))
    await asyncio.sleep(0.01)
    gate.set()
    out1, out2 = await asyncio.gather(t1, t2)
    assert out1 == {"ok": True}
    assert out2 == {"ok": True}
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_get_or_set_exception_unblocks_waiters_and_allows_retry():
    cache = TTLCache()
    gate = asyncio.Event()

    async def failing_factory():
        await gate.wait()
        raise RuntimeError("boom")

    t1 = asyncio.create_task(cache.get_or_set("k", failing_factory, 10))
    t2 = asyncio.create_task(cache.get_or_set("k", failing_factory, 10))
    await asyncio.sleep(0.01)
    gate.set()
    results = await asyncio.gather(t1, t2, return_exceptions=True)
    assert all(isinstance(item, RuntimeError) for item in results)

    async def ok_factory():
        return {"recovered": True}

    assert await cache.get_or_set("k", ok_factory, 10) == {"recovered": True}
