"""
Hybrid Token Rate Limiter for Gateway Authentication Service

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import time
from fastapi import HTTPException
import logging

from .redis_token_rate_limiter import RedisTokenRateLimiter
from .token_rate_limiter import TokenRateLimiter

logger = logging.getLogger(__name__)

class HybridTokenRateLimiter:
    def __init__(self, primary: RedisTokenRateLimiter, fallback: TokenRateLimiter) -> None:
        self._primary = primary
        self._fallback = fallback
        self._last_warn = 0.0

    def enforce(self, key: str) -> None:
        try:
            self._primary.enforce(key)
        except HTTPException:
            raise
        except Exception as exc:
            now = time.monotonic()
            if now - self._last_warn > 30:
                logger.warning("Redis rate limiter unavailable, falling back: %s", type(exc).__name__)
                self._last_warn = now
            self._fallback.enforce(key)
            