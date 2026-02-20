"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Optional
from urllib.parse import urlparse, urlunparse

from fastapi import HTTPException, status

try:
    import redis
except Exception:
    redis = None

logger = logging.getLogger(__name__)

_MAX_IN_MEMORY_KEYS = 50_000


def _sanitize_redis_url(url: str) -> str:
    try:
        p = urlparse(url)
        host = f"{p.hostname}:{p.port}" if p.port else (p.hostname or "")
        return urlunparse(p._replace(netloc=host))
    except Exception:
        return "<redis-url>"


class TokenRateLimiter:
    def __init__(self, limit_per_minute: int) -> None:
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

            if key not in self._hits and len(self._hits) >= _MAX_IN_MEMORY_KEYS:
                oldest = min(self._hits, key=lambda k: self._hits[k][0])
                self._hits.pop(oldest, None)

            start, count = self._hits.get(key, (now, 0))
            if now - start >= 60:
                start, count = now, 0
            count += 1
            self._hits[key] = (start, count)

        if count > self._limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded")


class RedisTokenRateLimiter:
    def __init__(
        self,
        limit_per_minute: int,
        url: str,
        *,
        socket_timeout: float = 1.0,
        max_connections: int = 50,
    ) -> None:
        if redis is None:
            raise RuntimeError("redis library not available")
        self._limit = max(1, int(limit_per_minute))
        self._client = redis.from_url(
            url,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_timeout,
            max_connections=max_connections,
            decode_responses=True,
        )
        try:
            if not self._client.ping():
                raise RuntimeError("redis ping returned falsy response")
        except Exception as exc:
            raise RuntimeError(
                f"unable to connect to Redis at {_sanitize_redis_url(url)}: {type(exc).__name__}"
            ) from exc

    def enforce(self, key: str) -> None:
        bucket = f"beobs:rl:{key}:{int(time.time()) // 60}"
        # transaction=False: INCR is atomic; MULTI/EXEC adds contention under burst
        pipe = self._client.pipeline(transaction=False)
        pipe.incr(bucket)
        pipe.expire(bucket, 61)
        count, _ = pipe.execute()
        if int(count) > self._limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded")


class HybridTokenRateLimiter:
    def __init__(self, primary: RedisTokenRateLimiter, fallback: TokenRateLimiter) -> None:
        self._primary = primary
        self._fallback = fallback
        self._last_warn = 0.0

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
                    logger.warning(
                        "Redis rate limiter unavailable, falling back: %s",
                        type(exc).__name__,
                    )
                    self._last_warn = now
        self._fallback.enforce(key)


def make_default_rate_limiter(
    limit: int,
    backend: str = "auto",
    redis_url: str | None = None,
    *,
    socket_timeout: float = 1.0,
    max_connections: int = 50,
) -> TokenRateLimiter | HybridTokenRateLimiter:
    backend = (backend or "auto").strip().lower()

    if backend in ("memory", "in-memory", "inmemory") or not redis_url:
        if backend == "redis" and not redis_url:
            logger.warning("GATEWAY_RATE_LIMIT_BACKEND=redis but URL not set; using in-memory")
        logger.info("Gateway rate limiting backend: in-memory")
        return TokenRateLimiter(limit)

    try:
        primary = RedisTokenRateLimiter(
            limit,
            redis_url,
            socket_timeout=socket_timeout,
            max_connections=max_connections,
        )
        logger.info("Gateway rate limiting backend: redis (%s)", _sanitize_redis_url(redis_url))
        return HybridTokenRateLimiter(primary, TokenRateLimiter(limit))
    except Exception as exc:
        logger.warning(
            "Redis rate limiter init failed (%s), using in-memory fallback",
            type(exc).__name__,
        )
        return TokenRateLimiter(limit)