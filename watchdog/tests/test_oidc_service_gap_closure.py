"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from tests._env import ensure_test_env

ensure_test_env()

from services.auth import oidc_service as mod


class _Resp:
    def __init__(self, payload, status_code=200, headers=None, text=""):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise mod.httpx.HTTPStatusError(
                "bad",
                request=mod.httpx.Request("GET", "https://idp.example"),
                response=mod.httpx.Response(self.status_code),
            )

    def json(self):
        return self._payload


def test_jwk_to_verification_key_branches(monkeypatch):
    pub_rsa = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    pub_ec = ec.generate_private_key(ec.SECP256R1()).public_key()

    monkeypatch.setattr(mod.RSAAlgorithm, "from_jwk", lambda _jwk: pub_rsa)
    monkeypatch.setattr(mod.ECAlgorithm, "from_jwk", lambda _jwk: pub_ec)
    assert isinstance(mod._jwk_to_verification_key({"kty": "RSA"}, "RS256"), rsa.RSAPublicKey)
    assert isinstance(mod._jwk_to_verification_key({"kty": "EC"}, "ES256"), ec.EllipticCurvePublicKey)

    monkeypatch.setattr(mod.RSAAlgorithm, "from_jwk", lambda _jwk: object())
    with pytest.raises(ValueError, match="Invalid RSA"):
        mod._jwk_to_verification_key({"kty": "RSA"}, "RS256")

    monkeypatch.setattr(mod.ECAlgorithm, "from_jwk", lambda _jwk: object())
    with pytest.raises(ValueError, match="Invalid EC"):
        mod._jwk_to_verification_key({"kty": "EC"}, "ES256")

    with pytest.raises(ValueError, match="Unsupported OIDC token algorithm"):
        mod._jwk_to_verification_key({"kty": "OKP"}, "HS256")


def test_verify_jwt_rejection_and_nonce_paths(monkeypatch):
    service = mod.OIDCService()
    token = "a.b.c"

    monkeypatch.setattr(mod.jwt, "get_unverified_header", lambda _token: {})
    assert service._verify_jwt(token) is None

    monkeypatch.setattr(mod.jwt, "get_unverified_header", lambda _token: {"alg": "HS256"})
    assert service._verify_jwt(token) is None

    monkeypatch.setattr(mod.jwt, "get_unverified_header", lambda _token: {"alg": "RS256"})
    monkeypatch.setattr(mod.config, "OIDC_TOKEN_ALGORITHM", "ES256", raising=False)
    assert service._verify_jwt(token) is None

    monkeypatch.setattr(mod.config, "OIDC_TOKEN_ALGORITHM", "RS256", raising=False)
    monkeypatch.setattr(service, "_select_jwk", lambda **kwargs: None)
    assert service._verify_jwt(token) is None

    monkeypatch.setattr(service, "_select_jwk", lambda **kwargs: {"kty": "RSA"})
    monkeypatch.setattr(service, "_verification_key_for", lambda *args, **kwargs: object())
    monkeypatch.setattr(service, "_get_well_known", lambda: {"issuer": "https://issuer"})
    monkeypatch.setattr(mod.config, "OIDC_AUDIENCE", None, raising=False)
    monkeypatch.setattr(mod.config, "OIDC_CLIENT_ID", "client", raising=False)

    monkeypatch.setattr(mod.jwt, "decode", lambda *_args, **_kwargs: {"exp": 1, "iat": 1, "nonce": "n1"})
    assert service._verify_jwt(token, nonce=None, require_nonce=True) is None
    assert service._verify_jwt(token, nonce="other", require_nonce=False) is None

    monkeypatch.setattr(mod.jwt, "decode", lambda *_args, **_kwargs: {"exp": 1, "iat": 1})
    assert service._verify_jwt(token, nonce="n1", require_nonce=False) is None

    monkeypatch.setattr(mod.jwt, "decode", lambda *_args, **_kwargs: {"exp": 1, "iat": 1, "nonce": "n1", "sub": "u1"})
    claims = service._verify_jwt(token, nonce="n1", require_nonce=False)
    assert claims and claims.get("sub") == "u1"

    monkeypatch.setattr(mod.jwt, "decode", lambda *_args, **_kwargs: (_ for _ in ()).throw(jwt.PyJWTError("bad")))
    assert service._verify_jwt(token) is None

    monkeypatch.setattr(mod.jwt, "decode", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("bad")))
    assert service._verify_jwt(token) is None


def test_admin_token_and_keycloak_user_error_paths(monkeypatch):
    service = mod.OIDCService()
    monkeypatch.setattr(mod.config, "KEYCLOAK_ADMIN_URL", "https://kc", raising=False)
    monkeypatch.setattr(mod.config, "KEYCLOAK_ADMIN_REALM", "master", raising=False)
    monkeypatch.setattr(mod.config, "KEYCLOAK_ADMIN_CLIENT_ID", "cid", raising=False)
    monkeypatch.setattr(mod.config, "KEYCLOAK_ADMIN_CLIENT_SECRET", "secret", raising=False)

    class _HttpBadBody:
        def post(self, _url, **_kwargs):
            return _Resp(["not-a-dict"])

        def close(self):
            return None

    monkeypatch.setattr(service, "_http", _HttpBadBody())
    assert service._get_admin_token() is None

    class _HttpNoToken:
        def post(self, _url, **_kwargs):
            return _Resp({"expires_in": 10})

        def close(self):
            return None

    service2 = mod.OIDCService()
    monkeypatch.setattr(service2, "_http", _HttpNoToken())
    assert service2._get_admin_token() is None

    monkeypatch.setattr(mod.config, "KEYCLOAK_USER_PROVISIONING_ENABLED", False, raising=False)
    assert service2.create_keycloak_user(email="x@y.z", username="x", full_name=None) is None

    monkeypatch.setattr(mod.config, "KEYCLOAK_USER_PROVISIONING_ENABLED", True, raising=False)
    monkeypatch.setattr(service2, "_get_admin_token", lambda: None)
    assert service2.create_keycloak_user(email="x@y.z", username="x", full_name=None) is None

    service3 = mod.OIDCService()
    monkeypatch.setattr(service3, "_get_admin_token", lambda: "token")

    class _HttpCreateBranches:
        def __init__(self):
            self.mode = "created-no-location"

        def post(self, url, **_kwargs):
            if self.mode == "created-no-location":
                return _Resp({}, status_code=201, headers={})
            if self.mode == "conflict-no-user":
                return _Resp({}, status_code=409)
            return _Resp({}, status_code=500)

        def get(self, _url, **_kwargs):
            return _Resp([])

        def close(self):
            return None

    http = _HttpCreateBranches()
    monkeypatch.setattr(service3, "_http", http)
    assert service3.create_keycloak_user(email="x@y.z", username="x", full_name="X Y") is None
    http.mode = "conflict-no-user"
    assert service3.create_keycloak_user(email="x@y.z", username="x", full_name=None) is None

    http.mode = "raise"
    with pytest.raises(mod.httpx.HTTPStatusError):
        service3.create_keycloak_user(email="x@y.z", username="x", full_name=None)
