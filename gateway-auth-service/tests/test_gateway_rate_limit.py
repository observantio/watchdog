"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
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
            # reload both config and service so the new flag is picked up
            importlib.reload(__import__("services.config", fromlist=["*"]))
            importlib.reload(__import__("services.gateway_service", fromlist=["*"]))
            from services.gateway_service import GatewayAuthService
            service = GatewayAuthService(rate_limit_per_minute=100, ip_allowlist="")
            # should not raise
            service.enforce_ip_allowlist(_request("198.51.100.1"))
        finally:
            if prev is None:
                os.environ.pop("GATEWAY_ALLOWLIST_FAIL_OPEN", None)
            else:
                os.environ["GATEWAY_ALLOWLIST_FAIL_OPEN"] = prev
            importlib.reload(__import__("services.config", fromlist=["*"]))
            importlib.reload(__import__("services.gateway_service", fromlist=["*"]))

    def test_validate_otlp_token_raises_database_unavailable_on_db_error(self):
        service = GatewayAuthService(rate_limit_per_minute=100, ip_allowlist="")

        from sqlalchemy.exc import SQLAlchemyError

        class BrokenSession:
            def __enter__(self):
                raise SQLAlchemyError("db down")

            def __exit__(self, exc_type, exc, tb):
                return False

        # patch the module-level SessionLocal used by the service
        import services.gateway_service as svc_mod
        prev = svc_mod.db_models.SessionLocal
        try:
            svc_mod.db_models.SessionLocal = BrokenSession
            with self.assertRaises(svc_mod.DatabaseUnavailable):
                service.validate_otlp_token("tok")
        finally:
            svc_mod.db_models.SessionLocal = prev

    def test_validate_endpoint_returns_503_on_database_unavailable(self):
        # Ensure allowlist permits our test IP
        import ipaddress
        from routers import gateway_router

        gateway_router._service._networks = [ipaddress.ip_network("127.0.0.1/32")]

        # stub the validate_otlp_token to simulate DB outage
        # use the same DatabaseUnavailable class that the router has imported,
        # otherwise earlier reloads can leave us with two distinct objects and the
        # except clause in the router won't match.
        def _boom(token):
            raise gateway_router.DatabaseUnavailable("db down")

        prev = gateway_router._service.validate_otlp_token
        try:
            gateway_router._service.validate_otlp_token = _boom
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
            # router returns sanitized 503 and logs a friendly warning (no SQL internals)
            self.assertEqual(cm.exception.status_code, 503)
            self.assertEqual(cm.exception.detail, "Auth database unavailable")
            log_output = "\n".join(log_ctx.output)
            self.assertIn("Auth database unavailable", log_output)
            self.assertNotIn("SQLAlchemy", log_output)
            self.assertNotIn("Traceback", log_output)
        finally:
            gateway_router._service.validate_otlp_token = prev


if __name__ == "__main__":
    unittest.main()
