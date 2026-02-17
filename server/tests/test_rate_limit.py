"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


import importlib
import os
import sys
import time
import unittest

from fastapi import HTTPException
from starlette.requests import Request


SAFE_ENV = {
    "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
    "CORS_ORIGINS": "http://localhost:5173",
    "CORS_ALLOW_CREDENTIALS": "true",
    "JWT_ALGORITHM": "RS256",
}


class _BrokenPrimaryLimiter:
    def hit(self, key: str, *, limit: int, window_seconds: int):
        raise RuntimeError("redis unavailable")


def _reload_rate_limit_module():
    os.environ.update(SAFE_ENV)
    for module_name in ("middleware.rate_limit", "config"):
        if module_name in sys.modules:
            del sys.modules[module_name]
    return importlib.import_module("middleware.rate_limit")


def _request_with_ip(ip_value: str) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/health",
        "headers": [(b"x-forwarded-for", ip_value.encode("utf-8"))],
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "query_string": b"",
    }
    return Request(scope)


class RateLimitTests(unittest.TestCase):
    def test_in_memory_limiter_blocks_then_recovers_next_window(self):
        module = _reload_rate_limit_module()
        limiter = module.InMemoryRateLimiter()

        self.assertTrue(limiter.hit("user:1", limit=2, window_seconds=1).allowed)
        self.assertTrue(limiter.hit("user:1", limit=2, window_seconds=1).allowed)
        self.assertFalse(limiter.hit("user:1", limit=2, window_seconds=1).allowed)

        time.sleep(1.1)
        self.assertTrue(limiter.hit("user:1", limit=2, window_seconds=1).allowed)

    def test_hybrid_limiter_falls_back_when_primary_fails(self):
        module = _reload_rate_limit_module()
        fallback = module.InMemoryRateLimiter()
        hybrid = module.HybridRateLimiter(_BrokenPrimaryLimiter(), fallback)
        module.rate_limiter = hybrid

        module.enforce_rate_limit(key="user:test", limit=1, window_seconds=60)
        with self.assertRaises(HTTPException):
            module.enforce_rate_limit(key="user:test", limit=1, window_seconds=60)

    def test_hybrid_limiter_deny_mode_blocks_when_redis_down(self):
        module = _reload_rate_limit_module()
        fallback = module.InMemoryRateLimiter()
        hybrid = module.HybridRateLimiter(_BrokenPrimaryLimiter(), fallback)
        module.rate_limiter = hybrid

        with self.assertRaises(HTTPException):
            module.enforce_rate_limit(key="user:test-deny", limit=1, window_seconds=60, fallback_mode="deny")

    def test_client_ip_uses_forwarded_header_when_proxy_trusted(self):
        module = _reload_rate_limit_module()
        previous = module.config.TRUST_PROXY_HEADERS
        module.config.TRUST_PROXY_HEADERS = True
        try:
            request = _request_with_ip("203.0.113.9")
            self.assertEqual(module.client_ip(request), "203.0.113.9")
        finally:
            module.config.TRUST_PROXY_HEADERS = previous


if __name__ == "__main__":
    unittest.main()
