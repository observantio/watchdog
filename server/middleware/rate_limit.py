"""
Simple in-process rate limiting helpers.

This provides pragmatic spam protection without adding infrastructure.
For true multi-instance scalability, replace the backing store with Redis
or an API gateway rate limiter.
"""

from __future__ import annotations

import logging
import os
import time
import threading
from dataclasses import dataclass
from typing import Dict, Tuple, Optional
from ipaddress import ip_address, ip_network

from fastapi import HTTPException, status, Request
from config import config

try:
    import redis
except Exception:
    redis = None


logger = logging.getLogger(__name__)


@dataclass
class RateLimitState:
    window_start: float
    count: int


class InMemoryRateLimiter:
    """Fixed-window rate limiter (per process)."""

    def __init__(self, *, gc_every: int = 1024, stale_after_seconds: int = 3600) -> None:
        self._lock = threading.Lock()
        self._states: Dict[str, RateLimitState] = {}
        self._gc_every = max(100, int(gc_every))
        self._stale_after_seconds = max(60, int(stale_after_seconds))
        self._ops = 0

    def _cleanup(self, now: float, window_seconds: int) -> None:
        self._ops += 1
        if self._ops % self._gc_every != 0:
            return
        threshold = now - max(window_seconds * 2, self._stale_after_seconds)
        stale_keys = [key for key, state in self._states.items() if state.window_start < threshold]
        for key in stale_keys:
            self._states.pop(key, None)

    def hit(self, key: str, *, limit: int, window_seconds: int) -> Tuple[bool, int, int]:
        """Record a hit and return (allowed, remaining, retry_after_seconds)."""
        if limit <= 0:
            return True, 0, 0  

        now = time.time()
        window_seconds = int(window_seconds)
        if window_seconds <= 0:
            return True, 0, 0

        with self._lock:
            self._cleanup(now, window_seconds)
            st = self._states.get(key)
            if st is None or (now - st.window_start) >= window_seconds:
                st = RateLimitState(window_start=now, count=0)
                self._states[key] = st

            st.count += 1
            allowed = st.count <= limit
            remaining = max(0, limit - st.count)
            retry_after = max(0, int(window_seconds - (now - st.window_start)))
            return allowed, remaining, retry_after


class RedisFixedWindowRateLimiter:
    """Redis-backed fixed-window limiter."""

    def __init__(self, redis_url: str, *, key_prefix: str = "beobs:rl", socket_timeout: float = 0.25) -> None:
        if redis is None:
            raise RuntimeError("redis package is not installed")
        self._key_prefix = key_prefix
        self._client = redis.from_url(
            redis_url,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_timeout,
            decode_responses=True,
        )

    def hit(self, key: str, *, limit: int, window_seconds: int) -> Tuple[bool, int, int]:
        if limit <= 0:
            return True, 0, 0

        window_seconds = int(window_seconds)
        if window_seconds <= 0:
            return True, 0, 0

        now = int(time.time())
        window_id = now // window_seconds
        bucket_key = f"{self._key_prefix}:{key}:{window_id}"
        retry_after = max(1, window_seconds - (now % window_seconds))

        pipe = self._client.pipeline(transaction=True)
        pipe.incr(bucket_key)
        pipe.expire(bucket_key, window_seconds + 1)
        current, _ = pipe.execute()

        count = int(current)
        allowed = count <= limit
        remaining = max(0, limit - count)
        return allowed, remaining, retry_after


class HybridRateLimiter:
    """Redis-first limiter with in-memory fallback when Redis is unavailable."""

    def __init__(
        self,
        redis_limiter: Optional[RedisFixedWindowRateLimiter],
        fallback_limiter: InMemoryRateLimiter,
    ) -> None:
        self._redis_limiter = redis_limiter
        self._fallback_limiter = fallback_limiter
        self._last_warning = 0.0

    def hit(self, key: str, *, limit: int, window_seconds: int) -> Tuple[bool, int, int]:
        if self._redis_limiter is not None:
            try:
                return self._redis_limiter.hit(key, limit=limit, window_seconds=window_seconds)
            except Exception as exc:
                now = time.monotonic()
                if now - self._last_warning > 30:
                    logger.warning("Redis rate limiter unavailable, falling back to in-memory limiter: %s", exc)
                    self._last_warning = now
        return self._fallback_limiter.hit(key, limit=limit, window_seconds=window_seconds)


def _build_rate_limiter() -> HybridRateLimiter:
    backend = (os.getenv("RATE_LIMIT_BACKEND", "auto") or "auto").strip().lower()
    redis_url = (os.getenv("RATE_LIMIT_REDIS_URL", "") or "").strip()

    fallback = InMemoryRateLimiter()
    if backend in {"memory", "in-memory", "inmemory"}:
        return HybridRateLimiter(None, fallback)

    if not redis_url:
        if backend == "redis":
            logger.warning("RATE_LIMIT_BACKEND=redis but RATE_LIMIT_REDIS_URL is not set; using in-memory limiter")
        return HybridRateLimiter(None, fallback)

    try:
        redis_limiter = RedisFixedWindowRateLimiter(redis_url)
        logger.info("Using Redis-backed rate limiter")
        return HybridRateLimiter(redis_limiter, fallback)
    except Exception as exc:
        logger.warning("Failed to initialize Redis rate limiter, using in-memory fallback: %s", exc)
        return HybridRateLimiter(None, fallback)


rate_limiter = _build_rate_limiter()


def client_ip(request: Request) -> str:
    def _trusted_proxy_peer() -> bool:
        if not config.TRUST_PROXY_HEADERS:
            return False
        trusted_cidrs = getattr(config, "TRUSTED_PROXY_CIDRS", []) or []
        if not trusted_cidrs:
            return True

        direct = (request.client.host if request.client else "").strip()
        valid_direct = _valid_ip(direct)
        if not valid_direct:
            return False

        try:
            peer_ip = ip_address(valid_direct)
            for cidr in trusted_cidrs:
                try:
                    if peer_ip in ip_network(cidr, strict=False):
                        return True
                except ValueError:
                    continue
        except ValueError:
            return False
        return False

    def _valid_ip(value: str) -> Optional[str]:
        candidate = (value or "").strip()
        if not candidate:
            return None
        try:
            ip_address(candidate)
            return candidate
        except ValueError:
            return None

    if _trusted_proxy_peer():
        forwarded_for = (request.headers.get("x-forwarded-for") or "").strip()
        if forwarded_for:
            first = forwarded_for.split(",", 1)[0].strip()
            valid_first = _valid_ip(first)
            if valid_first:
                return valid_first

        real_ip = (request.headers.get("x-real-ip") or "").strip()
        valid_real_ip = _valid_ip(real_ip)
        if valid_real_ip:
            return valid_real_ip

    direct = (request.client.host if request.client else "unknown").strip()
    return _valid_ip(direct) or "unknown"


def enforce_rate_limit(
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> None:
    allowed, _remaining, retry_after = rate_limiter.hit(key, limit=limit, window_seconds=window_seconds)
    if allowed:
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many requests",
        headers={"Retry-After": str(retry_after)},
    )


def enforce_ip_rate_limit(
    request: Request,
    *,
    scope: str,
    limit: int,
    window_seconds: int,
) -> None:
    ip = client_ip(request)
    if ip == "unknown":
        logger.warning("Client IP could not be resolved for scope=%s; applying strict unknown-IP bucket", scope)
    enforce_rate_limit(key=f"ip:{ip}:{scope}", limit=limit, window_seconds=window_seconds)

