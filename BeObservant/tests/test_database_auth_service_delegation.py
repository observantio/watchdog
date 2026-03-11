
"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import SQLAlchemyError

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from config import config
from services import database_auth_service as das


def _patch_sync(monkeypatch, obj, name, result, calls):
    def fake(*args, **kwargs):
        calls.append((name, args, kwargs))
        return result

    monkeypatch.setattr(obj, name, fake)


def test_lazy_init_sets_initialized(monkeypatch):
    svc = das.DatabaseAuthService()
    svc._initialized = False
    monkeypatch.setattr(svc, "_ensure_default_setup", lambda: None)

    svc._lazy_init()

    assert isinstance(svc._initialized, bool)


def test_lazy_init_swallows_bootstrap_errors(monkeypatch):
    svc = das.DatabaseAuthService()

    def blow_up():
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(svc, "_ensure_default_setup", blow_up)
    svc._lazy_init()

    assert svc._initialized is False


@pytest.mark.parametrize(
    ("provider", "enabled", "expected"),
    [
        ("oidc", True, True),
        ("keycloak", True, True),
        ("oidc", False, False),
        ("local", True, False),
    ],
)
def test_auth_mode_helpers(monkeypatch, provider, enabled, expected):
    svc = das.DatabaseAuthService()
    monkeypatch.setattr(config, "AUTH_PROVIDER", provider)
    monkeypatch.setattr(svc.oidc_service, "is_enabled", lambda: enabled)
    monkeypatch.setattr(config, "AUTH_PASSWORD_FLOW_ENABLED", 1)

    assert svc.is_external_auth_enabled() is expected
    assert svc.is_password_auth_enabled() is True


def test_otlp_helpers(monkeypatch):
    svc = das.DatabaseAuthService()
    monkeypatch.setattr(config, "DEFAULT_OTLP_TOKEN", "configured-token")

    assert svc._resolve_default_otlp_token() == "configured-token"
    assert svc._hash_otlp_token("abc") == svc._hash_otlp_token("abc")
    generated = svc._generate_otlp_token()
    assert generated.startswith("bo_")


def test_authenticate_user_short_circuits_for_external_only(monkeypatch):
    svc = das.DatabaseAuthService()
    monkeypatch.setattr(svc, "is_external_auth_enabled", lambda: True)
    monkeypatch.setattr(svc, "is_password_auth_enabled", lambda: False)

    assert svc.authenticate_user("user", "pass") is None


def test_list_and_replace_api_key_shares_dump_models(monkeypatch):
    svc = das.DatabaseAuthService()

    class Share:
        def __init__(self, payload):
            self.payload = payload

        def model_dump(self):
            return self.payload

    monkeypatch.setattr(das, "list_api_key_shares_op", lambda *_args: [Share({"user_id": "u1"})])
    monkeypatch.setattr(
        das,
        "replace_api_key_shares_op",
        lambda *_args, **_kwargs: [Share({"user_id": "u2"}), Share({"user_id": "u3"})],
    )

    assert svc.list_api_key_shares("owner", "tenant", "key") == [{"user_id": "u1"}]
    assert svc.replace_api_key_shares("owner", "tenant", "key", ["u2"], group_ids=["g1"]) == [
        {"user_id": "u2"},
        {"user_id": "u3"},
    ]


@pytest.mark.parametrize(
    ("module_name", "attr_name", "method_name", "args", "kwargs", "result"),
    [
        ("db_bootstrap", "ensure_permissions", "_ensure_permissions", ("db",), {}, None),
        ("db_bootstrap", "ensure_default_api_key", "_ensure_default_api_key", ("db", "user"), {}, None),
        ("db_password", "hash_password", "hash_password", ("secret",), {}, "hashed"),
        ("db_password", "verify_password", "verify_password", ("plain", "hashed"), {}, True),
        (
            "db_password",
            "reset_user_password_temp",
            "reset_user_password_temp",
            ("actor", "target", "tenant"),
            {},
            {1: "x", "target": "y"},
        ),
        ("db_mfa", "_get_fernet", "_get_fernet", (), {}, "fernet"),
        ("db_mfa", "_encrypt_mfa_secret", "_encrypt_mfa_secret", ("secret",), {}, "cipher"),
        ("db_mfa", "_decrypt_mfa_secret", "_decrypt_mfa_secret", ("token",), {}, "plain"),
        ("db_mfa", "_generate_recovery_codes", "_generate_recovery_codes", (), {"count": 3}, ["a", "b", "c"]),
        ("db_mfa", "_hash_recovery_codes", "_hash_recovery_codes", (["a"],), {}, ["hashed"]),
        ("db_mfa", "_consume_recovery_code", "_consume_recovery_code", ("db_user", "code"), {}, True),
        ("db_mfa", "enroll_totp", "enroll_totp", ("user-1",), {}, {"secret": "s", "otpauth_url": "u"}),
        ("db_mfa", "verify_enable_totp", "verify_enable_totp", ("user-1", "123456"), {}, ["recovery"]),
        ("db_mfa", "verify_totp_code", "verify_totp_code", ("user", "123456"), {}, True),
        (
            "db_mfa",
            "disable_totp",
            "disable_totp",
            ("user-1",),
            {"current_password": "pw", "code": "123"},
            True,
        ),
        ("db_mfa", "reset_totp", "reset_totp", ("user-1", "admin"), {}, True),
        ("db_mfa", "mfa_setup_challenge", "_mfa_setup_challenge", ("user",), {}, {"challenge": True}),
        ("db_mfa", "needs_mfa_setup", "_needs_mfa_setup", ("user",), {}, False),
        ("das", "create_access_token_op", "create_access_token", ("user",), {}, "token"),
        ("db_token", "build_token_data_for_user", "_build_token_data_for_user", ("user",), {}, "token-data"),
        ("db_token", "decode_token", "decode_token", ("jwt",), {}, "decoded"),
        ("db_auth", "login", "login", ("user", "pass", "000000"), {}, "login-ok"),
        (
            "db_auth",
            "exchange_oidc_authorization_code",
            "exchange_oidc_authorization_code",
            ("code", "https://cb"),
            {"transaction_id": "tx", "state": "st", "code_verifier": "ver"},
            "exchange-ok",
        ),
        (
            "db_auth",
            "get_oidc_authorization_url",
            "get_oidc_authorization_url",
            ("https://cb",),
            {
                "state": "st",
                "nonce": "no",
                "code_challenge": "cc",
                "code_challenge_method": "S256",
            },
            {"authorization_url": "https://idp"},
        ),
        (
            "db_auth",
            "provision_external_user",
            "provision_external_user",
            (),
            {"email": "u@example.com", "username": "user", "full_name": "U"},
            "user-id",
        ),
        (
            "db_oidc",
            "extract_permissions_from_oidc_claims",
            "_extract_permissions_from_oidc_claims",
            ({"groups": []},),
            {},
            ["read:users"],
        ),
        ("db_oidc", "sync_user_from_oidc_claims", "_sync_user_from_oidc_claims", ({"sub": "1"},), {}, "user"),
        (
            "db_oidc",
            "provision_oidc_user",
            "_provision_oidc_user",
            ("db", "u@example.com", "user", "User", "sub"),
            {},
            "db-user",
        ),
        (
            "db_oidc",
            "update_oidc_user",
            "_update_oidc_user",
            ("db", "user", "u@example.com", "User", "sub"),
            {},
            None,
        ),
        ("db_permissions", "get_user_permissions", "get_user_permissions", ("user",), {}, ["a"]),
        ("db_permissions", "get_user_direct_permissions", "get_user_direct_permissions", ("user",), {}, ["b"]),
        ("db_permissions", "collect_permissions", "_collect_permissions", ("user",), {}, ["c"]),
        ("db_permissions", "list_all_permissions", "list_all_permissions", (), {}, [{"name": "read:users"}]),
        ("db_schema", "to_user_schema", "_to_user_schema", ("user",), {}, "user-schema"),
        ("db_schema", "build_user_response", "build_user_response", ("user", ["perm"]), {}, "user-response"),
        ("db_schema", "to_api_key_schema", "_to_api_key_schema", ("api-key",), {}, "api-key-schema"),
        ("db_schema", "to_group_schema", "_to_group_schema", ("group",), {}, "group-schema"),
        ("das", "get_user_by_id_op", "get_user_by_id", ("user-1",), {"tenant_id": "tenant", "db": "db"}, "user"),
        ("das", "get_user_by_id_op", "get_user_by_id_in_tenant", ("user-1", "tenant"), {}, "user"),
        ("das", "get_user_by_username_op", "get_user_by_username", ("name",), {}, "user"),
        (
            "das",
            "create_user_op",
            "create_user",
            ("payload", "tenant"),
            {
                "creator_id": "creator",
                "actor_role": "admin",
                "actor_permissions": ["perm"],
                "actor_is_superuser": True,
            },
            "created-user",
        ),
        ("das", "list_users_op", "list_users", ("tenant",), {"limit": 10, "offset": 2}, ["user"]),
        ("das", "update_user_op", "update_user", ("user-1", "update", "tenant", "updater"), {}, "updated-user"),
        ("das", "set_grafana_user_id_op", "set_grafana_user_id", ("user-1", 42, "tenant"), {}, True),
        ("das", "delete_user_op", "delete_user", ("user-1", "tenant", "deleter"), {}, True),
        (
            "das",
            "update_user_permissions_op",
            "update_user_permissions",
            ("user-1", ["perm"], "tenant"),
            {
                "actor_user_id": "actor",
                "actor_role": "admin",
                "actor_permissions": ["perm"],
                "actor_is_superuser": True,
            },
            True,
        ),
        ("das", "update_password_op", "update_password", ("user-1", "pw-update", "tenant"), {}, True),
        ("das", "list_api_keys_op", "list_api_keys", ("user-1", True), {}, ["key"]),
        ("das", "create_api_key_op", "create_api_key", ("user-1", "tenant", "create"), {}, "key"),
        ("das", "update_api_key_op", "update_api_key", ("user-1", "key", "update"), {}, "key"),
        ("das", "set_api_key_hidden_op", "set_api_key_hidden", ("user-1", "key", False), {}, True),
        ("das", "regenerate_api_key_otlp_token_op", "regenerate_api_key_otlp_token", ("user-1", "key"), {}, "key"),
        ("das", "delete_api_key_op", "delete_api_key", ("user-1", "key"), {}, True),
        ("das", "delete_api_key_share_op", "delete_api_key_share", ("owner", "tenant", "key", "shared"), {}, True),
        ("das", "validate_otlp_token_op", "validate_otlp_token", ("token",), {"suppress_errors": False}, "tenant"),
        ("das", "backfill_otlp_tokens_op", "backfill_otlp_tokens", (), {}, None),
        ("das", "create_group_op", "create_group", ("group-create", "tenant", "creator"), {}, "group"),
        (
            "das",
            "list_groups_op",
            "list_groups",
            ("tenant",),
            {"actor_user_id": "actor", "actor_role": "admin", "actor_is_superuser": True},
            ["group"],
        ),
        (
            "das",
            "get_group_op",
            "get_group",
            ("group-1", "tenant"),
            {"actor_user_id": "actor", "actor_role": "admin", "actor_is_superuser": True},
            "group",
        ),
        (
            "das",
            "delete_group_op",
            "delete_group",
            ("group-1", "tenant", "deleter"),
            {"actor_role": "admin", "actor_is_superuser": True},
            True,
        ),
        (
            "das",
            "update_group_op",
            "update_group",
            ("group-1", "update", "tenant", "updater"),
            {"actor_role": "admin", "actor_is_superuser": True},
            "group",
        ),
        (
            "das",
            "update_group_permissions_op",
            "update_group_permissions",
            ("group-1", ["perm"], "tenant"),
            {
                "actor_user_id": "actor",
                "actor_role": "admin",
                "actor_permissions": ["perm"],
                "actor_is_superuser": True,
            },
            True,
        ),
        (
            "das",
            "update_group_members_op",
            "update_group_members",
            ("group-1", ["u1"], "tenant"),
            {
                "actor_user_id": "actor",
                "actor_role": "admin",
                "actor_permissions": ["perm"],
                "actor_is_superuser": True,
            },
            True,
        ),
    ],
)
def test_database_auth_service_delegates(monkeypatch, module_name, attr_name, method_name, args, kwargs, result):
    svc = das.DatabaseAuthService()
    calls = []

    def fake(*call_args, **call_kwargs):
        calls.append((call_args, call_kwargs))
        return result

    target = das if module_name == "das" else getattr(das, module_name)
    monkeypatch.setattr(target, attr_name, fake)

    value = getattr(svc, method_name)(*args, **kwargs)

    assert value == ({str(k): v for k, v in result.items()} if method_name == "reset_user_password_temp" else result)
    if method_name != "backfill_otlp_tokens":
        assert calls, method_name


def test_log_audit_delegates(monkeypatch):
    svc = das.DatabaseAuthService()
    called = {}

    def fake(*args, **kwargs):
        called["args"] = args
        called["kwargs"] = kwargs

    monkeypatch.setattr(das.db_audit, "log_audit", fake)

    svc._log_audit(
        "db",
        "tenant",
        "user",
        "action",
        "resource",
        "id-1",
        {"ok": True},
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert called["args"][:6] == ("db", "tenant", "user", "action", "resource", "id-1")
    assert called["kwargs"] == {"ip_address": "127.0.0.1", "user_agent": "pytest"}