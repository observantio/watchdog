"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from types import SimpleNamespace

import httpx
import pytest

from tests._env import ensure_test_env

ensure_test_env()

from services.auth.oidc_service import OIDCService, _json_dict, _looks_like_jwt


class ResponseStub:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)

    def json(self):
        return self._payload


def test_oidc_small_helpers_and_authorization_validation(monkeypatch):
    service = OIDCService()
    assert _json_dict({"a": 1}) == {"a": 1}
    assert _json_dict([]) == {}
    assert _looks_like_jwt("a.b.c") is True
    assert _looks_like_jwt("a.b") is False
    assert service._pkce_s256("abc")
    assert service._random_token(4)

    monkeypatch.setattr(service, "_get_well_known", lambda: {"authorization_endpoint": "https://issuer/auth"})
    with pytest.raises(ValueError, match="Unsupported PKCE"):
        service.build_authorization_url("https://app/cb", "state", "nonce", code_challenge="x", code_challenge_method="bad")

    with pytest.raises(ValueError, match="code_challenge_method requires code_challenge"):
        asyncio.run(
            service.start_authorization_transaction_async(
                redirect_uri="https://app/cb",
                code_challenge_method="S256",
            )
        )


def test_oidc_well_known_jwks_and_exchange_paths(monkeypatch):
    service = OIDCService()
    get_calls = []
    post_calls = []

    class HttpStub:
        def get(self, url, **kwargs):
            get_calls.append((url, kwargs))
            if url.endswith("openid-configuration"):
                return ResponseStub({"issuer": "https://issuer", "jwks_uri": "https://issuer/jwks", "userinfo_endpoint": "https://issuer/userinfo", "token_endpoint": "https://issuer/token", "authorization_endpoint": "https://issuer/auth"})
            if url.endswith("/jwks"):
                return ResponseStub({"keys": [{"kid": "kid-1", "kty": "RSA", "alg": "RS256", "use": "sig"}]})
            if url.endswith("/userinfo"):
                return ResponseStub({"sub": "1"})
            return ResponseStub([])

        def post(self, url, **kwargs):
            post_calls.append((url, kwargs))
            return ResponseStub({"access_token": "tok", "expires_in": 60, "id_token": "id"})

        def close(self):
            return None

    monkeypatch.setattr(service, "_http", HttpStub())
    monkeypatch.setattr("services.auth.oidc_service.config.OIDC_ISSUER_URL", "https://issuer")
    monkeypatch.setattr("services.auth.oidc_service.config.OIDC_CLIENT_ID", "client")
    monkeypatch.setattr("services.auth.oidc_service.config.OIDC_SCOPES", "openid profile")
    monkeypatch.setattr("services.auth.oidc_service.config.OIDC_CLIENT_SECRET", "secret")

    wk = service._get_well_known()
    assert wk["issuer"] == "https://issuer"
    assert service._get_well_known() is wk
    jwks = service._get_jwks()
    assert jwks["keys"][0]["kid"] == "kid-1"
    assert service._select_jwk(kid="kid-1", alg="RS256")["kid"] == "kid-1"
    assert service.fetch_userinfo("access") == {"sub": "1"}
    assert service.exchange_password("user", "pass")["access_token"] == "tok"
    assert service.exchange_authorization_code("code", "https://app/cb", code_verifier="verifier")["id_token"] == "id"
    assert service.build_authorization_url("https://app/cb", "state", "nonce").startswith("https://issuer/auth?")
    assert len(get_calls) >= 3
    assert len(post_calls) == 2


def test_oidc_exchange_and_fetch_error_paths(monkeypatch):
    service = OIDCService()
    monkeypatch.setattr(service, "_get_well_known", lambda: {"token_endpoint": "", "authorization_endpoint": None})
    with pytest.raises(ValueError, match="token endpoint"):
        service.exchange_password("user", "pass")
    with pytest.raises(ValueError, match="token endpoint"):
        service.exchange_authorization_code("code", "https://cb")
    with pytest.raises(ValueError, match="authorization endpoint"):
        service.build_authorization_url("https://cb", "state", "nonce")

    monkeypatch.setattr(service, "_get_well_known", lambda: {"userinfo_endpoint": None})
    assert service.fetch_userinfo("access") is None

    monkeypatch.setattr(service, "_get_well_known", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert service.fetch_userinfo("access") is None


def test_oidc_transaction_error_paths(monkeypatch):
    service = OIDCService()
    monkeypatch.setattr(service, "_get_well_known", lambda: {"authorization_endpoint": "https://issuer/auth"})
    monkeypatch.setattr("services.auth.oidc_service.config.OIDC_CLIENT_ID", "client")
    monkeypatch.setattr("services.auth.oidc_service.config.OIDC_SCOPES", "openid")

    created = asyncio.run(
        service.start_authorization_transaction_async(
            redirect_uri="https://app/cb",
            state="state1",
            nonce="nonce1",
            code_challenge="verifier",
            code_challenge_method="plain",
        )
    )
    record = asyncio.run(
        service.consume_authorization_transaction_async(
            transaction_id=created["transaction_id"],
            state="state1",
            redirect_uri="https://app/cb",
            code_verifier="verifier",
        )
    )
    assert record["nonce"] == "nonce1"

    with pytest.raises(ValueError, match="transaction not found"):
        asyncio.run(service.consume_authorization_transaction_async(transaction_id=None, state="missing", redirect_uri="https://app/cb"))

    created2 = asyncio.run(
        service.start_authorization_transaction_async(
            redirect_uri="https://app/cb",
            state="state2",
            nonce="nonce2",
            code_challenge="challenge",
            code_challenge_method="plain",
        )
    )
    with pytest.raises(ValueError, match="Missing PKCE"):
        asyncio.run(service.consume_authorization_transaction_async(transaction_id=created2["transaction_id"], state="state2", redirect_uri="https://app/cb"))
    with pytest.raises(ValueError, match="Invalid PKCE"):
        asyncio.run(service.consume_authorization_transaction_async(transaction_id=created2["transaction_id"], state="state2", redirect_uri="https://app/cb", code_verifier="wrong"))


def test_oidc_sync_runtime_helpers(monkeypatch):
    service = OIDCService()
    assert service._in_event_loop() is False

    monkeypatch.setattr(service, "_in_event_loop", lambda: True)
    coro = asyncio.sleep(0)
    with pytest.raises(RuntimeError, match="cannot run inside an event loop"):
        service._run_async(coro)
    coro.close()

    monkeypatch.setattr(service, "_in_event_loop", lambda: False)
    monkeypatch.setattr(service, "_ensure_bg_loop", lambda: SimpleNamespace())
    future = Future()
    future.set_result({"ok": True})
    monkeypatch.setattr("services.auth.oidc_service.asyncio.run_coroutine_threadsafe", lambda coro, loop: (coro.close(), future)[1])
    assert service._run_async(asyncio.sleep(0, result={"ok": True})) == {"ok": True}


def test_oidc_admin_token_and_keycloak_user_paths(monkeypatch):
    service = OIDCService()
    monkeypatch.setattr("services.auth.oidc_service.config.KEYCLOAK_ADMIN_URL", "https://kc")
    monkeypatch.setattr("services.auth.oidc_service.config.KEYCLOAK_ADMIN_REALM", "master")
    monkeypatch.setattr("services.auth.oidc_service.config.KEYCLOAK_ADMIN_CLIENT_ID", "cid")
    monkeypatch.setattr("services.auth.oidc_service.config.KEYCLOAK_ADMIN_CLIENT_SECRET", "secret")
    monkeypatch.setattr("services.auth.oidc_service.config.KEYCLOAK_USER_PROVISIONING_ENABLED", True)

    calls = []

    class HttpStub:
        def post(self, url, **kwargs):
            calls.append(("post", url, kwargs))
            if url.endswith("/token"):
                return ResponseStub({"access_token": "admin-token", "expires_in": 60})
            return ResponseStub({}, status_code=201, headers={"Location": "https://kc/admin/realms/master/users/user-1"})

        def get(self, url, **kwargs):
            calls.append(("get", url, kwargs))
            return ResponseStub([{"id": "existing-id"}])

        def close(self):
            return None

    monkeypatch.setattr(service, "_http", HttpStub())
    token = service._get_admin_token()
    assert token == "admin-token"
    assert service._get_admin_token() == "admin-token"
    assert service.create_keycloak_user(email="user@example.com", username="user", full_name="User Name") == "user-1"

    class ConflictHttpStub(HttpStub):
        def post(self, url, **kwargs):
            if url.endswith("/token"):
                return ResponseStub({"access_token": "admin-token", "expires_in": 60})
            return ResponseStub({}, status_code=409)

    service2 = OIDCService()
    monkeypatch.setattr(service2, "_http", ConflictHttpStub())
    monkeypatch.setattr(service2, "_admin_token_cache", "admin-token")
    monkeypatch.setattr(service2, "_admin_token_expires_at", 9999999999)
    assert service2.create_keycloak_user(email="user@example.com", username="user", full_name=None) == "existing-id"
