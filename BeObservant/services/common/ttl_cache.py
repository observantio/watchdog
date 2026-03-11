"""
TTLCache implementation for Be Observant, with optional Redis backend support.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable, Dict, Optional, Protocol, runtime_checkable

from config import config
from custom_types.json import JSONValue, is_json_value

_redis_asyncio = None
try:
    import redis
    _redis_asyncio = getattr(redis, "asyncio", None)
except ImportError:
    _redis_asyncio = None

logger = logging.getLogger(__name__)

@runtime_checkable
class RedisAsyncClient(Protocol):
    async def ping(self) -> object: ...
    async def set(self, key: str, value: bytes, ex: int) -> object: ...
    async def get(self, key: str) -> Optional[bytes]: ...
    async def keys(self, pattern: str) -> list[str] | list[bytes]: ...
    async def delete(self, *keys: str | bytes) -> object: ...
    async def aclose(self) -> object: ...
    async def close(self) -> object: ...


class TTLCache:
    def __init__(self) -> None:
        self._data: Dict[str, tuple[JSONValue, float]] = {}
        self._lock = asyncio.Lock()
        self._redis_url = (config.TTL_CACHE_REDIS_URL or config.RATE_LIMIT_REDIS_URL or "").strip()
        self._key_prefix = (config.TTL_CACHE_KEY_PREFIX or "beobs:ttl").strip()
        self._redis_client: Optional[RedisAsyncClient] = None
        self._redis_connected = False
        self._redis_loop_id: Optional[int] = None

    def _redis_key(self, key: str) -> str:
        return f"{self._key_prefix}:{key}"

    def _serialize_value(self, value: JSONValue) -> bytes:
        try:
            return b"j:" + json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("TTL cache only supports JSON-serializable values") from exc

    def _deserialize_value(self, raw: Optional[bytes]) -> Optional[JSONValue]:
        if not raw:
            return None
        if raw.startswith(b"j:"):
            try:
                payload: object = json.loads(raw[2:].decode("utf-8"))
                return payload if is_json_value(payload) else None
            except (TypeError, ValueError, json.JSONDecodeError):
                logger.warning("TTL cache JSON payload is invalid; dropping cache value")
                return None
        logger.warning("TTL cache encountered non-JSON legacy payload; dropping cache value")
        return None

    async def _close_redis_client(self) -> None:
        client = self._redis_client
        self._redis_client = None
        self._redis_connected = False
        self._redis_loop_id = None
        if client is None:
            return
        try:
            await client.aclose()
            return
        except AttributeError:
            pass
        except (OSError, RuntimeError):
            pass
        try:
            await client.close()
        except AttributeError:
            pass
        except (OSError, RuntimeError):
            pass

    async def _ensure_redis(self) -> bool:
        if _redis_asyncio is None or not self._redis_url:
            return False

        loop_id = id(asyncio.get_running_loop())

        if self._redis_client is None or self._redis_loop_id != loop_id:
            await self._close_redis_client()
            try:
                self._redis_client = _redis_asyncio.from_url(
                    self._redis_url,
                    decode_responses=False,
                    health_check_interval=30,
                    socket_keepalive=True,
                )
                self._redis_loop_id = loop_id
            except (AttributeError, OSError, RuntimeError, ValueError) as exc:
                logger.warning("Failed to initialize Redis client for TTLCache; using in-memory fallback: %s", exc)
                self._redis_client = None
                return False

        client = self._redis_client
        if self._redis_connected and client is not None:
            return True

        try:
            if client is None:
                return False
            ok = await client.ping()
            if ok:
                self._redis_connected = True
                logger.info("Connected to Redis for TTL cache: %s", self._redis_url)
                await self._flush_memory_to_redis()
                return True
        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning("Redis TTL cache unreachable; falling back to in-memory cache: %s", exc)
            await self._close_redis_client()
            return False

        return False

    async def _flush_memory_to_redis(self) -> None:
        client = self._redis_client
        if client is None or not self._data:
            return

        now = time.monotonic()
        items = list(self._data.items())

        for k, (v, expires) in items:
            ttl = int(expires - now)
            if ttl <= 0:
                continue
            try:
                await client.set(self._redis_key(k), self._serialize_value(v), ex=ttl)
            except (OSError, RuntimeError, ValueError):
                await self._close_redis_client()
                return

        async with self._lock:
            now2 = time.monotonic()
            for k, (_, expires) in list(self._data.items()):
                if now2 > expires:
                    self._data.pop(k, None)
            if self._redis_client is not None:
                self._data.clear()

    async def get(self, key: str) -> Optional[JSONValue]:
        if await self._ensure_redis():
            try:
                client = self._redis_client
                if client is None:
                    return None
                raw = await client.get(self._redis_key(key))
                return self._deserialize_value(raw)
            except (OSError, RuntimeError, ValueError) as exc:
                logger.warning("Redis TTL cache GET failed; falling back to memory: %s", exc)
                await self._close_redis_client()

        async with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            value, expires = entry
            if time.monotonic() > expires:
                self._data.pop(key, None)
                return None
            return value

    async def set(self, key: str, value: JSONValue, ttl_seconds: int) -> None:
        ttl = max(0, int(ttl_seconds))

        if await self._ensure_redis():
            try:
                client = self._redis_client
                if client is None:
                    return
                await client.set(self._redis_key(key), self._serialize_value(value), ex=ttl)
                return
            except (OSError, RuntimeError, ValueError) as exc:
                logger.warning("Redis TTL cache SET failed; using in-memory fallback: %s", exc)
                await self._close_redis_client()

        async with self._lock:
            self._data[key] = (value, time.monotonic() + ttl)

    async def get_or_set(
        self, key: str, factory: Callable[[], Awaitable[Optional[JSONValue]]], ttl_seconds: int
    ) -> Optional[JSONValue]:
        v = await self.get(key)
        if v is not None:
            return v

        value = await factory()
        if value is None:
            return None

        await self.set(key, value, ttl_seconds)
        return value

    async def clear(self) -> None:
        if await self._ensure_redis():
            try:
                client = self._redis_client
                if client is None:
                    return
                keys = await client.keys(f"{self._key_prefix}:*")
                if keys:
                    await client.delete(*keys)
            except (OSError, RuntimeError, ValueError) as exc:
                logger.warning("Redis TTL cache CLEAR failed; clearing in-memory cache: %s", exc)
                await self._close_redis_client()

        async with self._lock:
            self._data.clear()
