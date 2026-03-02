"""
In-memory token cache for the gateway auth service.


Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.
"""

from __future__ import annotations

import time
import hashlib
from threading import Lock
from typing import Optional

DEFAULT_MAX_SIZE = 50_000
GC_INTERVAL = 512

class TokenCache:
    def __init__(self, ttl: int, max_size: int = DEFAULT_MAX_SIZE) -> None:
        self._ttl = int(ttl)
        self._max_size = max(256, int(max_size))
        self._cache: dict[str, tuple[Optional[str], float]] = {}
        self._lock = Lock()
        self._ops = 0

    @staticmethod
    def _cache_key(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def get(self, token: str) -> tuple[bool, Optional[str]]:
        key = self._cache_key(token)
        with self._lock:
            entry = self._cache.get(key)
        if entry is None:
            return False, None
        org_id, ts = entry
        if time.monotonic() - ts < self._ttl:
            return True, org_id
        with self._lock:
            self._cache.pop(key, None)
        return False, None

    def set(self, token: str, org_id: Optional[str]) -> None:
        key = self._cache_key(token)
        now = time.monotonic()
        with self._lock:
            self._cache[key] = (org_id, now)
            self._ops += 1
            if self._ops % GC_INTERVAL == 0:
                self._gc(now)
            elif len(self._cache) > self._max_size:
                self._evict_oldest()

    def _gc(self, now: float) -> None:
        cutoff = now - self._ttl
        self._cache = {k: v for k, v in self._cache.items() if v[1] >= cutoff}

    def _evict_oldest(self) -> None:
        oldest = min(self._cache, key=lambda k: self._cache[k][1])
        self._cache.pop(oldest, None)
