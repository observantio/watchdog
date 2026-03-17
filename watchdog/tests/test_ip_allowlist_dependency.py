"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import os
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql://safeuser:safePass_123@db:5432/watchdog")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")

from fastapi import HTTPException
from starlette.requests import Request

from middleware.dependencies import enforce_ip_allowlist
from config import config


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


class IpAllowlistDependencyTests(unittest.TestCase):
    def test_enforce_ip_allowlist_blocks_when_empty_by_default(self):
        previous = config.ALLOWLIST_FAIL_OPEN
        try:
            config.ALLOWLIST_FAIL_OPEN = False
            req = _request_with_ip("198.51.100.1")
            with self.assertRaises(HTTPException):
                enforce_ip_allowlist(req, allowlist="", scope="test")
        finally:
            config.ALLOWLIST_FAIL_OPEN = previous

    def test_enforce_ip_allowlist_allows_when_fail_open_enabled(self):
        previous = config.ALLOWLIST_FAIL_OPEN
        try:
            config.ALLOWLIST_FAIL_OPEN = True
            req = _request_with_ip("198.51.100.1")
            enforce_ip_allowlist(req, allowlist="", scope="test")
        finally:
            config.ALLOWLIST_FAIL_OPEN = previous


if __name__ == "__main__":
    unittest.main()
