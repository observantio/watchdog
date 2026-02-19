from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Optional

from fastapi import HTTPException, status

try:
    import redis
except Exception:  # pragma: no cover - optional dependency
    redis = None

logger = logging.getLogger(__name__)


class TokenRateLimiter:
    """In-memory token-based rate limiter (per-minute buckets)."""

    def __init__(self, limit_per_minute: int):
        self._limit = max(1, int(limit_per_minute))
        self._hits: dict[str, tuple[float, int]] = {}
        self._lock = Lock()
        self._ops = 0

    def enforce(self, key: str) -> None:
        now = time.time()
        with self._lock:
            self._ops += 1
            if self._ops % 1024 == 0:
                cutoff = now - 120
                self._hits = {k: v for k, v in self._hits.items() if v[0] >= cutoff}

            start, count = self._hits.get(key, (now, 0))
            if now - start >= 60:
                start, count = now, 0
            count += 1
            self._hits[key] = (start, count)

        if count > self._limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded")


class RedisTokenRateLimiter:
    """Redis-backed per-minute token bucket implementation."""

    def __init__(self, limit_per_minute: int, url: str):
        if redis is None:
            raise RuntimeError("redis library not available")
        self._limit = max(1, int(limit_per_minute))
        self._client = redis.from_url(url, socket_timeout=0.25, socket_connect_timeout=0.25, decode_responses=True)

    def enforce(self, key: str) -> None:
        bucket = f"beobs:rl:{key}:{int(time.time()) // 60}"
        pipe = self._client.pipeline(transaction=True)
        pipe.incr(bucket)
        pipe.expire(bucket, 61)
        count, _ = pipe.execute()
        if int(count) > self._limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded")


class HybridTokenRateLimiter:
    """Primary/fallback wrapper that prefers `primary` and falls back to `fallback`.

    The `primary` argument may be any object implementing `enforce(key)`.
    This class is intentionally small and used by tests to inject failing primaries.
    """

    def __init__(self, primary, fallback):
        self._primary = primary
        self._fallback = fallback
        self._last_warn = 0.0
        self._logger = logging.getLogger(__name__)

    def enforce(self, key: str) -> None:
        if self._primary:
            try:
                self._primary.enforce(key)
                return
            except HTTPException:
                raise
            except Exception as exc:
                now = time.monotonic()
                if now - self._last_warn > 30:
                    self._logger.warning("Redis rate limiter unavailable, falling back: %s", exc)
                    self._last_warn = now
        self._fallback.enforce(key)


def make_default_rate_limiter(limit: int, backend: str = "auto", redis_url: str | None = None):
    """Factory used by `GatewayAuthService` to pick the backend at runtime."""
    backend = (backend or "auto").strip().lower()
    if backend in ("memory", "in-memory", "inmemory") or not redis_url:
        if backend == "redis" and not redis_url:
            logger.warning("GATEWAY_RATE_LIMIT_BACKEND=redis but URL not set; using in-memory")
        logger.info("Gateway rate limiting backend: in-memory")
        return TokenRateLimiter(limit)

    try:
        primary = RedisTokenRateLimiter(limit, redis_url)
        logger.info("Gateway rate limiting backend: redis")
        return HybridTokenRateLimiter(primary, TokenRateLimiter(limit))
    except Exception as exc:
        logger.warning("Redis rate limiter init failed, using in-memory: %s", exc)
        return TokenRateLimiter(limit)
