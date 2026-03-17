"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import importlib
import os
import sys
from unittest.mock import patch

import pytest

CONFIG_MODULE = "config"

def _reload_config():
    if CONFIG_MODULE in sys.modules:
        del sys.modules[CONFIG_MODULE]
    return importlib.import_module(CONFIG_MODULE)


@pytest.fixture(autouse=True)
def _restore_after_test():
    yield
    _reload_config()


def _base_prod_env() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "GATEWAY_AUTH_API_URL": "https://watchdog:4319/api/internal/otlp/validate",
        "GATEWAY_SSL_VERIFY": "true",
        "GATEWAY_ALLOWLIST_FAIL_OPEN": "false",
        "GATEWAY_INTERNAL_SERVICE_TOKEN": "strong_internal_token_123",
        "GATEWAY_STATUS_OTLP_TOKEN": "startup_probe_token_123",
    }


def test_production_rejects_non_https_auth_api():
    env = _base_prod_env()
    env["GATEWAY_AUTH_API_URL"] = "http://watchdog:4319/api/internal/otlp/validate"
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(ValueError):
            _reload_config()


def test_production_rejects_ssl_verify_disabled():
    env = _base_prod_env()
    env["GATEWAY_SSL_VERIFY"] = "false"
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(ValueError):
            _reload_config()


def test_production_rejects_missing_internal_token():
    env = _base_prod_env()
    env["GATEWAY_INTERNAL_SERVICE_TOKEN"] = ""
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(ValueError):
            _reload_config()


def test_production_rejects_allowlist_fail_open():
    env = _base_prod_env()
    env["GATEWAY_ALLOWLIST_FAIL_OPEN"] = "true"
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(ValueError):
            _reload_config()


def test_production_rejects_weak_internal_token():
    env = _base_prod_env()
    env["GATEWAY_INTERNAL_SERVICE_TOKEN"] = "replace_with_token"
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(ValueError):
            _reload_config()


def test_production_rejects_missing_status_token_in_strict_mode():
    env = _base_prod_env()
    env["GATEWAY_STATUS_OTLP_TOKEN"] = ""
    env["GATEWAY_STARTUP_CHECK_MODE"] = "strict"
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(ValueError):
            _reload_config()


def test_production_allows_missing_status_token_in_warn_mode():
    env = _base_prod_env()
    env["GATEWAY_STATUS_OTLP_TOKEN"] = ""
    env["GATEWAY_STARTUP_CHECK_MODE"] = "warn"
    with patch.dict(os.environ, env, clear=False):
        module = _reload_config()
    assert module.GATEWAY_STARTUP_CHECK_MODE == "warn"
