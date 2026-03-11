"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import unittest
from unittest.mock import patch, MagicMock

from tests._env import ensure_test_env
from fastapi.testclient import TestClient

ensure_test_env()

from models.access.auth_models import Permission, ROLE_PERMISSIONS, Role
from services.auth.permission_defs import PERMISSION_DEFS
from services.auth.auth_ops import validate_otlp_token
from config import config


class _BrokenContext:
    def __enter__(self):
        raise RuntimeError("db down")

    def __exit__(self, exc_type, exc, tb):
        return False


class AuditComplianceFeatureTests(unittest.TestCase):
    def test_audit_permission_in_enum_and_admin_defaults(self):
        self.assertEqual(Permission.READ_AUDIT_LOGS.value, "read:audit_logs")
        self.assertIn(Permission.READ_AUDIT_LOGS, ROLE_PERMISSIONS[Role.ADMIN])

    def test_audit_permission_in_permission_catalog(self):
        names = {item[0] for item in PERMISSION_DEFS}
        self.assertIn("read:audit_logs", names)

    @patch("services.auth.auth_ops.get_db_session", return_value=_BrokenContext())
    def test_validate_otlp_token_handles_internal_errors(self, _mock_db):
        service = MagicMock()
        result = validate_otlp_token(service, "token-1")
        self.assertIsNone(result)
        service.logger.warning.assert_called_once()

    @patch("services.auth.auth_ops.get_db_session")
    def test_validate_otlp_token_accepts_configured_default_token(self, mock_db):
        service = MagicMock()
        original_default_token = config.DEFAULT_OTLP_TOKEN
        original_default_org = config.DEFAULT_ORG_ID
        try:
            config.DEFAULT_OTLP_TOKEN = "default-token"
            config.DEFAULT_ORG_ID = "default-org"
            result = validate_otlp_token(service, "default-token")
        finally:
            config.DEFAULT_OTLP_TOKEN = original_default_token
            config.DEFAULT_ORG_ID = original_default_org

        self.assertEqual(result, "default-org")
        mock_db.assert_not_called()

    def test_internal_otlp_validate_endpoint(self):
        import os
        import sys
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        import database
        from services import database_auth_service as das_mod
        with patch.object(database, "init_database", lambda *args, **kwargs: None), patch.object(
            database, "init_db", lambda *args, **kwargs: None
        ), patch.object(das_mod.DatabaseAuthService, "_lazy_init", lambda self: None), patch.object(
            das_mod.DatabaseAuthService, "_ensure_default_setup", lambda self: None
        ), patch.object(das_mod.DatabaseAuthService, "backfill_otlp_tokens", lambda self: None):
            # reload main in case it has been imported earlier by other tests
            sys.modules.pop("main", None)
            from main import app

            client = TestClient(app)
            original_internal_token = config.GATEWAY_INTERNAL_SERVICE_TOKEN
            config.GATEWAY_INTERNAL_SERVICE_TOKEN = "internal-test-token"
            headers = {"x-internal-token": "internal-test-token"}

            try:
                legacy = client.get("/api/internal/otlp/validate", params={"token": "tok"}, headers=headers)
                self.assertEqual(legacy.status_code, 410)

                with patch(
                    "services.database_auth_service.DatabaseAuthService.validate_otlp_token",
                    return_value="org1",
                ):
                    resp = client.post("/api/internal/otlp/validate", json={"token": "tok"}, headers=headers)
                    self.assertEqual(resp.status_code, 200)
                    self.assertEqual(resp.json(), {"org_id": "org1"})

                with patch(
                    "services.database_auth_service.DatabaseAuthService.validate_otlp_token",
                    return_value=None,
                ):
                    resp = client.post("/api/internal/otlp/validate", json={"token": "tok"}, headers=headers)
                    self.assertEqual(resp.status_code, 404)

                from sqlalchemy.exc import SQLAlchemyError

                with patch(
                    "services.database_auth_service.DatabaseAuthService.validate_otlp_token",
                    side_effect=SQLAlchemyError("boom"),
                ):
                    resp = client.post("/api/internal/otlp/validate", json={"token": "tok"}, headers=headers)
                    self.assertEqual(resp.status_code, 503)
            finally:
                config.GATEWAY_INTERNAL_SERVICE_TOKEN = original_internal_token


if __name__ == "__main__":
    unittest.main()
