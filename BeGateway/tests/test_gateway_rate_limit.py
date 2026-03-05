"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import unittest

from fastapi import HTTPException
from starlette.requests import Request

from services.gateway_service import GatewayAuthService
from services.rate_limit import TokenRateLimiter, HybridTokenRateLimiter


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

    def test_allowlist_blocks_when_empty_by_default(self):
        service = GatewayAuthService(rate_limit_per_minute=100, ip_allowlist="")
        with self.assertRaises(HTTPException):
            service.enforce_ip_allowlist(_request("198.51.100.1"))

    def test_allowlist_allows_when_fail_open_env_set(self):
        import importlib
        import os

        prev = os.environ.get("GATEWAY_ALLOWLIST_FAIL_OPEN")
        try:
            os.environ["GATEWAY_ALLOWLIST_FAIL_OPEN"] = "true"
            importlib.reload(__import__("config", fromlist=["*"]))
            importlib.reload(__import__("services.gateway_service", fromlist=["*"]))
            from services.gateway_service import GatewayAuthService
            service = GatewayAuthService(rate_limit_per_minute=100, ip_allowlist="")
            service.enforce_ip_allowlist(_request("198.51.100.1"))
        finally:
            if prev is None:
                os.environ.pop("GATEWAY_ALLOWLIST_FAIL_OPEN", None)
            else:
                os.environ["GATEWAY_ALLOWLIST_FAIL_OPEN"] = prev
            importlib.reload(__import__("config", fromlist=["*"]))
            importlib.reload(__import__("services.gateway_service", fromlist=["*"]))

    def test_validate_otlp_token_raises_database_unavailable_on_api_error(self):
        service = GatewayAuthService(rate_limit_per_minute=100, ip_allowlist="")
        from services import gateway_service as gw_mod

        def boom(self, token):
            raise gw_mod.DatabaseUnavailable("api down")

        prev = GatewayAuthService._fetch_org_from_api
        try:
            GatewayAuthService._fetch_org_from_api = boom
            with self.assertRaises(gw_mod.DatabaseUnavailable):
                service.validate_otlp_token("tok")
        finally:
            GatewayAuthService._fetch_org_from_api = prev

    def test_validate_endpoint_returns_503_on_database_unavailable(self):
        import ipaddress
        from routers import gateway_router

        gateway_router.service._networks = [ipaddress.ip_network("127.0.0.1/32")]
        def _boom(self, token):
            raise gateway_router.DatabaseUnavailable("db down")

        prev = GatewayAuthService.validate_otlp_token
        try:
            GatewayAuthService.validate_otlp_token = _boom
            scope = {
                "type": "http",
                "http_version": "1.1",
                "method": "GET",
                "path": "/api/gateway/validate",
                "headers": [(b"x-otlp-token", b"tok"), (b"x-forwarded-for", b"127.0.0.1")],
                "client": ("127.0.0.1", 1234),
                "scheme": "http",
                "query_string": b"",
            }
            req = Request(scope)
            import asyncio
            with self.assertLogs("routers.gateway_router", level="WARNING") as log_ctx:
                with self.assertRaises(HTTPException) as cm:
                    asyncio.run(gateway_router.validate_otlp_token(req))
            self.assertEqual(cm.exception.status_code, 503)
            self.assertEqual(cm.exception.detail, "Auth backend unavailable")
            log_output = "\n".join(log_ctx.output)
            self.assertIn("Auth backend unavailable", log_output)
            self.assertNotIn("Traceback", log_output)
        finally:
            GatewayAuthService.validate_otlp_token = prev


    def test_token_cache_hits(self):
        service = GatewayAuthService(rate_limit_per_minute=100, ip_allowlist="")
        calls: list[str] = []

        def fetch(self, token):
            calls.append(token)
            return "org42"

        prev = GatewayAuthService._fetch_org_from_api
        try:
            GatewayAuthService._fetch_org_from_api = fetch
            self.assertEqual(service.validate_otlp_token("tok"), "org42")
            self.assertEqual(calls, ["tok"])
            self.assertEqual(service.validate_otlp_token("tok"), "org42")
            self.assertEqual(calls, ["tok"])
        finally:
            GatewayAuthService._fetch_org_from_api = prev

    def test_token_cache_caches_negative(self):
        service = GatewayAuthService(rate_limit_per_minute=100, ip_allowlist="")
        calls: list[str] = []

        def fetch(self, token):
            calls.append(token)
            return None

        prev = GatewayAuthService._fetch_org_from_api
        try:
            GatewayAuthService._fetch_org_from_api = fetch
            self.assertIsNone(service.validate_otlp_token("bad"))
            self.assertIsNone(service.validate_otlp_token("bad"))
            self.assertEqual(calls, ["bad"])
        finally:
            GatewayAuthService._fetch_org_from_api = prev

    def test_make_token_cache_fallback(self):
        import services.token_cache as tc_mod
        prev_redis = getattr(tc_mod, "redis", None)
        tc_mod.redis = None
        try:
            cache = tc_mod.make_token_cache(5, "redis://doesnotmatter")
            self.assertIsInstance(cache, tc_mod.TokenCache)
        finally:
            tc_mod.redis = prev_redis

    def test_strict_rate_limiter_requires_redis(self):
        import config as cfg
        import services.rate_limit as rl_mod
        from services.rate_limit import make_default_rate_limiter, RedisTokenRateLimiter

        prev_strict_cfg = cfg.GATEWAY_RATE_LIMIT_STRICT
        prev_strict_rl = rl_mod.gw_config.GATEWAY_RATE_LIMIT_STRICT
        cfg.GATEWAY_RATE_LIMIT_STRICT = True
        rl_mod.gw_config.GATEWAY_RATE_LIMIT_STRICT = True

        orig_init = RedisTokenRateLimiter.__init__
        try:
            def fail(self, *args, **kwargs):
                raise RuntimeError("no redis")

            RedisTokenRateLimiter.__init__ = fail
            with self.assertRaises(RuntimeError):
                make_default_rate_limiter(1, backend="redis", redis_url=None)
            with self.assertRaises(RuntimeError):
                make_default_rate_limiter(1, backend="redis", redis_url="redis://localhost")
            def ok_init(self, limit, url, *args, **kwargs):
                self._limit = limit
                self.enforce = lambda key: None

            RedisTokenRateLimiter.__init__ = ok_init
            limiter = make_default_rate_limiter(2, backend="redis", redis_url="redis://localhost")
            self.assertIsInstance(limiter, RedisTokenRateLimiter)
        finally:
            cfg.GATEWAY_RATE_LIMIT_STRICT = prev_strict_cfg
            rl_mod.gw_config.GATEWAY_RATE_LIMIT_STRICT = prev_strict_rl
            RedisTokenRateLimiter.__init__ = orig_init

    if __name__ == "__main__":
        unittest.main()
