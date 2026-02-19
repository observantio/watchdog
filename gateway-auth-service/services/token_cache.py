from __future__ import annotations

import time
from threading import Lock
from typing import Optional


class TokenCache:
    """Simple TTL cache for validated tokens.

    API: get(token) -> (hit: bool, org_id: Optional[str])
         set(token, org_id)
    """

    def __init__(self, ttl: int):
        self._ttl = int(ttl)
        self._cache: dict[str, tuple[Optional[str], float]] = {}
        self._lock = Lock()

    def get(self, token: str) -> tuple[bool, Optional[str]]:
        with self._lock:
            entry = self._cache.get(token)
        if entry and time.monotonic() - entry[1] < self._ttl:
            return True, entry[0]
        return False, None

    def set(self, token: str, org_id: Optional[str]) -> None:
        with self._lock:
            self._cache[token] = (org_id, time.monotonic())
            if len(self._cache) % 512 == 0:
                cutoff = time.monotonic() - self._ttl
                self._cache = {k: v for k, v in self._cache.items() if v[1] >= cutoff}
