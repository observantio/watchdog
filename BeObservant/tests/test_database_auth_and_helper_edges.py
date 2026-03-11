"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException, Request, Response

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Permission, Role, Token, TokenData
from services.auth import helper as auth_helper
from services.database_auth import auth as auth_mod
from services.database_auth import password as pwd_mod
from services.database_auth import permissions as perms_mod


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "scheme": "http", "query_string": b"", "client": ("127.0.0.1", 1234), "http_version": "1.1"})


def _user(**kwargs) -> TokenData:
    payload = {
        "user_id": "u1",
        "username": "user",
        "tenant_id": "tenant",
        "org_id": "org",
        "role": Role.USER,
        "permissions": [Permission.READ_AUDIT_LOGS.value],
        "group_ids": ["g1"],
        "is_superuser": False,
    }
    payload.update(kwargs)
    return TokenData(**payload)


class Query:
    def __init__(self, row):
        self.row = row
        self.filters = []
        self.opts = []

    def options(self, *args, **kwargs):
        self.opts.append((args, kwargs))
        return self

    def filter(self, *args, **kwargs):
        self.filters.append((args, kwargs))
        return self

    def filter_by(self, **kwargs):
        self.filters.append(((), kwargs))
        return self

    def first(self):
        return self.row

    def all(self):
        if self.row is None:
            return []
        if isinstance(self.row, list):
            return self.row
        return [self.row]

    def outerjoin(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self


class FakeDB:
    def __init__(self, *rows):
        self.rows = list(rows)
        self.flushed = 0

    def query(self, *args, **kwargs):
        row = self.rows.pop(0) if self.rows else None
        return Query(row)

    def flush(self):
        self.flushed += 1


class PermissionsDB:
    def __init__(self, user_row, permission_rows):
        self.user_row = user_row
        self.permission_rows = permission_rows

    def query(self, model, *args, **kwargs):
        if model is perms_mod.Permission:
            return Query(self.permission_rows)
        return Query(self.user_row)


@contextmanager
def _ctx(db):
    yield db


def test_database_auth_auth_helpers_and_login_flows(monkeypatch):
    assert auth_mod._OidcTokens.from_mapping({"access_token": "a", "id_token": "b"}).is_empty() is False
    assert auth_mod._OidcTokens.from_mapping({}).is_empty() is True

    service = SimpleNamespace(
        _MFA_REQUIRED_RESPONSE="mfa_required",
        _needs_mfa_setup=lambda user: False,
        _mfa_setup_challenge=lambda user: {"setup": True},
        verify_totp_code=lambda user, code: code == "123456",
        oidc_service=SimpleNamespace(
            verify_id_token=lambda token, nonce=None: {"sub": "1"} if token else None,
            fetch_userinfo=lambda token: {"sub": "1"} if token == "access" else {},
            verify_access_token=lambda token: {"sub": "1"} if token == "fallback" else None,
            exchange_password=lambda username, password: {"access_token": "access", "id_token": "id"},
            consume_authorization_transaction=lambda **kwargs: {"nonce": "nonce", "code_challenge": "abc"},
            exchange_authorization_code=lambda *args, **kwargs: {"access_token": "access", "id_token": "id"},
            start_authorization_transaction=lambda **kwargs: {"authorization_url": "https://idp", "state": "s"},
            create_keycloak_user=lambda **kwargs: "external-id",
        ),
        logger=SimpleNamespace(error=lambda *_args, **_kwargs: None, warning=lambda *_args, **_kwargs: None),
        is_external_auth_enabled=lambda: False,
        is_password_auth_enabled=lambda: True,
        authenticate_user=lambda username, password: SimpleNamespace(mfa_enabled=False, is_active=True),
        create_access_token=lambda user: Token(access_token="jwt", expires_in=60),
        _sync_user_from_oidc_claims=lambda claims: SimpleNamespace(is_active=True),
    )
    monkeypatch.setattr(auth_mod, "sync_active_user_from_claims", lambda service, claims: SimpleNamespace(is_active=True))

    user = SimpleNamespace(mfa_enabled=False)
    assert auth_mod._mfa_gate(service, user, None) is True
    service._needs_mfa_setup = lambda user: True
    assert auth_mod._mfa_gate(service, user, None) == {"setup": True}
    service._needs_mfa_setup = lambda user: False
    user = SimpleNamespace(mfa_enabled=True)
    assert auth_mod._mfa_gate(service, user, None) == {"mfa_required": True}
    assert auth_mod._mfa_gate(service, user, "bad") is None

    tokens = auth_mod._OidcTokens(access_token="", id_token="id")
    assert auth_mod._resolve_oidc_claims(service, tokens=tokens, expected_nonce="nonce", enforce_nonce=True) == {"sub": "1"}
    tokens = auth_mod._OidcTokens(access_token="access", id_token="")
    assert auth_mod._resolve_oidc_claims(service, tokens=tokens, expected_nonce="", enforce_nonce=False) == {"sub": "1"}
    tokens = auth_mod._OidcTokens(access_token="fallback", id_token="")
    assert auth_mod._resolve_oidc_claims(service, tokens=tokens, expected_nonce="nonce", enforce_nonce=True) is None

    assert isinstance(auth_mod.login(service, "user", "pw"), Token)
    service.authenticate_user = lambda username, password: None
    assert auth_mod.login(service, "user", "pw") is None

    service.is_external_auth_enabled = lambda: True
    service.is_password_auth_enabled = lambda: False
    assert auth_mod.login(service, "user", "pw") is None
    service.is_password_auth_enabled = lambda: True
    assert isinstance(auth_mod.login(service, "user", "pw"), Token)

    assert isinstance(auth_mod.exchange_oidc_authorization_code(service, "code", "https://cb", transaction_id="tx"), Token)
    service.is_external_auth_enabled = lambda: False
    assert auth_mod.exchange_oidc_authorization_code(service, "code", "https://cb") is None
    service.is_external_auth_enabled = lambda: True
    assert auth_mod.get_oidc_authorization_url(service, "https://cb")["authorization_url"] == "https://idp"
    assert auth_mod.provision_external_user(service, email="a@b.c", username="user", full_name="User") == "external-id"


def test_password_and_permissions_modules(monkeypatch):
    service = SimpleNamespace(_password_op_semaphore=None, _log_audit=lambda *args, **kwargs: None)
    monkeypatch.setattr(pwd_mod.config, "BCRYPT_ROUNDS", "bad", raising=False)
    assert pwd_mod._bcrypt_rounds() == 12
    monkeypatch.setattr(pwd_mod.config, "BCRYPT_ROUNDS", 20, raising=False)
    assert pwd_mod._bcrypt_rounds() == 15
    with pytest.raises(ValueError):
        pwd_mod.hash_password(service, "")
    hashed = pwd_mod.hash_password(service, "secret")
    assert pwd_mod.verify_password(service, "secret", hashed) is True
    assert pwd_mod.verify_password(service, "bad", hashed) is False
    assert len(pwd_mod._generate_temp_password(5)) >= 12
    assert len(pwd_mod._generate_temp_password(100)) <= 64
    assert pwd_mod._is_admin_role("Role.ADMIN") is True

    actor = SimpleNamespace(is_superuser=False, role="admin", permissions=[])
    assert pwd_mod._actor_can_reset_password(actor) is True
    actor = SimpleNamespace(is_superuser=False, role="user", permissions=[SimpleNamespace(name="manage:users")])
    assert pwd_mod._actor_can_reset_password(actor) is True

    db = FakeDB(None)
    monkeypatch.setattr(pwd_mod, "get_db_session", lambda: _ctx(db))
    with pytest.raises(HTTPException):
        pwd_mod._require_user_in_tenant(db, "u1", "tenant")

    target = SimpleNamespace(id="u2", tenant_id="tenant", role="user", is_superuser=False, username="target", email="t@example.com")
    actor = SimpleNamespace(id="u1", tenant_id="tenant", is_superuser=True, role="user", permissions=[])
    db = FakeDB(actor, target)
    monkeypatch.setattr(pwd_mod, "get_db_session", lambda: _ctx(db))
    monkeypatch.setattr(pwd_mod, "hash_password", lambda service, password: f"hashed:{password}")
    monkeypatch.setattr(pwd_mod.config, "TEMP_PASSWORD_LENGTH", 12, raising=False)
    result = pwd_mod.reset_user_password_temp(service, "u1", "u2", "tenant")
    assert result["target_username"] == "target"
    assert db.flushed == 1

    db = FakeDB(None)
    monkeypatch.setattr(pwd_mod, "get_db_session", lambda: _ctx(db))
    with pytest.raises(HTTPException):
        pwd_mod.reset_user_password_temp(service, "u1", "u2", "tenant")

    db_user = SimpleNamespace(role="admin", groups=[SimpleNamespace(is_active=True, permissions=[SimpleNamespace(name="gperm")])], permissions=[SimpleNamespace(name="uperm")])
    permission_rows = [SimpleNamespace(id="p1", name="read:users", display_name="Read", description="d", resource_type="users", action="read")]
    monkeypatch.setattr(perms_mod, "get_db_session", lambda: _ctx(PermissionsDB(db_user, permission_rows)))
    user = SimpleNamespace(id="u1", role="admin", groups=[], permissions=[])
    assert "gperm" in perms_mod.get_user_permissions(None, user)
    assert perms_mod.get_user_direct_permissions(user) == ["uperm"]
    collected = perms_mod.collect_permissions(db_user)
    assert "gperm" in collected and "uperm" in collected
    assert perms_mod.list_all_permissions()[0]["name"] == "read:users"
    assert perms_mod._safe_role("bad") == Role.USER


def test_auth_helper_edges(monkeypatch):
    monkeypatch.setattr(auth_helper, "require_permission_with_scope", lambda *args, **kwargs: (lambda: None))
    with pytest.raises(HTTPException):
        auth_helper.require_admin_with_audit_permission(_user())
    assert auth_helper.require_admin_with_audit_permission(_user(role=Role.ADMIN))

    monkeypatch.setattr(auth_helper, "cookie_secure", lambda request: True)
    monkeypatch.setattr(auth_helper.config, "FORCE_SECURE_COOKIES", False)
    monkeypatch.setattr(auth_helper.config, "JWT_EXPIRATION_MINUTES", 5)
    response = Response()
    auth_helper.set_auth_cookie(_request(), response, "jwt")
    assert "beobservant_token=jwt" in response.headers["set-cookie"]
    response = Response()
    auth_helper.clear_auth_cookie(_request(), response)
    assert "Max-Age=0" in response.headers["set-cookie"]

    assert auth_helper.audit_key_is_sensitive("password") is True
    assert auth_helper.audit_key_is_sensitive("status_code") is False
    assert auth_helper.redact_query_string("code=123&name=alice") == "code=%5BREDACTED%5D&name=alice"
    assert "code=%5BREDACTED%5D" in auth_helper.sanitize_resource_id("https://x?code=123")
    assert auth_helper.sanitize_audit_details({"token": "abc", "query": "code=123", "ok": True}) == {"token": "[REDACTED]", "query": "code=%5BREDACTED%5D", "ok": True}
    assert Permission.READ_ALERTS.value in auth_helper.role_permission_strings(Role.ADMIN)
    assert auth_helper.role_permission_strings("bad") == []
    assert auth_helper.perms_check(_user(permissions=["a", "b"])) == {"a", "b"}
    assert auth_helper.is_admin_check(_user(role=Role.ADMIN)) is True
    assert auth_helper.is_admin_check(_user(is_superuser=True)) is True
