"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from tests._env import ensure_test_env

ensure_test_env()

from services.database_auth import auth as mod


def _base_service():
    return SimpleNamespace(
        _MFA_REQUIRED_RESPONSE="mfa_required",
        _needs_mfa_setup=lambda _user: False,
        _mfa_setup_challenge=lambda _user: {"setup": True},
        verify_totp_code=lambda _user, _code: True,
        logger=SimpleNamespace(error=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None),
        is_external_auth_enabled=lambda: True,
        is_password_auth_enabled=lambda: True,
        create_access_token=lambda user: {"not": "token"},
        _sync_user_from_oidc_claims=lambda claims: SimpleNamespace(is_active=True) if claims else None,
        oidc_service=SimpleNamespace(),
    )


def test_login_external_failure_paths(monkeypatch):
    service = _base_service()
    service.oidc_service.exchange_password = lambda _u, _p: (_ for _ in ()).throw(
        httpx.ConnectError("boom", request=httpx.Request("POST", "https://idp"))
    )
    assert mod.login(service, "user", "pw") is None

    service.oidc_service.exchange_password = lambda _u, _p: {}
    assert mod.login(service, "user", "pw") is None

    monkeypatch.setattr(mod, "sync_active_user_from_claims", lambda _service, _claims: None)
    service.oidc_service.exchange_password = lambda _u, _p: {"access_token": "at", "id_token": "id"}
    service.oidc_service.verify_id_token = lambda *_args, **_kwargs: {"sub": "1"}
    assert mod.login(service, "user", "pw") is None


def test_exchange_authorization_code_and_helpers_failure_paths():
    service = _base_service()
    service.oidc_service.consume_authorization_transaction = lambda **_kwargs: {"nonce": "n1"}
    service.oidc_service.exchange_authorization_code = lambda *_args, **_kwargs: {}
    assert mod.exchange_oidc_authorization_code(service, "code", "https://cb", transaction_id="tx") is None

    service.oidc_service.exchange_authorization_code = lambda *_args, **_kwargs: {
        "access_token": "at",
        "id_token": "",
    }
    # expected nonce is set from transaction and id_token is missing -> must reject
    assert mod.exchange_oidc_authorization_code(service, "code", "https://cb", transaction_id="tx") is None

    service.oidc_service.start_authorization_transaction = lambda **_kwargs: "not-a-dict"
    with pytest.raises(ValueError, match="did not return a mapping"):
        mod.get_oidc_authorization_url(service, "https://cb")

    service.oidc_service.start_authorization_transaction = lambda **_kwargs: {"state": "s"}
    with pytest.raises(ValueError, match="authorization_url"):
        mod.get_oidc_authorization_url(service, "https://cb")

    service.oidc_service.create_keycloak_user = lambda **_kwargs: (_ for _ in ()).throw(ValueError("bad"))
    assert mod.provision_external_user(service, email="u@example.com", username="u", full_name=None) is None
