"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

Unit tests for gateway auth service rate limiting and allowlist enforcement.
"""
import unittest

from fastapi import HTTPException
from starlette.requests import Request

from services.gateway_service import GatewayAuthService, TokenRateLimiter, HybridTokenRateLimiter


class _BrokenPrimaryRateLimiter:
    def enforce(self, key: str) -> None:
        raise RuntimeError("redis unavailable")


def _request(ip: str) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/api/gateway/validate",
        "headers": [(b"x-forwarded-for", ip.encode("utf-8"))],
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
        "query_string": b"",
    }
    return Request(scope)


class GatewayRateLimitTests(unittest.TestCase):
    def test_in_memory_gateway_limiter_blocks_after_threshold(self):
        limiter = TokenRateLimiter(limit_per_minute=1)
        limiter.enforce("client-a")
        with self.assertRaises(HTTPException):
            limiter.enforce("client-a")

    def test_hybrid_gateway_limiter_falls_back_to_memory(self):
        fallback = TokenRateLimiter(limit_per_minute=1)
        limiter = HybridTokenRateLimiter(_BrokenPrimaryRateLimiter(), fallback)

        limiter.enforce("client-b")
        with self.assertRaises(HTTPException):
            limiter.enforce("client-b")

    def test_allowlist_enforcement_rejects_non_allowed_ip(self):
        service = GatewayAuthService(rate_limit_per_minute=100, ip_allowlist="203.0.113.10")
        with self.assertRaises(HTTPException):
            service.enforce_ip_allowlist(_request("198.51.100.1"))


if __name__ == "__main__":
    unittest.main()
