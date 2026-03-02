import asyncio
import json
import logging
import time
from typing import Any, Awaitable, Callable, Dict, Optional

from config import config

_redis_asyncio = None
try:
    import redis
    _redis_asyncio = getattr(redis, "asyncio", None)
except Exception:
    _redis_asyncio = None

logger = logging.getLogger(__name__)


class TTLCache:
    def __init__(self) -> None:
        self._data: Dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()
        self._redis_url = (config.TTL_CACHE_REDIS_URL or config.RATE_LIMIT_REDIS_URL or "").strip()
        self._key_prefix = (config.TTL_CACHE_KEY_PREFIX or "beobs:ttl").strip()
        self._redis_client = None
        self._redis_connected = False
        self._redis_loop_id: Optional[int] = None

    def _redis_key(self, key: str) -> str:
        return f"{self._key_prefix}:{key}"

    def _serialize_value(self, value: Any) -> bytes:
        try:
            return b"j:" + json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        except Exception as exc:
            raise ValueError("TTL cache only supports JSON-serializable values") from exc

    def _deserialize_value(self, raw: Optional[bytes]) -> Optional[Any]:
        if not raw:
            return None
        if raw.startswith(b"j:"):
            try:
                return json.loads(raw[2:].decode("utf-8"))
            except Exception:
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
        except Exception:
            try:
                await client.close()
            except Exception:
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
            except Exception as exc:
                logger.warning("Failed to initialize Redis client for TTLCache; using in-memory fallback: %s", exc)
                self._redis_client = None
                return False

        if self._redis_connected:
            return True

        try:
            ok = await self._redis_client.ping()
            if ok:
                self._redis_connected = True
                logger.info("Connected to Redis for TTL cache: %s", self._redis_url)
                await self._flush_memory_to_redis()
                return True
        except Exception as exc:
            logger.warning("Redis TTL cache unreachable; falling back to in-memory cache: %s", exc)
            await self._close_redis_client()
            return False

        return False

    async def _flush_memory_to_redis(self) -> None:
        if not self._redis_client or not self._data:
            return

        now = time.monotonic()
        items = list(self._data.items())

        for k, (v, expires) in items:
            ttl = int(expires - now)
            if ttl <= 0:
                continue
            try:
                await self._redis_client.set(self._redis_key(k), self._serialize_value(v), ex=ttl)
            except Exception:
                await self._close_redis_client()
                return

        async with self._lock:
            now2 = time.monotonic()
            for k, (_, expires) in list(self._data.items()):
                if now2 > expires:
                    self._data.pop(k, None)
            if self._redis_client is not None:
                self._data.clear()

    async def get(self, key: str) -> Optional[Any]:
        if await self._ensure_redis():
            try:
                raw = await self._redis_client.get(self._redis_key(key))
                return self._deserialize_value(raw)
            except Exception as exc:
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

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        ttl = max(0, int(ttl_seconds))

        if await self._ensure_redis():
            try:
                await self._redis_client.set(self._redis_key(key), self._serialize_value(value), ex=ttl)
                return
            except Exception as exc:
                logger.warning("Redis TTL cache SET failed; using in-memory fallback: %s", exc)
                await self._close_redis_client()

        async with self._lock:
            self._data[key] = (value, time.monotonic() + ttl)

    async def get_or_set(
        self, key: str, factory: Callable[[], Awaitable[Any]], ttl_seconds: int
    ) -> Optional[Any]:
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
                keys = await self._redis_client.keys(f"{self._key_prefix}:*")
                if keys:
                    await self._redis_client.delete(*keys)
            except Exception as exc:
                logger.warning("Redis TTL cache CLEAR failed; clearing in-memory cache: %s", exc)
                await self._close_redis_client()

        async with self._lock:
            self._data.clear()