"""
Tests for audit redaction/sanitization behavior.

Ensure `status_code` is not treated as sensitive (it must be visible in audit logs),
while genuinely sensitive keys (token, code, mfa_code, etc.) remain redacted.
"""

import unittest

from tests._env import ensure_test_env

ensure_test_env()

import routers.access.auth_router as auth_router


class AuditSanitizationTests(unittest.TestCase):
    def test_redact_query_string_keeps_status_code(self):
        qs = "status_code=200&token=secrettoken&code=12345&mfa_code=0000"
        out = auth_router._redact_query_string(qs)
        # status_code must remain intact
        self.assertIn("status_code=200", out)
        # sensitive params must be redacted
        self.assertIn("token=%5BREDACTED%5D", out)
        self.assertIn("code=%5BREDACTED%5D", out)
        self.assertIn("mfa_code=%5BREDACTED%5D", out)

    def test_sanitize_audit_details_keeps_status_code(self):
        details = {"method": "GET", "status_code": 200, "token": "abc", "code": "xyz"}
        sanitized = auth_router._sanitize_audit_details(details)
        self.assertEqual(sanitized.get("status_code"), 200)
        self.assertEqual(sanitized.get("token"), "[REDACTED]")
        self.assertEqual(sanitized.get("code"), "[REDACTED]")


if __name__ == "__main__":
    unittest.main()
