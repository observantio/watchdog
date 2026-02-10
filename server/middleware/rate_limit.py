"""
Simple in-process rate limiting helpers.

This provides pragmatic spam protection without adding infrastructure.
For true multi-instance scalability, replace the backing store with Redis
or an API gateway rate limiter.
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Dict, Tuple, Optional

from fastapi import HTTPException, status, Request


@dataclass
class RateLimitState:
    window_start: float
    count: int


class InMemoryRateLimiter:
    """Fixed-window rate limiter (per process)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: Dict[str, RateLimitState] = {}

    def hit(self, key: str, *, limit: int, window_seconds: int) -> Tuple[bool, int, int]:
        """Record a hit and return (allowed, remaining, retry_after_seconds)."""
        if limit <= 0:
            return True, 0, 0  

        now = time.time()
        window_seconds = int(window_seconds)
        if window_seconds <= 0:
            return True, 0, 0

        with self._lock:
            st = self._states.get(key)
            if st is None or (now - st.window_start) >= window_seconds:
                st = RateLimitState(window_start=now, count=0)
                self._states[key] = st

            st.count += 1
            allowed = st.count <= limit
            remaining = max(0, limit - st.count)
            retry_after = max(0, int(window_seconds - (now - st.window_start)))
            return allowed, remaining, retry_after


rate_limiter = InMemoryRateLimiter()


def client_ip(request: Request) -> str:
    return (request.client.host if request.client else "unknown").strip()


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
    enforce_rate_limit(key=f"ip:{ip}:{scope}", limit=limit, window_seconds=window_seconds)

