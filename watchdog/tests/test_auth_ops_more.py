"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from sqlalchemy.exc import SQLAlchemyError

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Role
from models.access.user_models import UserPasswordUpdate
from services.auth import auth_ops as auth_mod


class _Query:
    def __init__(self, row):
        self.row = row

    def options(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def filter_by(self, **_kwargs):
        return self

    def join(self, *_args, **_kwargs):
        return self

    def first(self):
        if isinstance(self.row, list):
            return self.row[0] if self.row else None
        return self.row


class _DB:
    def __init__(self, *rows, exc=None):
        self.rows = list(rows)
        self.exc = exc
        self.flushed = 0
        self.committed = 0
        self.expunged = []

    def query(self, *_args, **_kwargs):
        if self.exc:
            raise self.exc
        row = self.rows.pop(0) if self.rows else None
        return _Query(row)

    def flush(self):
        self.flushed += 1

    def commit(self):
        self.committed += 1

    def expunge(self, obj):
        self.expunged.append(obj)


@contextmanager
def _ctx(db):
    yield db


def _pem_pair(key_type: str) -> tuple[str, str]:
    if key_type == "rsa":
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    else:
        private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def _service(**kwargs):
    payload = {
        "_collect_permissions": lambda user: ["read:users", "read:users"],
        "_lazy_init": lambda: None,
        "verify_password": lambda raw, hashed: raw == hashed,
        "hash_password": lambda password: f"hashed:{password}",
        "_hash_otlp_token": lambda token: f"hash:{token}",
        "logger": SimpleNamespace(debug=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None),
    }
    payload.update(kwargs)
    return SimpleNamespace(**payload)


def test_jwt_helpers_create_and_decode_token(monkeypatch):
    rsa_private, rsa_public = _pem_pair("rsa")
    ec_private, ec_public = _pem_pair("ec")
    auth_mod._jwt_key_objects.cache_clear()
    monkeypatch.setattr(auth_mod.config, "JWT_ALGORITHM", "HS256", raising=False)
    with pytest.raises(ValueError):
        auth_mod._jwt_key_objects()

    auth_mod._jwt_key_objects.cache_clear()
    monkeypatch.setattr(auth_mod.config, "JWT_ALGORITHM", "RS256", raising=False)
    monkeypatch.setattr(auth_mod.config, "JWT_PRIVATE_KEY", "", raising=False)
    monkeypatch.setattr(auth_mod.config, "JWT_PUBLIC_KEY", "", raising=False)
    with pytest.raises(ValueError):
        auth_mod._jwt_key_objects()

    auth_mod._jwt_key_objects.cache_clear()
    monkeypatch.setattr(auth_mod.config, "JWT_PRIVATE_KEY", ec_private, raising=False)
    monkeypatch.setattr(auth_mod.config, "JWT_PUBLIC_KEY", ec_public, raising=False)
    with pytest.raises(ValueError):
        auth_mod._jwt_key_objects()

    auth_mod._jwt_key_objects.cache_clear()
    monkeypatch.setattr(auth_mod.config, "JWT_PRIVATE_KEY", rsa_private, raising=False)
    monkeypatch.setattr(auth_mod.config, "JWT_PUBLIC_KEY", rsa_public, raising=False)
    monkeypatch.setattr(auth_mod.config, "JWT_EXPIRATION_MINUTES", 5, raising=False)
    monkeypatch.setattr(auth_mod.config, "DEFAULT_ORG_ID", "org-default", raising=False)
    db_user = SimpleNamespace(
        id="u1",
        username="alice",
        tenant_id="tenant",
        org_id="org-1",
        role=Role.ADMIN.value,
        is_superuser=True,
        groups=[SimpleNamespace(id="g1")],
        permissions=[],
    )
    db = _DB(db_user)
    monkeypatch.setattr(auth_mod, "get_db_session", lambda: _ctx(db))
    token = auth_mod.create_access_token(_service(), SimpleNamespace(id="u1"))
    decoded = auth_mod.decode_token(_service(), token.access_token)
    assert decoded and decoded.user_id == "u1"
    assert decoded.permissions == ["read:users"]
    assert decoded.group_ids == ["g1"]

    mfa_token = auth_mod.create_mfa_setup_token(SimpleNamespace(id="u1", username="alice", tenant_id="tenant"), minutes=999)
    decoded_mfa = auth_mod.decode_token(_service(), mfa_token.access_token)
    assert decoded_mfa and decoded_mfa.is_mfa_setup is True
    assert mfa_token.expires_in == auth_mod.MAX_MFA_SETUP_TOKEN_MINUTES * 60

    assert auth_mod.decode_token(_service(), "bad.token") is None
    payload = auth_mod.decode_token(_service(), auth_mod.jwt.encode({"sub": "u1"}, auth_mod._jwt_signing_key(), algorithm=auth_mod.config.JWT_ALGORITHM))
    assert payload is None
    bad_role = auth_mod.jwt.encode({"sub": "u1", "username": "alice", "role": "bad", "tenant_id": "tenant", "permissions": "x", "group_ids": "y"}, auth_mod._jwt_signing_key(), algorithm=auth_mod.config.JWT_ALGORITHM)
    decoded_bad_role = auth_mod.decode_token(_service(), bad_role)
    assert decoded_bad_role and decoded_bad_role.role == Role.USER
    assert auth_mod._normalize_username(" Alice ") == "alice"

    auth_mod._jwt_key_objects.cache_clear()
    monkeypatch.setattr(auth_mod.config, "JWT_ALGORITHM", "ES256", raising=False)
    monkeypatch.setattr(auth_mod.config, "JWT_PRIVATE_KEY", ec_private, raising=False)
    monkeypatch.setattr(auth_mod.config, "JWT_PUBLIC_KEY", ec_public, raising=False)
    assert auth_mod._jwt_signing_key()
    assert auth_mod._jwt_verification_key()


def test_authenticate_update_password_and_validate_otlp(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(auth_mod, "_utcnow", lambda: now)
    monkeypatch.setattr(auth_mod.config, "DEFAULT_ADMIN_USERNAME", "admin", raising=False)
    monkeypatch.setattr(auth_mod.config, "DEFAULT_ADMIN_PASSWORD", "pw", raising=False)
    monkeypatch.setattr(auth_mod.config, "PASSWORD_RESET_INTERVAL_DAYS", 30, raising=False)
    monkeypatch.setattr(auth_mod.config, "DEFAULT_ORG_ID", "org-default", raising=False)
    monkeypatch.setattr(auth_mod.config, "DEFAULT_OTLP_TOKEN", "default-token", raising=False)

    user = SimpleNamespace(
        id="u1",
        username="admin",
        hashed_password="pw",
        is_active=True,
        needs_password_change=False,
        password_changed_at=now - timedelta(days=40),
        last_login=None,
        tenant=SimpleNamespace(id="tenant"),
        groups=[],
        permissions=[],
    )
    hydrated = SimpleNamespace(id="u1")
    db = _DB(user, hydrated)
    monkeypatch.setattr(auth_mod, "get_db_session", lambda: _ctx(db))
    authenticated = auth_mod.authenticate_user(_service(), " Admin ", "pw")
    assert authenticated is hydrated
    assert db.flushed == 1 and db.committed == 1 and db.expunged == [hydrated]
    assert user.needs_password_change is True

    db = _DB(None)
    monkeypatch.setattr(auth_mod, "get_db_session", lambda: _ctx(db))
    assert auth_mod.authenticate_user(_service(), "alice", "pw") is None

    inactive = SimpleNamespace(id="u2", username="alice", hashed_password="pw", is_active=False)
    db = _DB(inactive)
    monkeypatch.setattr(auth_mod, "get_db_session", lambda: _ctx(db))
    assert auth_mod.authenticate_user(_service(), "alice", "pw") is None

    with pytest.raises(ValueError):
        auth_mod.update_password(_service(), "u1", UserPasswordUpdate(current_password="pw", new_password="short"), "tenant")

    db = _DB(None)
    monkeypatch.setattr(auth_mod, "get_db_session", lambda: _ctx(db))
    assert auth_mod.update_password(_service(), "u1", UserPasswordUpdate(current_password="pw", new_password="newpassword123"), "tenant") is False

    user = SimpleNamespace(id="u1", tenant_id="tenant", auth_provider="oidc", needs_password_change=False, hashed_password="pw")
    db = _DB(user)
    monkeypatch.setattr(auth_mod, "get_db_session", lambda: _ctx(db))
    with pytest.raises(ValueError):
        auth_mod.update_password(_service(), "u1", UserPasswordUpdate(current_password="pw", new_password="newpassword123"), "tenant")

    user = SimpleNamespace(id="u1", tenant_id="tenant", auth_provider="local", needs_password_change=False, hashed_password="pw")
    db = _DB(user)
    monkeypatch.setattr(auth_mod, "get_db_session", lambda: _ctx(db))
    assert auth_mod.update_password(_service(verify_password=lambda raw, hashed: False), "u1", UserPasswordUpdate(current_password="bad", new_password="newpassword123"), "tenant") is False

    user = SimpleNamespace(id="u1", tenant_id="tenant", auth_provider="local", needs_password_change=False, hashed_password="samepass")
    db = _DB(user)
    monkeypatch.setattr(auth_mod, "get_db_session", lambda: _ctx(db))
    with pytest.raises(ValueError):
        auth_mod.update_password(_service(verify_password=lambda raw, hashed: raw == hashed), "u1", UserPasswordUpdate(current_password="samepass", new_password="samepass"), "tenant")

    user = SimpleNamespace(id="u1", tenant_id="tenant", auth_provider="oidc", needs_password_change=True, hashed_password="oldpass", session_invalid_before="x")
    db = _DB(user)
    monkeypatch.setattr(auth_mod, "get_db_session", lambda: _ctx(db))
    assert auth_mod.update_password(_service(verify_password=lambda raw, hashed: raw == hashed), "u1", UserPasswordUpdate(current_password="ignored", new_password="newpassword123"), "tenant") is True
    assert user.auth_provider == "local"
    assert user.hashed_password == "hashed:newpassword123"
    assert user.session_invalid_before is None

    assert auth_mod.validate_otlp_token(_service(), None) is None
    assert auth_mod.validate_otlp_token(_service(), "   ") is None
    assert auth_mod.validate_otlp_token(_service(), "x" * 5000) is None
    assert auth_mod.validate_otlp_token(_service(), "default-token") == "org-default"

    api_key = SimpleNamespace(key="tenant-org")
    db = _DB(api_key)
    monkeypatch.setattr(auth_mod, "get_db_session", lambda: _ctx(db))
    assert auth_mod.validate_otlp_token(_service(), "custom-token") == "tenant-org"

    db = _DB(exc=SQLAlchemyError("db"))
    monkeypatch.setattr(auth_mod, "get_db_session", lambda: _ctx(db))
    assert auth_mod.validate_otlp_token(_service(), "custom-token") is None
    with pytest.raises(SQLAlchemyError):
        auth_mod.validate_otlp_token(_service(), "custom-token", suppress_errors=False)

    @contextmanager
    def _runtime_error_ctx():
        raise RuntimeError("boom")
        yield

    monkeypatch.setattr(auth_mod, "get_db_session", _runtime_error_ctx)
    assert auth_mod.validate_otlp_token(_service(), "custom-token") is None
    with pytest.raises(RuntimeError):
        auth_mod.validate_otlp_token(_service(), "custom-token", suppress_errors=False)