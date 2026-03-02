"""
Rate limiting implementations for the gateway auth service.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse, urlunparse
from .rate_limits.token_rate_limiter import TokenRateLimiter
from .rate_limits.redis_token_rate_limiter import RedisTokenRateLimiter
from .rate_limits.hybrid_token_rate_limiter import HybridTokenRateLimiter

import config as gw_config

try:
    redis: object
except ImportError:
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


def make_default_rate_limiter(
    limit: int,
    backend: str = "auto",
    redis_url: Optional[str] = None,
    *,
    socket_timeout: float = 1.0,
    max_connections: int = 50,
) -> TokenRateLimiter | HybridTokenRateLimiter:
    backend = (backend or "auto").strip().lower()
    strict = gw_config.GATEWAY_RATE_LIMIT_STRICT

    def _make_redis() -> RedisTokenRateLimiter:
        if not redis_url:
            raise RuntimeError("Redis URL not provided")
        return RedisTokenRateLimiter(limit, redis_url, socket_timeout=socket_timeout, max_connections=max_connections)

    if strict:
        try:
            r = _make_redis()
            logger.info("Gateway rate limiting backend: redis (strict) %s", _sanitize_redis_url(redis_url))
            return r
        except Exception as exc:
            logger.error("Redis init failed in strict mode: %s", exc)
            raise

    if backend in ("memory", "in-memory", "inmemory") or not redis_url:
        if backend == "redis" and not redis_url:
            logger.warning("GATEWAY_RATE_LIMIT_BACKEND=redis but URL not set; using in-memory")
        logger.info("Gateway rate limiting backend: in-memory")
        return TokenRateLimiter(limit)

    try:
        primary = _make_redis()
        logger.info("Gateway rate limiting backend: redis (%s)", _sanitize_redis_url(redis_url))
        return HybridTokenRateLimiter(primary, TokenRateLimiter(limit))
    except Exception as exc:
        logger.warning("Redis rate limiter init failed (%s), using in-memory fallback", type(exc).__name__)
        return TokenRateLimiter(limit)