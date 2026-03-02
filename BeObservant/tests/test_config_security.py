"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import importlib
import os
import sys
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

try:
    import services
    if not hasattr(services, "__path__"):
        services.__path__ = [os.path.join(os.path.dirname(__file__), "..", "services")]
except ImportError:
    pass


CONFIG_MODULE = "config"


def _reload_config_module():
    if CONFIG_MODULE in sys.modules:
        del sys.modules[CONFIG_MODULE]
    return importlib.import_module(CONFIG_MODULE)


def _rsa_keypair_pem() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


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

    def test_vault_enabled_in_production_without_addr_raises(self):
        with patch.dict(os.environ, {
            "CORS_ORIGINS": "http://localhost:5173",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "RS256",
            "APP_ENV": "production",
            "VAULT_ENABLED": "true",
            "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
            "DEFAULT_ADMIN_PASSWORD": "strongProdPassword_123!",
        }, clear=False):
            with self.assertRaises(ValueError):
                _reload_config_module()

    def test_loads_secrets_from_vault_when_enabled(self):
        class FakeVaultProvider:
            def __init__(self, *a, **k):
                pass

            def get(self, key):
                mapping = {
                    "DATABASE_URL": "postgresql://vaultuser:vaultpass@db:5432/beobservant",
                    "JWT_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----FAKE",
                    "JWT_PUBLIC_KEY": "-----BEGIN PUBLIC KEY-----FAKE",
                    "DEFAULT_ADMIN_PASSWORD": "vault-default-admin-pass",
                    "DATA_ENCRYPTION_KEY": "9j95_Fl__by42XjEQ03cNIw1MNfK8gxjhEC5Q8ru4ZE=",
                }
                return mapping.get(key)

        with patch.dict(os.environ, {
            "CORS_ORIGINS": "http://localhost:5173",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "RS256",
            "VAULT_ENABLED": "true",
            "VAULT_ADDR": "http://vault:8200",
            "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
        }, clear=False):
            import types, sys
            fake = types.SimpleNamespace(VaultSecretProvider=FakeVaultProvider, VaultClientError=Exception)
            sys.modules['services.secrets.vault_client'] = fake
            module = None
            try:
                module = _reload_config_module()
            finally:
                sys.modules.pop('services.secrets.vault_client', None)
            self.assertIsNotNone(module)
            self.assertEqual(module.config.DATABASE_URL, "postgresql://vaultuser:vaultpass@db:5432/beobservant")
            self.assertEqual(module.config.DEFAULT_ADMIN_PASSWORD, "vault-default-admin-pass")
            self.assertTrue(module.config.JWT_PRIVATE_KEY.startswith("-----BEGIN PRIVATE KEY"))
            self.assertTrue(module.config.JWT_PUBLIC_KEY.startswith("-----BEGIN PUBLIC KEY"))
            self.assertEqual(module.config.DATA_ENCRYPTION_KEY, "9j95_Fl__by42XjEQ03cNIw1MNfK8gxjhEC5Q8ru4ZE=")

    def test_production_requires_benotified_service_token(self):
        private_key, public_key = _rsa_keypair_pem()
        with patch.dict(os.environ, {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
            "CORS_ORIGINS": "https://app.example.com",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "RS256",
            "JWT_PRIVATE_KEY": private_key,
            "JWT_PUBLIC_KEY": public_key,
            "JWT_AUTO_GENERATE_KEYS": "false",
            "DEFAULT_ADMIN_PASSWORD": "strongProdPassword_123!",
            "DEFAULT_ADMIN_BOOTSTRAP_ENABLED": "false",
            "DATA_ENCRYPTION_KEY": "9j95_Fl__by42XjEQ03cNIw1MNfK8gxjhEC5Q8ru4ZE=",
            "BENOTIFIED_SERVICE_TOKEN": "",
            "BENOTIFIED_CONTEXT_SIGNING_KEY": "strong_context_signing_key_123",
            "BECERTAIN_SERVICE_TOKEN": "strong_becertain_service_token_123",
            "BECERTAIN_CONTEXT_SIGNING_KEY": "strong_becertain_context_signing_key_123",
            "GATEWAY_INTERNAL_SERVICE_TOKEN": "strong_gateway_token_123",
            "INBOUND_WEBHOOK_TOKEN": "strong_webhook_token_123",
        }, clear=False):
            with self.assertRaises(ValueError):
                _reload_config_module()

    def test_rejects_invalid_benotified_context_algorithm(self):
        private_key, public_key = _rsa_keypair_pem()
        with patch.dict(os.environ, {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
            "CORS_ORIGINS": "https://app.example.com",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "RS256",
            "JWT_PRIVATE_KEY": private_key,
            "JWT_PUBLIC_KEY": public_key,
            "JWT_AUTO_GENERATE_KEYS": "false",
            "DEFAULT_ADMIN_PASSWORD": "strongProdPassword_123!",
            "DEFAULT_ADMIN_BOOTSTRAP_ENABLED": "false",
            "DATA_ENCRYPTION_KEY": "9j95_Fl__by42XjEQ03cNIw1MNfK8gxjhEC5Q8ru4ZE=",
            "BENOTIFIED_SERVICE_TOKEN": "strong_benotified_service_token_123",
            "BENOTIFIED_CONTEXT_SIGNING_KEY": "strong_context_signing_key_123",
            "BENOTIFIED_CONTEXT_ALGORITHM": "RS256",
            "BECERTAIN_SERVICE_TOKEN": "strong_becertain_service_token_123",
            "BECERTAIN_CONTEXT_SIGNING_KEY": "strong_becertain_context_signing_key_123",
            "GATEWAY_INTERNAL_SERVICE_TOKEN": "strong_gateway_token_123",
            "INBOUND_WEBHOOK_TOKEN": "strong_webhook_token_123",
        }, clear=False):
            with self.assertRaises(ValueError):
                _reload_config_module()

    def test_rejects_production_allowlist_fail_open(self):
        private_key, public_key = _rsa_keypair_pem()
        with patch.dict(os.environ, {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
            "CORS_ORIGINS": "https://app.example.com",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "RS256",
            "JWT_PRIVATE_KEY": private_key,
            "JWT_PUBLIC_KEY": public_key,
            "JWT_AUTO_GENERATE_KEYS": "false",
            "DEFAULT_ADMIN_PASSWORD": "strongProdPassword_123!",
            "DEFAULT_ADMIN_BOOTSTRAP_ENABLED": "false",
            "DATA_ENCRYPTION_KEY": "9j95_Fl__by42XjEQ03cNIw1MNfK8gxjhEC5Q8ru4ZE=",
            "BENOTIFIED_SERVICE_TOKEN": "strong_benotified_service_token_123",
            "BENOTIFIED_CONTEXT_SIGNING_KEY": "strong_context_signing_key_123",
            "BECERTAIN_SERVICE_TOKEN": "strong_becertain_service_token_123",
            "BECERTAIN_CONTEXT_SIGNING_KEY": "strong_becertain_context_signing_key_123",
            "GATEWAY_INTERNAL_SERVICE_TOKEN": "strong_gateway_token_123",
            "INBOUND_WEBHOOK_TOKEN": "strong_webhook_token_123",
            "ALLOWLIST_FAIL_OPEN": "true",
        }, clear=False):
            with self.assertRaises(ValueError):
                _reload_config_module()

    def test_rejects_invalid_data_encryption_key_in_production(self):
        private_key, public_key = _rsa_keypair_pem()
        with patch.dict(os.environ, {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
            "CORS_ORIGINS": "https://app.example.com",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "RS256",
            "JWT_PRIVATE_KEY": private_key,
            "JWT_PUBLIC_KEY": public_key,
            "JWT_AUTO_GENERATE_KEYS": "false",
            "DEFAULT_ADMIN_PASSWORD": "strongProdPassword_123!",
            "DEFAULT_ADMIN_BOOTSTRAP_ENABLED": "false",
            "DATA_ENCRYPTION_KEY": "not-a-fernet-key",
            "BENOTIFIED_SERVICE_TOKEN": "strong_benotified_service_token_123",
            "BENOTIFIED_CONTEXT_SIGNING_KEY": "strong_context_signing_key_123",
            "BECERTAIN_SERVICE_TOKEN": "strong_becertain_service_token_123",
            "BECERTAIN_CONTEXT_SIGNING_KEY": "strong_becertain_context_signing_key_123",
            "GATEWAY_INTERNAL_SERVICE_TOKEN": "strong_gateway_token_123",
            "INBOUND_WEBHOOK_TOKEN": "strong_webhook_token_123",
        }, clear=False):
            with self.assertRaises(ValueError):
                _reload_config_module()


if __name__ == "__main__":
    unittest.main()
