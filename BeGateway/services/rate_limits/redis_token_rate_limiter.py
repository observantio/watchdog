"""
Redis Token Rate Limiter for Gateway Authentication Service

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations
import time
from urllib.parse import urlparse, urlunparse
from fastapi import HTTPException

try:
    import redis
    redis: object
except ImportError:
    redis = None
    
def _sanitize_redis_url(url: str) -> str:
    try:
        p = urlparse(url)
        host = f"{p.hostname}:{p.port}" if p.port else (p.hostname or "")
        return urlunparse(p._replace(netloc=host))
    except Exception:
        return "<redis-url>"


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
        pipe = self._client.pipeline(transaction=False)
        pipe.incr(bucket)
        pipe.expire(bucket, 61)
        count, _ = pipe.execute()
        if int(count) > self._limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded")