"""
Redis-backed token cache for the gateway auth service.

Extracted from the previous ``TokenCache`` module; this implementation assumes
that the ``redis`` library is available and that a connection can be
established during initialization. Errors will propagate so that callers can
fall back or fail as appropriate.
"""

from __future__ import annotations

import logging
import hashlib
from typing import Optional

try:
    import redis
    _redis_available = True
except Exception:
    redis = None  
    _redis_available = False

logger = logging.getLogger(__name__)


class RedisTokenCache:
    def __init__(
        self,
        ttl: int,
        url: str,
        *,
        socket_timeout: float = 1.0,
        max_connections: int = 50,
    ) -> None:
        if not _redis_available:
            raise RuntimeError("redis library not available")
        self._ttl = int(ttl)
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
            raise RuntimeError(f"unable to connect to Redis at {url}: {type(exc).__name__}") from exc

    @staticmethod
    def _cache_key(token: str) -> str:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return f"beobs:tok:{digest}"

    def get(self, token: str) -> tuple[bool, Optional[str]]:
        val = self._client.get(self._cache_key(token))
        if val is None:
            return False, None
        return True, val or None

    def set(self, token: str, org_id: Optional[str]) -> None:
        self._client.setex(self._cache_key(token), self._ttl, org_id or "")
