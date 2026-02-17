import importlib
import os
import sys
import unittest
from unittest.mock import patch


CONFIG_MODULE = "config"


def _reload_config_module():
    if CONFIG_MODULE in sys.modules:
        del sys.modules[CONFIG_MODULE]
    return importlib.import_module(CONFIG_MODULE)


class ConfigSecurityTests(unittest.TestCase):
    def test_rejects_example_database_url(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://beobservant:changeme123@localhost:5432/beobservant",
            "CORS_ORIGINS": "http://localhost:5173",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "RS256",
        }, clear=False):
            with self.assertRaises(ValueError):
                _reload_config_module()

    def test_rejects_wildcard_cors_with_credentials(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
            "CORS_ORIGINS": "*",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "RS256",
        }, clear=False):
            with self.assertRaises(ValueError):
                _reload_config_module()

    def test_generates_runtime_admin_password_when_missing(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
            "CORS_ORIGINS": "http://localhost:5173",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "RS256",
            "DEFAULT_ADMIN_PASSWORD": "",
            "JWT_PRIVATE_KEY": "",
            "JWT_PUBLIC_KEY": "",
        }, clear=False):
            module = _reload_config_module()
            self.assertTrue(module.config.DEFAULT_ADMIN_PASSWORD)
            self.assertNotEqual(module.config.DEFAULT_ADMIN_PASSWORD, "admin123")
            self.assertTrue(module.config.JWT_PRIVATE_KEY)
            self.assertTrue(module.config.JWT_PUBLIC_KEY)
            self.assertIn("BEGIN", module.config.JWT_PRIVATE_KEY)
            self.assertIn("BEGIN", module.config.JWT_PUBLIC_KEY)

    def test_rejects_non_asymmetric_jwt_algorithm(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
            "CORS_ORIGINS": "http://localhost:5173",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "HS256",
        }, clear=False):
            with self.assertRaises(ValueError):
                _reload_config_module()

    def test_generates_es256_keypair_when_enabled(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
            "CORS_ORIGINS": "http://localhost:5173",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "ES256",
            "JWT_PRIVATE_KEY": "",
            "JWT_PUBLIC_KEY": "",
            "JWT_AUTO_GENERATE_KEYS": "true",
            "APP_ENV": "development",
        }, clear=False):
            module = _reload_config_module()
            self.assertTrue(module.config.JWT_PRIVATE_KEY)
            self.assertTrue(module.config.JWT_PUBLIC_KEY)
            self.assertIn("BEGIN PRIVATE KEY", module.config.JWT_PRIVATE_KEY)
            self.assertIn("BEGIN PUBLIC KEY", module.config.JWT_PUBLIC_KEY)

    def test_rejects_bootstrap_and_auto_keys_in_production(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
            "CORS_ORIGINS": "https://app.example.com",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "RS256",
            "APP_ENV": "production",
            "DEFAULT_ADMIN_BOOTSTRAP_ENABLED": "true",
            "JWT_AUTO_GENERATE_KEYS": "true",
            "DEFAULT_ADMIN_PASSWORD": "strongProdPassword_123!",
        }, clear=False):
            with self.assertRaises(ValueError):
                _reload_config_module()


if __name__ == "__main__":
    unittest.main()
