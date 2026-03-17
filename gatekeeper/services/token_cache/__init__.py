"""
Token cache package for gateway authentication service.

This package exposes a simple factory ``make_token_cache`` which returns either
an in-memory ``TokenCache`` or a ``RedisTokenCache`` instance depending on
configuration. The package also re-exports the classes and provides a
``redis`` attribute for compatibility with existing tests.
"""

from __future__ import annotations

import logging
from typing import Optional

from ._redis_compat import redis
from .memory import TokenCache
from .redis import RedisTokenCache

logger = logging.getLogger(__name__)

__all__ = ["TokenCache", "RedisTokenCache", "make_token_cache", "redis"]


def make_token_cache(ttl: int, redis_url: Optional[str] = None) -> TokenCache | RedisTokenCache:
    if redis_url:
        try:
            cache = RedisTokenCache(ttl, redis_url)
            logger.info("Gateway token cache backend: redis (%s)", redis_url)
            return cache
        except RuntimeError as exc:
            logger.warning(
                "Redis token cache init failed (%s), using in-memory fallback", type(exc).__name__
            )
    logger.info("Gateway token cache backend: in-memory")
    return TokenCache(ttl)
