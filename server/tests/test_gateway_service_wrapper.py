"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


import unittest
import types
import sys
from unittest.mock import MagicMock

from tests._env import ensure_test_env

ensure_test_env()

stub_database_auth = types.ModuleType("services.database_auth_service")


class _StubDatabaseAuthService:
    def validate_otlp_token(self, token):
        return token


stub_database_auth.DatabaseAuthService = _StubDatabaseAuthService
sys.modules.setdefault("services.database_auth_service", stub_database_auth)

from services.gateway_service import GatewayService


class GatewayServiceWrapperTests(unittest.TestCase):
    def test_extract_otlp_token_strips_whitespace(self):
        service = GatewayService(auth_service=MagicMock())
        self.assertEqual(service.extract_otlp_token('  abc  '), 'abc')
        self.assertEqual(service.extract_otlp_token(None), '')

    def test_validate_otlp_token_delegates_to_auth_service(self):
        auth_service = MagicMock()
        auth_service.validate_otlp_token.return_value = 'org-1'
        service = GatewayService(auth_service=auth_service)

        self.assertEqual(service.validate_otlp_token('tok'), 'org-1')
        auth_service.validate_otlp_token.assert_called_once_with('tok')


if __name__ == '__main__':
    unittest.main()
