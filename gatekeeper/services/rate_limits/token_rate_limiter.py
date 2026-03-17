"""
Token Rate Limiter for Gateway Authentication Service

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import time
from threading import Lock
from fastapi import HTTPException, status

MAX_IN_MEMORY_KEYS = 50_000


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

            if key not in self._hits and len(self._hits) >= MAX_IN_MEMORY_KEYS:
                oldest = min(self._hits, key=lambda k: self._hits[k][0])
                self._hits.pop(oldest, None)

            start, count = self._hits.get(key, (now, 0))
            if now - start >= 60:
                start, count = now, 0
            count += 1
            self._hits[key] = (start, count)

        if count > self._limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded")
