"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import pytest

from tests._env import ensure_test_env

ensure_test_env()

from services.auth.oidc_service import OIDCService
from services.auth import oidc_service as mod


def test_oidc_select_jwk_cache_refresh_and_candidate_paths(monkeypatch):
    service = OIDCService()
    calls = {"count": 0}

    def get_jwks(force_refresh=False):
        calls["count"] += 1
        if calls["count"] == 1:
            service._jwks_by_kid = {}
            return {"keys": [{"kid": "a", "kty": "RSA", "alg": "RS256", "use": "sig"}]}
        service._jwks_by_kid = {"kid-1": {"kid": "kid-1", "kty": "RSA", "alg": "RS256", "use": "sig"}}
        return {"keys": [{"kid": "kid-1", "kty": "RSA", "alg": "RS256", "use": "sig"}]}

    monkeypatch.setattr(service, "_get_jwks", get_jwks)
    selected = service._select_jwk(kid="kid-1", alg="RS256")
    assert selected and selected.get("kid") == "kid-1"

    monkeypatch.setattr(service, "_get_jwks", lambda force_refresh=False: {"keys": [{"kid": "single", "kty": "RSA"}]})
    assert service._select_jwk(kid=None, alg=None)["kid"] == "single"

    monkeypatch.setattr(
        service,
        "_get_jwks",
        lambda force_refresh=False: {"keys": [{"kid": "x", "kty": "RSA", "alg": "RS256", "use": "sig"}]},
    )
    assert service._select_jwk(kid=None, alg="RS256")["kid"] == "x"


def test_oidc_verification_key_cache_and_close_runtime_path(monkeypatch):
    service = OIDCService()
    monkeypatch.setattr(mod, "_jwk_to_verification_key", lambda *_args, **_kwargs: "vk")
    assert service._verification_key_for({"kid": "k1"}, "RS256", "k1") == "vk"
    # second call must use cache
    assert service._verification_key_for({"kid": "k1"}, "RS256", "k1") == "vk"

    class _Http:
        def close(self):
            raise RuntimeError("closed")

    service._http = _Http()
    service.close()


def test_oidc_is_enabled_and_admin_token_missing_config(monkeypatch):
    service = OIDCService()
    monkeypatch.setattr(mod.config, "AUTH_PROVIDER", "oidc", raising=False)
    monkeypatch.setattr(mod.config, "OIDC_ISSUER_URL", "https://issuer", raising=False)
    monkeypatch.setattr(mod.config, "OIDC_CLIENT_ID", "client", raising=False)
    assert service.is_enabled() is True

    monkeypatch.setattr(mod.config, "OIDC_CLIENT_ID", "", raising=False)
    assert service.is_enabled() is False

    monkeypatch.setattr(mod.config, "KEYCLOAK_ADMIN_URL", "", raising=False)
    assert service._get_admin_token() is None


@pytest.mark.asyncio
async def test_oidc_consume_transaction_expired_redirect_state_and_unknown_pkce(monkeypatch):
    service = OIDCService()

    class _Cache:
        async def get(self, key):
            if key.startswith("oidc_tx_state:"):
                return {"tx_id": "tx1"}
            return {
                "state": "s1",
                "nonce": "n1",
                "redirect_uri": "https://cb",
                "expires_at": 1,
                "used": False,
                "code_challenge": "",
                "code_challenge_method": "",
            }

        async def set(self, *_args, **_kwargs):
            return None

    service._ttl_cache = _Cache()
    monkeypatch.setattr(mod.time, "time", lambda: 100)
    with pytest.raises(ValueError, match="invalid or expired"):
        await service.consume_authorization_transaction_async(transaction_id=None, state="s1", redirect_uri="https://cb")

    class _Cache2(_Cache):
        async def get(self, key):
            if key.startswith("oidc_tx_state:"):
                return {"tx_id": "tx2"}
            return {
                "state": "s1",
                "nonce": "n1",
                "redirect_uri": "https://other",
                "expires_at": 1000,
                "used": False,
                "code_challenge": "",
                "code_challenge_method": "",
            }

    service._ttl_cache = _Cache2()
    monkeypatch.setattr(mod.time, "time", lambda: 10)
    with pytest.raises(ValueError, match="invalid or expired"):
        await service.consume_authorization_transaction_async(transaction_id=None, state="s1", redirect_uri="https://cb")

    class _Cache3(_Cache):
        async def get(self, key):
            if key.startswith("oidc_tx_state:"):
                return {"tx_id": "tx3"}
            return {
                "state": "s1",
                "nonce": "n1",
                "redirect_uri": "https://cb",
                "expires_at": 1000,
                "used": False,
                "code_challenge": "abc",
                "code_challenge_method": "UNKNOWN",
            }

    service._ttl_cache = _Cache3()
    with pytest.raises(ValueError, match="Unsupported PKCE method"):
        await service.consume_authorization_transaction_async(
            transaction_id=None,
            state="s1",
            redirect_uri="https://cb",
            code_verifier="abc",
        )
