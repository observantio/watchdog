"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import importlib
import os
import sys
import types

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import pytest

from tests._env import ensure_test_env

ensure_test_env()


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


def _valid_dev_env() -> dict[str, str]:
    return {
        "APP_ENV": "development",
        "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
        "CORS_ORIGINS": "http://localhost:5173",
        "CORS_ALLOW_CREDENTIALS": "true",
        "JWT_ALGORITHM": "RS256",
        "JWT_PRIVATE_KEY": "",
        "JWT_PUBLIC_KEY": "",
        "JWT_AUTO_GENERATE_KEYS": "true",
        "DEFAULT_ADMIN_PASSWORD": "",
        "VAULT_ENABLED": "false",
    }


def _valid_prod_env() -> dict[str, str]:
    private_key, public_key = _rsa_keypair_pem()
    return {
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
        "DATA_ENCRYPTION_KEY": Fernet.generate_key().decode("utf-8"),
        "BENOTIFIED_SERVICE_TOKEN": "strong_benotified_service_token_123",
        "BENOTIFIED_CONTEXT_SIGNING_KEY": "strong_context_signing_key_123",
        "BECERTAIN_SERVICE_TOKEN": "strong_becertain_service_token_123",
        "BECERTAIN_CONTEXT_SIGNING_KEY": "strong_becertain_context_signing_key_123",
        "GATEWAY_INTERNAL_SERVICE_TOKEN": "strong_gateway_token_123",
        "INBOUND_WEBHOOK_TOKEN": "strong_webhook_token_123",
    }


def test_config_helper_functions_cover_none_paths():
    module = _reload_config_module()
    assert module._to_list(None, default=["x"]) == ["x"]
    assert module._is_placeholder(None, ["x"]) is True


def test_config_vault_optional_warning_and_secret_loading_paths(monkeypatch):
    class FailingVaultProvider:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("vault down")

    with monkeypatch.context() as ctx:
        for key, value in _valid_dev_env().items():
            ctx.setenv(key, value)
        ctx.setenv("VAULT_ENABLED", "true")
        ctx.setenv("VAULT_ADDR", "http://vault:8200")
        ctx.setenv("VAULT_FAIL_ON_MISSING", "false")
        ctx.setitem(
            sys.modules,
            "services.secrets.vault_client",
            types.SimpleNamespace(VaultSecretProvider=FailingVaultProvider, VaultClientError=RuntimeError),
        )
        module = _reload_config_module()
        assert module.config.VAULT_ENABLED is True

    class FakeVaultProvider:
        def __init__(self, *args, **kwargs):
            self.values = {
                "DATABASE_URL": "postgresql://vaultuser:vaultpass@db:5432/beobservant",
                "GATEWAY_INTERNAL_SERVICE_TOKEN": "vault-token",
            }

        def get(self, key):
            if key == "JWT_PRIVATE_KEY":
                raise RuntimeError("bad")
            return self.values.get(key)

    with monkeypatch.context() as ctx:
        for key, value in _valid_dev_env().items():
            ctx.setenv(key, value)
        ctx.setenv("VAULT_ENABLED", "true")
        ctx.setenv("VAULT_ADDR", "http://vault:8200")
        ctx.setitem(
            sys.modules,
            "services.secrets.vault_client",
            types.SimpleNamespace(VaultSecretProvider=FakeVaultProvider, VaultClientError=RuntimeError),
        )
        module = _reload_config_module()
        assert module.config.DATABASE_URL == "postgresql://vaultuser:vaultpass@db:5432/beobservant"
        assert module.config.GATEWAY_INTERNAL_SERVICE_TOKEN == "vault-token"
        assert module.config.get_secret("MAX_QUERY_LIMIT") == str(module.config.MAX_QUERY_LIMIT)
        module.config.MISSING_VALUE = None
        module.config._secret_provider = types.SimpleNamespace(get=lambda key: (_ for _ in ()).throw(RuntimeError("boom")))
        assert module.config.get_secret("MISSING_VALUE") is None


def test_apply_security_defaults_unsupported_auto_key_algorithm():
    module = _reload_config_module()
    cfg = module.Config.__new__(module.Config)
    cfg.DEFAULT_ADMIN_PASSWORD = "strong"
    cfg.DEFAULT_ADMIN_BOOTSTRAP_ENABLED = False
    cfg.IS_PRODUCTION = False
    cfg.JWT_SECRET_KEY = ""
    cfg.JWT_ALGORITHM = "HS256"
    cfg.ALLOWED_JWT_ALGORITHMS = {"HS256"}
    cfg.JWT_PRIVATE_KEY = ""
    cfg.JWT_PUBLIC_KEY = ""
    cfg.JWT_AUTO_GENERATE_KEYS = True
    with pytest.raises(ValueError, match="Unsupported JWT_ALGORITHM for auto key generation"):
        module.Config._apply_security_defaults(cfg)


def test_config_accepts_strong_production_secrets_and_legacy_jwt_secret(monkeypatch):
    env = _valid_prod_env()
    env.update(
        {
            "JWT_SECRET_KEY": "legacy-shared-secret",
            "ALLOWLIST_FAIL_OPEN": "false",
        }
    )
    with monkeypatch.context() as ctx:
        for key, value in env.items():
            ctx.setenv(key, value)
        module = _reload_config_module()
        assert module.config.JWT_SECRET_KEY == "legacy-shared-secret"
        assert module.config.BENOTIFIED_CONTEXT_SIGNING_KEY == "strong_context_signing_key_123"


@pytest.mark.parametrize(
    ("env_updates", "expected_message"),
    [
        ({"APP_ENV": "production", "JWT_AUTO_GENERATE_KEYS": "true"}, "JWT_AUTO_GENERATE_KEYS must be disabled in production"),
        ({"APP_ENV": "production", "DEFAULT_ADMIN_PASSWORD": ""}, "DEFAULT_ADMIN_PASSWORD must be set to a strong value in production"),
        ({"APP_ENV": "production", "DEFAULT_ADMIN_BOOTSTRAP_ENABLED": "true"}, "DEFAULT_ADMIN_BOOTSTRAP_ENABLED must be false in production"),
        ({"REQUIRE_TOTP_ENCRYPTION_KEY": "true", "DATA_ENCRYPTION_KEY": ""}, "DATA_ENCRYPTION_KEY is required when REQUIRE_TOTP_ENCRYPTION_KEY is enabled"),
        ({"APP_ENV": "production", "DATA_ENCRYPTION_KEY": "", "REQUIRE_TOTP_ENCRYPTION_KEY": "false"}, "DATA_ENCRYPTION_KEY must be configured in production"),
        ({"BECERTAIN_CONTEXT_ALGORITHM": "RS256"}, "Unsupported BECERTAIN_CONTEXT_ALGORITHM"),
        ({"BENOTIFIED_CONTEXT_TTL_SECONDS": "0"}, "BENOTIFIED_CONTEXT_TTL_SECONDS must be greater than 0"),
        ({"BECERTAIN_CONTEXT_TTL_SECONDS": "0"}, "BECERTAIN_CONTEXT_TTL_SECONDS must be greater than 0"),
        ({"MAX_QUERY_LIMIT": "0"}, "MAX_QUERY_LIMIT must be greater than 0"),
        ({"DEFAULT_QUERY_LIMIT": "0"}, "DEFAULT_QUERY_LIMIT must be greater than 0"),
        ({"MAX_QUERY_LIMIT": "20", "DEFAULT_QUERY_LIMIT": "30"}, "DEFAULT_QUERY_LIMIT cannot exceed MAX_QUERY_LIMIT"),
        ({"LOKI_FALLBACK_CONCURRENCY": "0"}, "LOKI_FALLBACK_CONCURRENCY must be greater than 0"),
        ({"LOKI_MAX_FALLBACK_QUERIES": "-1"}, "LOKI_MAX_FALLBACK_QUERIES must be greater than or equal to 0"),
        ({"LOKI_VOLUME_CACHE_TTL_SECONDS": "-1"}, "LOKI_VOLUME_CACHE_TTL_SECONDS must be greater than or equal to 0"),
        ({"TEMPO_TRACE_FETCH_CONCURRENCY": "0"}, "TEMPO_TRACE_FETCH_CONCURRENCY must be greater than 0"),
        ({"TEMPO_VOLUME_BUCKET_CONCURRENCY": "0"}, "TEMPO_VOLUME_BUCKET_CONCURRENCY must be greater than 0"),
        ({"TEMPO_COUNT_QUERY_CONCURRENCY": "0"}, "TEMPO_COUNT_QUERY_CONCURRENCY must be greater than 0"),
        ({"BECERTAIN_PROXY_CACHE_TTL_SECONDS": "-1"}, "BECERTAIN_PROXY_CACHE_TTL_SECONDS must be greater than or equal to 0"),
        ({"BECERTAIN_ANALYZE_MAX_CONCURRENCY": "0"}, "BECERTAIN_ANALYZE_MAX_CONCURRENCY must be greater than 0"),
        ({"BECERTAIN_ANALYZE_MAX_RETAINED_PER_USER": "0"}, "BECERTAIN_ANALYZE_MAX_RETAINED_PER_USER must be greater than 0"),
        ({"BECERTAIN_ANALYZE_JOB_TTL_SECONDS": "0"}, "BECERTAIN_ANALYZE_JOB_TTL_SECONDS must be greater than 0"),
        ({"PASSWORD_RESET_INTERVAL_DAYS": "-1"}, "PASSWORD_RESET_INTERVAL_DAYS must be >= 0"),
        ({"TEMP_PASSWORD_LENGTH": "11"}, "TEMP_PASSWORD_LENGTH must be >= 12"),
    ],
)
def test_config_validation_edges(monkeypatch, env_updates, expected_message):
    env = _valid_prod_env() if env_updates.get("APP_ENV") == "production" else _valid_dev_env()
    env.update(env_updates)
    with monkeypatch.context() as ctx:
        for key, value in env.items():
            ctx.setenv(key, value)
        with pytest.raises(ValueError, match=expected_message):
            _reload_config_module()