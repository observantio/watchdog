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

# expose redis module variable for tests that patch it
try:
    import redis  # type: ignore
    _redis_available = True
except Exception:
    redis = None  # type: ignore
    _redis_available = False

logger = logging.getLogger(__name__)

from .memory import TokenCache  # noqa: E402
from .redis import RedisTokenCache  # noqa: E402

__all__ = ["TokenCache", "RedisTokenCache", "make_token_cache", "redis"]


def make_token_cache(ttl: int, redis_url: Optional[str] = None) -> TokenCache | RedisTokenCache:
    if redis_url:
        try:
            cache = RedisTokenCache(ttl, redis_url)
            logger.info("Gateway token cache backend: redis (%s)", redis_url)
            return cache
        except Exception as exc:
            logger.warning(
                "Redis token cache init failed (%s), using in-memory fallback", type(exc).__name__
            )
    logger.info("Gateway token cache backend: in-memory")
    return TokenCache(ttl)
