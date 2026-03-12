"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.exc import IntegrityError

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Role, Token
from services.auth import delegation as delegation_mod
from services.database_auth import mfa as mfa_mod
from services.database_auth import oidc as oidc_mod


class _Query:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows if rows is not None else row

    def filter(self, *_args, **_kwargs):
        return self

    def filter_by(self, **_kwargs):
        return self

    def options(self, *_args, **_kwargs):
        return self

    def first(self):
        if isinstance(self.row, list):
            return self.row[0] if self.row else None
        return self.row

    def all(self):
        if self.rows is None:
            return []
        if isinstance(self.rows, list):
            return self.rows
        return [self.rows]


class _DB:
    def __init__(self, *, user=None, tenant=None, conflict=None, flush_errors=None):
        self.user = user
        self.tenant = tenant
        self.conflict = conflict
        self.flush_errors = list(flush_errors or [])
        self.added = []
        self.commits = 0
        self.refreshes = 0
        self.rollbacks = 0
        self.flushed = 0

    def query(self, model, *args, **kwargs):
        name = getattr(model, "__name__", str(model))
        if model is oidc_mod.Tenant or name == "Tenant":
            return _Query(self.tenant)
        if model is oidc_mod.User or name == "User":
            return _Query(self.conflict if self.conflict is not None else self.user)
        return _Query(self.user)

    def add(self, item):
        self.added.append(item)

    def flush(self):
        self.flushed += 1
        if self.flush_errors:
            raise self.flush_errors.pop(0)

    def commit(self):
        self.commits += 1

    def refresh(self, _item):
        self.refreshes += 1

    def rollback(self):
        self.rollbacks += 1


@contextmanager
def _ctx(db):
    yield db


def test_delegation_helpers_and_oidc_pure_helpers(monkeypatch):
    assert delegation_mod.role_to_text(Role.ADMIN) == "admin"
    assert delegation_mod.role_to_text("Role.USER") == "user"
    assert delegation_mod.role_rank("admin", {"admin": 5}) == 5
    assert delegation_mod.is_admin_actor(actor_role="user", actor_is_superuser=True) is True
    assert delegation_mod.is_admin_user(SimpleNamespace(role="admin")) is True
    assert delegation_mod.permission_is_admin_only("manage:users") is True
    assert delegation_mod.permission_is_admin_only("update:user_permissions") is True
    assert delegation_mod.normalize_permissions([" read:users ", "", None]) == {"read:users", "None"}
    with pytest.raises(Exception):
        delegation_mod.require_actor(None, purpose="testing")

    actor = SimpleNamespace(groups=[], permissions=[])
    db = _DB(user=actor)
    service = SimpleNamespace(_collect_permissions=lambda user: ["read:users"])
    assert delegation_mod.resolve_actor_permissions(service, db=db, actor_user_id=None, tenant_id="tenant", actor_permissions=["explicit"]) == {"explicit"}
    assert delegation_mod.resolve_actor_permissions(service, db=db, actor_user_id=None, tenant_id="tenant", actor_permissions=None) == set()
    assert delegation_mod.resolve_actor_permissions(service, db=db, actor_user_id="u1", tenant_id="tenant", actor_permissions=None) == {"read:users"}

    claims = {"permissions": [" read:users ", "bad"], "scp": ["write:users", " "]}
    assert oidc_mod._claim_str({"email": " a@b.c "}, "email") == "a@b.c"
    assert oidc_mod.extract_permissions_from_oidc_claims(claims) == ["read:users", "write:users"]
    assert oidc_mod._normalize_claim_list([" a ", "", None]) == {"a", "None"}
    assert oidc_mod._claim_truthy("yes") is True
    assert oidc_mod._claim_truthy(0) is False
    monkeypatch.setattr(oidc_mod.config, "OIDC_AUTO_LINK_BY_EMAIL", True, raising=False)
    monkeypatch.setattr(oidc_mod.config, "OIDC_REQUIRE_VERIFIED_EMAIL_FOR_LINK", True, raising=False)
    assert oidc_mod._can_auto_link_by_email({"email_verified": True}) is True
    assert oidc_mod._normalize_email({"email": "UP@EXAMPLE.COM"}) == "up@example.com"
    assert oidc_mod._normalize_subject({"sub": " sub "}) == "sub"
    assert oidc_mod._preferred_username({"preferred_username": " Alice "}, "a@example.com") == "alice"
    assert oidc_mod._preferred_username({}, "a@example.com") == "a"
    assert oidc_mod._full_name({"name": "Alice"}) == "Alice"
    assert oidc_mod._base_username("", "a@example.com") == "a"

    exists = iter([True, True, False])
    monkeypatch.setattr(oidc_mod, "_username_exists", lambda db, username: next(exists))
    assert oidc_mod._pick_unique_username(object(), "alice") == "alice2"


def test_mfa_helpers_and_flows(monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setattr("config.config.DATA_ENCRYPTION_KEY", None)
    monkeypatch.setattr("config.config.REQUIRE_TOTP_ENCRYPTION_KEY", False)
    assert mfa_mod._get_fernet(SimpleNamespace()) is None

    monkeypatch.setattr("config.config.REQUIRE_TOTP_ENCRYPTION_KEY", True)
    with pytest.raises(ValueError):
        mfa_mod._get_fernet(SimpleNamespace())

    monkeypatch.setattr("config.config.REQUIRE_TOTP_ENCRYPTION_KEY", False)
    monkeypatch.setattr("config.config.DATA_ENCRYPTION_KEY", b"bad")
    with pytest.raises(ValueError):
        mfa_mod._get_fernet(SimpleNamespace())

    monkeypatch.setattr("config.config.DATA_ENCRYPTION_KEY", key)
    encrypted = mfa_mod._encrypt_mfa_secret(SimpleNamespace(), "secret")
    assert mfa_mod._decrypt_mfa_secret(SimpleNamespace(), encrypted) == "secret"
    with pytest.raises(ValueError):
        mfa_mod._decrypt_mfa_secret(SimpleNamespace(), "bad-token")

    monkeypatch.setattr(mfa_mod.secrets, "token_urlsafe", lambda _n: "recovery")
    codes = mfa_mod._generate_recovery_codes(SimpleNamespace(), count=2)
    assert codes == ["recovery", "recovery"]
    hashes = mfa_mod._hash_recovery_codes(SimpleNamespace(), ["one"])
    assert mfa_mod._consume_recovery_code(SimpleNamespace(), SimpleNamespace(mfa_recovery_hashes=hashes), "one") is True
    user = SimpleNamespace(mfa_recovery_hashes=["bad"])
    assert mfa_mod._consume_recovery_code(SimpleNamespace(), user, "one") is False

    service = SimpleNamespace(_log_audit=lambda *args, **kwargs: None, verify_password=lambda password, hashed: password == "pw", _MFA_SETUP_RESPONSE="mfa_setup_required")
    user = SimpleNamespace(id="u1", email="a@b.c", username="alice", totp_secret="enc", tenant_id="tenant", mfa_enabled=False, must_setup_mfa=True, mfa_recovery_hashes=[])
    db = _DB(user=user)
    monkeypatch.setattr(mfa_mod, "get_db_session", lambda: _ctx(db))
    monkeypatch.setattr(mfa_mod, "_encrypt_mfa_secret", lambda service, secret: f"enc:{secret}")
    monkeypatch.setattr(mfa_mod.pyotp, "random_base32", lambda: "BASE32")

    class _TOTP:
        def __init__(self, secret):
            self.secret = secret

        def provisioning_uri(self, name, issuer_name):
            return f"otpauth://{name}/{issuer_name}/{self.secret}"

        def verify(self, code, valid_window=1):
            return code == "123456"

    monkeypatch.setattr(mfa_mod.pyotp, "TOTP", _TOTP)
    enrolled = mfa_mod.enroll_totp(service, "u1")
    assert enrolled["secret"] == "BASE32"
    assert user.totp_secret == "enc:BASE32"

    monkeypatch.setattr(mfa_mod, "_decrypt_mfa_secret", lambda service, token: "BASE32")
    monkeypatch.setattr(mfa_mod, "_generate_recovery_codes", lambda service: ["r1", "r2"])
    monkeypatch.setattr(mfa_mod, "_hash_recovery_codes", lambda service, codes: [f"h:{code}" for code in codes])
    assert mfa_mod.verify_enable_totp(service, "u1", "123456") == ["r1", "r2"]
    with pytest.raises(ValueError):
        mfa_mod.verify_enable_totp(service, "u1", "bad")

    user.id = "u2"
    db = _DB(user=user)
    monkeypatch.setattr(mfa_mod, "get_db_session", lambda: _ctx(db))
    monkeypatch.setattr(mfa_mod, "_consume_recovery_code", lambda service, db_user, code: code == "recovery")
    assert mfa_mod.verify_totp_code(service, user, "recovery") is True
    monkeypatch.setattr(mfa_mod, "_consume_recovery_code", lambda service, db_user, code: False)
    assert mfa_mod.verify_totp_code(service, user, "123456") is True
    monkeypatch.setattr(mfa_mod, "_decrypt_mfa_secret", lambda service, token: (_ for _ in ()).throw(ValueError("bad")))
    assert mfa_mod.verify_totp_code(service, user, "123456") is False

    user.hashed_password = "hashed"
    user.mfa_enabled = True
    user.totp_secret = "enc"
    monkeypatch.setattr(mfa_mod, "_verify_totp_code_in_db_user", lambda service, user, code: code == "123456")
    assert mfa_mod.disable_totp(service, "u2", current_password="pw") is False
    user.mfa_enabled = True
    user.totp_secret = "enc"
    assert mfa_mod.disable_totp(service, "u2", code="123456") is True
    user.mfa_enabled = False
    assert mfa_mod.disable_totp(service, "u2", current_password="pw") is False

    user.mfa_enabled = True
    assert mfa_mod.reset_totp(service, "u2", "admin") is True
    monkeypatch.setattr(mfa_mod, "create_mfa_setup_token_op", lambda user: None)
    with pytest.raises(ValueError, match="setup token"):
        mfa_mod.mfa_setup_challenge(service, user)
    monkeypatch.setattr(mfa_mod, "create_mfa_setup_token_op", lambda user: Token(access_token="jwt", expires_in=60))
    assert mfa_mod.mfa_setup_challenge(service, user)["setup_token"] == "jwt"
    assert mfa_mod.needs_mfa_setup(SimpleNamespace(must_setup_mfa=True, mfa_enabled=False)) is True


def test_oidc_sync_and_provision_helpers(monkeypatch):
    real_provision_oidc_user = oidc_mod.provision_oidc_user
    real_update_oidc_user = oidc_mod.update_oidc_user
    fake_user_model = type("User", (), {"external_subject": "external_subject", "id": "id", "email": "email", "username": "username"})
    fake_tenant_model = type("Tenant", (), {"__init__": lambda self, **kwargs: self.__dict__.update(kwargs)})
    monkeypatch.setattr(oidc_mod, "User", fake_user_model)
    monkeypatch.setattr(oidc_mod, "Tenant", fake_tenant_model)
    monkeypatch.setattr(oidc_mod, "func", SimpleNamespace(lower=lambda value: value))
    monkeypatch.setattr(oidc_mod.config, "DEFAULT_ADMIN_TENANT", "default", raising=False)
    monkeypatch.setattr(oidc_mod.config, "DEFAULT_ORG_ID", "org-default", raising=False)
    monkeypatch.setattr(oidc_mod.config, "AUTH_PROVIDER", "oidc", raising=False)
    monkeypatch.setattr(oidc_mod.config, "OIDC_AUTO_PROVISION_USERS", True, raising=False)
    monkeypatch.setattr(oidc_mod.config, "REQUIRE_MFA_FOR_NEW_USERS", True, raising=False)

    service = SimpleNamespace(
        _lazy_init=lambda: None,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
        hash_password=lambda password: f"hashed:{password}",
        _ensure_default_api_key=lambda db, user: setattr(user, "api_key_created", True),
    )

    existing = SimpleNamespace(id="u1", auth_provider="local", is_active=True, email="a@b.c", full_name="Old", external_subject=None)
    monkeypatch.setattr(oidc_mod, "_resolve_existing_user", lambda service, db, **kwargs: existing)
    updated = []
    monkeypatch.setattr(oidc_mod, "update_oidc_user", lambda db, user, email, full_name, subject: updated.append((email, full_name, subject)))
    db = _DB(user=existing)
    monkeypatch.setattr(oidc_mod, "get_db_session", lambda: _ctx(db))
    synced = oidc_mod.sync_user_from_oidc_claims(service, {"email": "a@b.c", "sub": "sub-1", "name": "Alice"})
    assert synced is existing
    assert db.commits == 1 and db.refreshes == 1
    assert updated == [("a@b.c", "Alice", "sub-1")]

    monkeypatch.setattr(oidc_mod, "_resolve_existing_user", lambda service, db, **kwargs: None)
    provisioned = SimpleNamespace(id="u2", is_active=True)
    monkeypatch.setattr(oidc_mod, "provision_oidc_user", lambda service, db, email, preferred_username, full_name, subject: provisioned)
    db = _DB(user=provisioned)
    monkeypatch.setattr(oidc_mod, "get_db_session", lambda: _ctx(db))
    assert oidc_mod.sync_user_from_oidc_claims(service, {"email": "b@c.d", "sub": "sub-2"}) is provisioned

    inactive = SimpleNamespace(id="u3", is_active=False, email="c@d.e", full_name=None, external_subject=None)
    monkeypatch.setattr(oidc_mod, "_resolve_existing_user", lambda service, db, **kwargs: inactive)
    db = _DB(user=inactive)
    monkeypatch.setattr(oidc_mod, "get_db_session", lambda: _ctx(db))
    assert oidc_mod.sync_user_from_oidc_claims(service, {"email": "c@d.e", "sub": "sub-3"}) is None
    assert oidc_mod.sync_user_from_oidc_claims(service, {"sub": "missing-email"}) is None

    tenant = SimpleNamespace(id="tenant-1")
    db = _DB(tenant=tenant)
    assert oidc_mod._ensure_default_tenant(db) is tenant
    db = _DB(tenant=None, flush_errors=[IntegrityError("stmt", {}, Exception("dup"))])
    db.tenant = SimpleNamespace(id="tenant-2")
    assert oidc_mod._ensure_default_tenant(db).id == "tenant-2"

    fake_user_ctor = lambda **kwargs: SimpleNamespace(**kwargs)
    monkeypatch.setattr(oidc_mod, "provision_oidc_user", real_provision_oidc_user)
    monkeypatch.setattr(oidc_mod, "User", fake_user_ctor)
    monkeypatch.setattr(oidc_mod, "_ensure_default_tenant", lambda db: SimpleNamespace(id="tenant-1"))
    attempts = iter(["alice", "alice1"])
    monkeypatch.setattr(oidc_mod, "_pick_unique_username", lambda db, base: next(attempts))
    token_values = iter(["pw1", "pw2"])
    monkeypatch.setattr(oidc_mod.secrets, "token_urlsafe", lambda _n: next(token_values))
    db = _DB(flush_errors=[IntegrityError("stmt", {}, Exception("dup"))])
    provisioned = oidc_mod.provision_oidc_user(service, db, "new@example.com", "alice", "Alice", "subject")
    assert provisioned.username == "alice1"
    assert db.rollbacks == 0
    assert getattr(provisioned, "api_key_created", False) is True

    user = SimpleNamespace(id="u9", auth_provider="local", external_subject=None, email="old@example.com", full_name="Old")
    db = _DB(conflict=None)
    monkeypatch.setattr(oidc_mod, "User", fake_user_model)
    monkeypatch.setattr(oidc_mod, "update_oidc_user", real_update_oidc_user)
    oidc_mod.update_oidc_user(db, user, "new@example.com", "New", "subject")
    assert user.auth_provider == "oidc"
    assert user.external_subject == "subject"
    assert user.email == "new@example.com"
    assert user.full_name == "New"
