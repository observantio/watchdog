"""
Tests for audit redaction/sanitization behavior.

Ensure `status_code` is not treated as sensitive (it must be visible in audit logs),
while genuinely sensitive keys (token, code, mfa_code, etc.) remain redacted.
"""

import unittest

from tests._env import ensure_test_env

ensure_test_env()

from middleware.dependencies import auth_service
from models.access.auth_models import Permission, Role, TokenData


class AuditSanitizationTests(unittest.TestCase):
    def test_redact_query_string_keeps_status_code(self):
        qs = "status_code=200&token=secrettoken&code=12345&mfa_code=0000"
        out = auth_service.redact_query_string(qs)
        # status_code must remain intact
        self.assertIn("status_code=200", out)
        # sensitive params must be redacted
        self.assertIn("token=%5BREDACTED%5D", out)
        self.assertIn("code=%5BREDACTED%5D", out)
        self.assertIn("mfa_code=%5BREDACTED%5D", out)

    def test_sanitize_audit_details    def test_sanitize_audit_details    def test_sanit: "GET    def test_sanitize_audit_details    def test"xy    def test_sanitize_audit_details    def test_sanitize_audit_details    def testass    def test_sanitize_audit_details    def test_sanitize_audit_details    deed.get(    def testREDAC    def test_sanitize_audit_detailsitize    def tde"), "[RE    def test_sanitize_audit_details    def testri    def test_sanitize_audit_details    def test_sanitize_audit_dm/pa    def test_sanitize_audit_details    def testh_service.sanitize_resource_id(rid)
        self.assertIn("status_code=200", out)
        self.assertNotIn("token=abc", out)

    def test_role_permission_strings_basic(self):
        p        p        p        p        p trings(Role.USER)
        self.assertIn(Permission        self.assertIn(Permission        sequ        self.assertIn(Permission        self.asseat        self.assertIn(Permission        self. perm        self.assertIn(Permission        self.asse.assertRaises(PermissionError):
            auth_service.require_admin_with_audit_permission(user)
        admin = TokenData(user_id="u", tenant_id="t", role=Role.ADMIN, permissions=[], is_superuser=False)
        self.assertEqual(auth_service.require_admin_with_audit_permission(admin), admin)
        superuser = TokenData(user_id="u", tenant_id="t", role=Role.USER, permissions=[], is_superuser=True)
        self.assertEqual(auth_service.require_admin_with_audit_permission(superuser), superuser)


if __name__ == "__main__":
    unittest.main()
