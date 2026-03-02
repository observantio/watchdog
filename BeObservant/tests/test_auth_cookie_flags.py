"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import importlib
import os

os.environ.setdefault("DATABASE_URL", "postgresql://safeuser:safePass_123@db:5432/beobservant")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
import unittest

from services.common.cookies import cookie_secure
from services.auth.helper import set_auth_cookie

from starlette.requests import Request
from fastapi.responses import Response

import middleware.dependencies as deps_module
from routers.access import auth_router
from config import config


def _request_with_scheme_and_headers(scheme: str = "http", headers: dict | None = None) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/api/auth/login",
        "headers": [(k.encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": ("127.0.0.1", 12345),
        "scheme": scheme,
        "query_string": b"",
    }
    return Request(scope)


class AuthCookieFlagsTests(unittest.TestCase):
    def test_set_auth_cookie_secure_based_on_trusted_forwarded_proto(self):
        previous_trust = config.TRUST_PROXY_HEADERS
        try:
            config.TRUST_PROXY_HEADERS = True
            req = _request_with_scheme_and_headers(headers={"x-forwarded-proto": "https"})
            self.assertTrue(cookie_secure(req))

            config.TRUST_PROXY_HEADERS = False
            req2 = _request_with_scheme_and_headers(headers={"x-forwarded-proto": "https"})
            self.assertFalse(cookie_secure(req2))
        finally:
            config.TRUST_PROXY_HEADERS = previous_trust

    def test_set_auth_cookie_forced_secure_in_production(self):
        prev_force = config.FORCE_SECURE_COOKIES
        prev_prod = config.IS_PRODUCTION
        try:
            config.IS_PRODUCTION = True
            config.FORCE_SECURE_COOKIES = True

            req = _request_with_scheme_and_headers(scheme="http", headers={})
            resp = Response()
            set_auth_cookie(req, resp, token="dummy-token")
            hdr = resp.headers.get("set-cookie", "")
            self.assertIn("Secure", hdr)
        finally:
            config.FORCE_SECURE_COOKIES = prev_force
            config.IS_PRODUCTION = prev_prod


if __name__ == "__main__":
    unittest.main()
