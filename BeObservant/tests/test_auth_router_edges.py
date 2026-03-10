"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request, Response

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from models.access.api_key_models import ApiKey, ApiKeyCreate, ApiKeyShareUpdateRequest, ApiKeyUpdate
from models.access.auth_models import Permission, Role, Token, TokenData
from models.access.group_models import GroupCreate, GroupMembersUpdate, GroupUpdate
from models.access.user_models import LoginRequest, MfaDisableRequest, MfaVerifyRequest, RegisterRequest, UserCreate, UserPasswordUpdate, UserUpdate
from routers.access.auth_router import api_keys as api_keys_router
from routers.access.auth_router import authentication as auth_router
from routers.access.auth_router import groups as groups_router
from routers.access.auth_router import mfa as mfa_router
from routers.access.auth_router import users as users_router


def _request(headers: list[tuple[bytes, bytes]] | None = None, cookies: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/",
        "headers": headers or [],
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
        "query_string": b"",
    }
    if cookies:
        scope["headers"] = scope["headers"] + [(b"cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()).encode("utf-8"))]
    return Request(scope)


async def _rtp(func, *args, **kwargs):
    value = func(*args, **kwargs)
    if inspect.isawaitable(value):
        return await value
    return value


def _current_user(**kwargs) -> TokenData:
    data = {
        "user_id": "u1",
        "username": "user",
        "tenant_id": "tenant",
        "org_id": "org",
        "role": Role.ADMIN,
        "permissions": [permission.value for permission in Permission],
        "group_ids": ["g1"],
        "is_superuser": True,
    }
    data.update(kwargs)
    return TokenData(**data)


@pytest.fixture(autouse=True)
def _patch_shared(monkeypatch):
    for module in (auth_router, api_keys_router, users_router, groups_router, mfa_router):
        monkeypatch.setattr(module, "rtp", _rtp)
    monkeypatch.setattr(auth_router, "rate_limit_func", lambda *_args, **_kwargs: None)


@pytest.mark.asyncio
async def test_authentication_routes_cover_success_and_error_branches(monkeypatch):
    cookie_calls = []
    cleared = []
    monkeypatch.setattr(auth_router, "set_auth_cookie", lambda request, response, token: cookie_calls.append((request, response, token)))
    monkeypatch.setattr(auth_router, "clear_auth_cookie", lambda request, response: cleared.append((request, response)))
    monkeypatch.setattr(auth_router.auth_service, "is_external_auth_enabled", lambda: True)
    monkeypatch.setattr(auth_router.auth_service, "is_password_auth_enabled", lambda: False)

    mode = await auth_router.auth_mode()
    assert mode.oidc_enabled is True
    assert mode.password_enabled is False

    request = _request()
    response = Response()
    login_payload = LoginRequest(username="User", password="secret")
    monkeypatch.setattr(auth_router.auth_service, "login", lambda *_args: None)
    with pytest.raises(HTTPException) as exc:
        await auth_router.login(request, login_payload, response)
    assert exc.value.status_code == 403

    monkeypatch.setattr(auth_router.auth_service, "is_password_auth_enabled", lambda: True)
    with pytest.raises(HTTPException) as exc:
        await auth_router.login(request, login_payload, response)
    assert exc.value.status_code == 401

    monkeypatch.setattr(auth_router.auth_service, "login", lambda *_args: {"mfa_required": True})
    with pytest.raises(HTTPException) as exc:
        await auth_router.login(request, login_payload, response)
    assert exc.value.detail == "MFA required"

    monkeypatch.setattr(auth_router.auth_service, "login", lambda *_args: {"mfa_setup_required": True})
    with pytest.raises(HTTPException) as exc:
        await auth_router.login(request, login_payload, response)
    assert exc.value.detail == {"mfa_setup_required": True}

    token = Token(access_token="jwt", expires_in=60)
    monkeypatch.setattr(auth_router.auth_service, "login", lambda *_args: token)
    assert await auth_router.login(request, login_payload, response) == token
    assert cookie_calls[-1][2] == "jwt"

    oidc_request = auth_router.OIDCAuthURLRequest(redirect_uri="https://app/callback", state="s")
    monkeypatch.setattr(auth_router.auth_service, "is_external_auth_enabled", lambda: False)
    with pytest.raises(HTTPException) as exc:
        await auth_router.oidc_authorize_url(request, oidc_request)
    assert exc.value.status_code == 400

    monkeypatch.setattr(auth_router.auth_service, "is_external_auth_enabled", lambda: True)
    monkeypatch.setattr(auth_router.auth_service, "get_oidc_authorization_url", lambda *_args: (_ for _ in ()).throw(ValueError("bad")))
    with pytest.raises(HTTPException) as exc:
        await auth_router.oidc_authorize_url(request, oidc_request)
    assert exc.value.status_code == 500

    monkeypatch.setattr(
        auth_router.auth_service,
        "get_oidc_authorization_url",
        lambda *_args: {"authorization_url": "https://idp", "state": "s", "transaction_id": "tx"},
    )
    result = await auth_router.oidc_authorize_url(request, oidc_request)
    assert result.authorization_url == "https://idp"

    exchange_payload = auth_router.OIDCCodeExchangeRequest(code="abc", redirect_uri="https://app/callback")
    monkeypatch.setattr(auth_router.auth_service, "exchange_oidc_authorization_code", lambda *_args: (_ for _ in ()).throw(ValueError("denied")))
    with pytest.raises(HTTPException) as exc:
        await auth_router.oidc_exchange_token(request, exchange_payload, response)
    assert exc.value.detail == "denied"

    monkeypatch.setattr(auth_router.auth_service, "exchange_oidc_authorization_code", lambda *_args: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(HTTPException) as exc:
        await auth_router.oidc_exchange_token(request, exchange_payload, response)
    assert exc.value.detail == "OIDC authentication failed"

    monkeypatch.setattr(auth_router.auth_service, "exchange_oidc_authorization_code", lambda *_args: None)
    with pytest.raises(HTTPException) as exc:
        await auth_router.oidc_exchange_token(request, exchange_payload, response)
    assert exc.value.detail == "OIDC authentication failed"

    monkeypatch.setattr(auth_router.auth_service, "exchange_oidc_authorization_code", lambda *_args: {"mfa_setup_required": True})
    with pytest.raises(HTTPException) as exc:
        await auth_router.oidc_exchange_token(request, exchange_payload, response)
    assert exc.value.detail == {"mfa_setup_required": True}

    monkeypatch.setattr(auth_router.auth_service, "exchange_oidc_authorization_code", lambda *_args: {"other": True})
    with pytest.raises(HTTPException) as exc:
        await auth_router.oidc_exchange_token(request, exchange_payload, response)
    assert exc.value.detail == "OIDC authentication challenge could not be completed"

    monkeypatch.setattr(auth_router.auth_service, "exchange_oidc_authorization_code", lambda *_args: token)
    assert await auth_router.oidc_exchange_token(request, exchange_payload, response) == token
    assert cookie_calls[-1][2] == "jwt"

    assert await auth_router.logout(request, response) == {"message": "Logged out"}
    assert cleared


@pytest.mark.asyncio
async def test_register_uses_default_tenant_and_sends_welcome_email(monkeypatch):
    monkeypatch.setattr(auth_router.auth_service, "is_external_auth_enabled", lambda: False)
    user = SimpleNamespace(email="u@example.com", username="user", full_name="User", role=Role.USER)
    response_obj = SimpleNamespace(api_keys=[])
    monkeypatch.setattr(auth_router.auth_service, "create_user", lambda *_args: user)
    monkeypatch.setattr(auth_router.auth_service, "build_user_response", lambda *_args: response_obj)

    sent = []

    class FakeQuery:
        def filter_by(self, **_kwargs):
            return self

        def first(self):
            return SimpleNamespace(id="tenant-id")

    class FakeDB:
        def query(self, *_args):
            return FakeQuery()

    class FakeCtx:
        def __enter__(self):
            return FakeDB()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(auth_router, "get_db_session", lambda: FakeCtx())

    async def fake_send(**kwargs):
        sent.append(kwargs)
        return True

    monkeypatch.setattr(auth_router.notification_service, "send_user_welcome_email", fake_send)

    result = await auth_router.register(
        _request(),
        RegisterRequest(username="new-user", email="u@example.com", password="password123", full_name="User"),
    )
    assert result is response_obj
    assert sent[0]["recipient_email"] == "u@example.com"


@pytest.mark.asyncio
async def test_register_is_blocked_for_external_auth(monkeypatch):
    monkeypatch.setattr(auth_router.auth_service, "is_external_auth_enabled", lambda: True)
    with pytest.raises(HTTPException) as exc:
        await auth_router.register(
            _request(),
            RegisterRequest(username="new-user", email="u@example.com", password="password123"),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_api_key_routes_cover_not_found_and_transformations(monkeypatch):
    now = datetime.now(timezone.utc)
    current_user = _current_user()
    api_key = ApiKey(id="k1", name="Key", key="secret", created_at=now)
    monkeypatch.setattr(api_keys_router.auth_service, "list_api_keys", lambda *_args: [api_key])
    assert await api_keys_router.list_api_keys(True, current_user) == [api_key]

    monkeypatch.setattr(api_keys_router.auth_service, "create_api_key", lambda *_args: api_key)
    assert await api_keys_router.create_api_key(ApiKeyCreate(name="Key"), current_user) == api_key

    monkeypatch.setattr(api_keys_router.auth_service, "update_api_key", lambda *_args: api_key)
    assert await api_keys_router.update_api_key("k1", ApiKeyUpdate(name="New"), current_user) == api_key

    monkeypatch.setattr(api_keys_router.auth_service, "regenerate_api_key_otlp_token", lambda *_args: api_key)
    assert await api_keys_router.regenerate_api_key_otlp_token("k1", current_user) == api_key

    monkeypatch.setattr(api_keys_router.auth_service, "delete_api_key", lambda *_args: False)
    with pytest.raises(HTTPException) as exc:
        await api_keys_router.delete_api_key("missing", current_user)
    assert exc.value.status_code == 404

    monkeypatch.setattr(api_keys_router.auth_service, "delete_api_key", lambda *_args: True)
    assert await api_keys_router.delete_api_key("k1", current_user) == {"message": "API key deleted"}

    calls = []
    monkeypatch.setattr(api_keys_router.auth_service, "set_api_key_hidden", lambda *_args: calls.append(_args) or True)
    assert await api_keys_router.hide_api_key("k1", api_keys_router.HideTogglePayload(hidden=False), current_user) == {
        "status": "success",
        "hidden": False,
    }
    assert calls

    share_payload = {"user_id": "u2", "username": "user2", "email": "u2@example.com", "created_at": now.isoformat()}
    monkeypatch.setattr(api_keys_router.auth_service, "list_api_key_shares", lambda *_args: [share_payload])
    shares = await api_keys_router.get_api_key_shares("k1", current_user)
    assert shares[0].user_id == "u2"

    monkeypatch.setattr(api_keys_router.auth_service, "replace_api_key_shares", lambda *_args: [share_payload])
    shares = await api_keys_router.put_api_key_shares(
        "k1",
        ApiKeyShareUpdateRequest(user_ids=["u2"], group_ids=["g1"]),
        current_user,
    )
    assert shares[0].email == "u2@example.com"

    monkeypatch.setattr(api_keys_router.auth_service, "delete_api_key_share", lambda *_args: False)
    with pytest.raises(HTTPException) as exc:
        await api_keys_router.remove_api_key_share("k1", "u2", current_user)
    assert exc.value.status_code == 404

    monkeypatch.setattr(api_keys_router.auth_service, "delete_api_key_share", lambda *_args: True)
    assert await api_keys_router.remove_api_key_share("k1", "u2", current_user) == {"message": "API key share removed"}


@pytest.mark.asyncio
async def test_user_group_and_mfa_routes_cover_admin_and_error_paths(monkeypatch):
    current_user = _current_user(is_superuser=False, permissions=[Permission.MANAGE_USERS.value])
    admin_user = _current_user()
    response_obj = SimpleNamespace(api_keys=[])
    user_obj = SimpleNamespace(
        id="u1",
        username="user",
        email="u@example.com",
        full_name="User",
        role=Role.USER,
        tenant_id="tenant",
    )

    monkeypatch.setattr(users_router.auth_service, "get_user_by_id", lambda *_args: user_obj)
    monkeypatch.setattr(users_router.auth_service, "build_user_response", lambda *_args: response_obj)
    monkeypatch.setattr(users_router.auth_service, "list_api_keys", lambda *_args: ["key"])
    result = await users_router.get_current_user_info(admin_user)
    assert result.api_keys == ["key"]

    monkeypatch.setattr(users_router.auth_service, "update_user", lambda *_args: user_obj)
    result = await users_router.update_current_user_info(UserUpdate(role=Role.ADMIN, is_active=False), admin_user)
    assert result.api_keys == ["key"]

    monkeypatch.setattr(users_router.auth_service, "list_users", lambda *_args, **_kwargs: [user_obj])
    users = await users_router.list_users(10, 0, admin_user)
    assert users == [response_obj]

    sent = []
    monkeypatch.setattr(users_router.auth_service, "create_user", lambda *_args: user_obj)

    async def fake_welcome_email(**kwargs):
        sent.append(kwargs)
        return True

    monkeypatch.setattr(users_router.notification_service, "send_user_welcome_email", fake_welcome_email)
    monkeypatch.setattr(users_router, "invalidate_grafana_proxy_auth_cache", lambda: sent.append({"cache": True}))
    created = await users_router.create_user(UserCreate(username="user2", email="u2@example.com", password="password123"), admin_user)
    assert created is response_obj
    assert any("recipient_email" in entry for entry in sent)

    limited_user = _current_user(is_superuser=False, permissions=[Permission.MANAGE_TENANTS.value], role=Role.USER)
    with pytest.raises(HTTPException) as exc:
        await users_router.update_user("u2", UserUpdate(full_name="Renamed"), limited_user)
    assert exc.value.status_code == 403

    non_admin = _current_user(is_superuser=False, permissions=[Permission.UPDATE_USERS.value], role=Role.USER)
    with pytest.raises(HTTPException) as exc:
        await users_router.update_user("u2", UserUpdate(role=Role.ADMIN), non_admin)
    assert exc.value.status_code == 403

    monkeypatch.setattr(users_router.auth_service, "update_user", lambda *_args: None)
    with pytest.raises(HTTPException) as exc:
        await users_router.update_user("u2", UserUpdate(full_name="Renamed"), admin_user)
    assert exc.value.status_code == 404

    monkeypatch.setattr(users_router.auth_service, "update_user", lambda *_args: user_obj)
    assert await users_router.update_user("u2", UserUpdate(group_ids=["g1"]), admin_user) is response_obj

    monkeypatch.setattr(
        users_router.auth_service,
        "update_user",
        lambda *_args: (_ for _ in ()).throw(HTTPException(status_code=403, detail="Users cannot change their own role, tenant scope, or group memberships")),
    )
    with pytest.raises(HTTPException) as exc:
        await users_router.update_user("u1", UserUpdate(role=Role.USER), admin_user)
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await users_router.update_user_password("u2", UserPasswordUpdate(current_password="oldpass123", new_password="newpass123"), _current_user(is_superuser=False, permissions=[]))
    assert exc.value.status_code == 403

    monkeypatch.setattr(users_router.auth_service, "update_password", lambda *_args: False)
    with pytest.raises(HTTPException) as exc:
        await users_router.update_user_password("u1", UserPasswordUpdate(current_password="oldpass123", new_password="newpass123"), admin_user)
    assert exc.value.status_code == 400

    monkeypatch.setattr(users_router.auth_service, "update_password", lambda *_args: True)
    assert await users_router.update_user_password("u1", UserPasswordUpdate(current_password="oldpass123", new_password="newpass123"), admin_user) == {
        "message": "Password updated successfully",
    }

    no_manage = _current_user(is_superuser=False, permissions=[], role=Role.USER)
    with pytest.raises(HTTPException) as exc:
        await users_router.reset_user_password_temp("u2", no_manage)
    assert exc.value.status_code == 403

    monkeypatch.setattr(users_router.auth_service, "get_user_by_id_in_tenant", lambda *_args: None)
    with pytest.raises(HTTPException) as exc:
        await users_router.reset_user_password_temp("u2", admin_user)
    assert exc.value.status_code == 404

    monkeypatch.setattr(users_router.auth_service, "get_user_by_id_in_tenant", lambda *_args: SimpleNamespace(username="target", role=Role.ADMIN))
    with pytest.raises(HTTPException) as exc:
        await users_router.reset_user_password_temp("u2", admin_user)
    assert exc.value.status_code == 403

    monkeypatch.setattr(users_router.auth_service, "get_user_by_id_in_tenant", lambda *_args: SimpleNamespace(username="target", role=Role.USER))
    monkeypatch.setattr(
        users_router.auth_service,
        "reset_user_password_temp",
        lambda *_args: {"temporary_password": "Temp1234", "target_email": "t@example.com", "target_username": "target"},
    )

    async def fake_temp_email(**kwargs):
        return kwargs["recipient_email"] == "t@example.com"

    monkeypatch.setattr(users_router.notification_service, "send_temporary_password_email", fake_temp_email)
    reset = await users_router.reset_user_password_temp("u2", admin_user)
    assert reset.temporary_password == "Temp1234"
    assert reset.email_sent is True

    with pytest.raises(HTTPException) as exc:
        await users_router.delete_user("u2", _current_user(is_superuser=False, permissions=[], role=Role.USER))
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await users_router.delete_user("u1", admin_user)
    assert exc.value.status_code == 400

    monkeypatch.setattr(users_router.auth_service, "get_user_by_id_in_tenant", lambda *_args: SimpleNamespace(role=Role.ADMIN))
    with pytest.raises(HTTPException) as exc:
        await users_router.delete_user("u2", admin_user)
    assert exc.value.status_code == 403

    monkeypatch.setattr(users_router.auth_service, "get_user_by_id_in_tenant", lambda *_args: SimpleNamespace(role=Role.USER))
    monkeypatch.setattr(users_router.auth_service, "delete_user", lambda *_args: False)
    with pytest.raises(HTTPException) as exc:
        await users_router.delete_user("u2", admin_user)
    assert exc.value.status_code == 404

    monkeypatch.setattr(users_router.auth_service, "delete_user", lambda *_args: True)
    assert await users_router.delete_user("u2", admin_user) == {"message": "User deleted successfully"}

    monkeypatch.setattr(users_router.auth_service, "update_user_permissions", lambda *_args: False)
    with pytest.raises(HTTPException) as exc:
        await users_router.update_user_permissions("u2", ["read:users"], admin_user)
    assert exc.value.status_code == 404

    monkeypatch.setattr(users_router.auth_service, "update_user_permissions", lambda *_args: True)
    assert await users_router.update_user_permissions("u2", ["read:users"], admin_user) == {
        "success": True,
        "permissions": ["read:users"],
    }

    monkeypatch.setattr(
        users_router.auth_service,
        "update_user_permissions",
        lambda *_args: (_ for _ in ()).throw(HTTPException(status_code=403, detail="Users cannot change their own permissions")),
    )
    with pytest.raises(HTTPException) as exc:
        await users_router.update_user_permissions("u1", ["read:users"], admin_user)
    assert exc.value.status_code == 403

    monkeypatch.setattr(users_router.auth_service, "list_all_permissions", lambda: [{"name": "read:users"}, {"name": "delete:users"}])
    assert await users_router.list_all_permissions(admin_user) == [{"name": "read:users"}, {"name": "delete:users"}]
    filtered = await users_router.list_all_permissions(_current_user(is_superuser=False, permissions=["read:users"]))
    assert filtered == [{"name": "read:users"}]

    defaults = await users_router.list_role_defaults(admin_user)
    assert Role.ADMIN.value in defaults
    filtered_defaults = await users_router.list_role_defaults(_current_user(is_superuser=False, permissions=[Permission.READ_USERS.value]))
    assert all(Permission.READ_USERS.value in perms or not perms for perms in filtered_defaults.values())

    group_obj = SimpleNamespace(id="g1")
    monkeypatch.setattr(groups_router.auth_service, "list_groups", lambda *_args: [group_obj])
    assert await groups_router.list_groups(admin_user) == [group_obj]

    monkeypatch.setattr(groups_router.auth_service, "create_group", lambda *_args: group_obj)
    assert await groups_router.create_group(GroupCreate(name="grp"), admin_user) is group_obj

    monkeypatch.setattr(groups_router.auth_service, "get_group", lambda *_args: None)
    with pytest.raises(HTTPException) as exc:
        await groups_router.get_group("g1", admin_user)
    assert exc.value.status_code == 404

    monkeypatch.setattr(groups_router.auth_service, "get_group", lambda *_args: group_obj)
    assert await groups_router.get_group("g1", admin_user) is group_obj

    monkeypatch.setattr(groups_router.auth_service, "update_group", lambda *_args: None)
    with pytest.raises(HTTPException) as exc:
        await groups_router.update_group("g1", GroupUpdate(name="new"), admin_user)
    assert exc.value.status_code == 404

    monkeypatch.setattr(groups_router.auth_service, "update_group", lambda *_args: group_obj)
    assert await groups_router.update_group("g1", GroupUpdate(name="new"), admin_user) is group_obj

    monkeypatch.setattr(groups_router.auth_service, "delete_group", lambda *_args: False)
    with pytest.raises(HTTPException) as exc:
        await groups_router.delete_group("g1", admin_user)
    assert exc.value.status_code == 404

    monkeypatch.setattr(groups_router.auth_service, "delete_group", lambda *_args: True)
    assert await groups_router.delete_group("g1", admin_user) == {"message": "Group deleted successfully"}

    monkeypatch.setattr(groups_router.auth_service, "update_group_permissions", lambda *_args: False)
    with pytest.raises(HTTPException) as exc:
        await groups_router.update_group_permissions("g1", ["read:users"], admin_user)
    assert exc.value.status_code == 404

    monkeypatch.setattr(groups_router.auth_service, "update_group_permissions", lambda *_args: True)
    assert await groups_router.update_group_permissions("g1", ["read:users"], admin_user) == {
        "success": True,
        "permissions": ["read:users"],
    }

    monkeypatch.setattr(groups_router.auth_service, "update_group_members", lambda *_args: False)
    with pytest.raises(HTTPException) as exc:
        await groups_router.update_group_members("g1", GroupMembersUpdate(user_ids=["u1"]), admin_user)
    assert exc.value.status_code == 404

    monkeypatch.setattr(groups_router.auth_service, "update_group_members", lambda *_args: True)
    assert await groups_router.update_group_members("g1", GroupMembersUpdate(user_ids=["u1"]), admin_user) == {
        "success": True,
        "user_ids": ["u1"],
    }

    monkeypatch.setattr(mfa_router.auth_service, "enroll_totp", lambda *_args: {"secret": "abc", "otpauth_url": "otpauth://url"})
    enrolled = await mfa_router.mfa_enroll(admin_user)
    assert enrolled.secret == "abc"

    monkeypatch.setattr(mfa_router.auth_service, "enroll_totp", lambda *_args: (_ for _ in ()).throw(ValueError("bad")))
    with pytest.raises(HTTPException) as exc:
        await mfa_router.mfa_enroll(admin_user)
    assert exc.value.status_code == 400

    monkeypatch.setattr(mfa_router.auth_service, "verify_enable_totp", lambda *_args: ["rc1", "rc2"])
    verified = await mfa_router.mfa_verify(MfaVerifyRequest(code="123456"), admin_user)
    assert verified.recovery_codes == ["rc1", "rc2"]

    monkeypatch.setattr(mfa_router.auth_service, "verify_enable_totp", lambda *_args: (_ for _ in ()).throw(ValueError("not enrolled")))
    with pytest.raises(HTTPException) as exc:
        await mfa_router.mfa_verify(MfaVerifyRequest(code="123456"), admin_user)
    assert exc.value.detail == "TOTP not enrolled for user"

    monkeypatch.setattr(mfa_router.auth_service, "verify_enable_totp", lambda *_args: (_ for _ in ()).throw(ValueError("Invalid TOTP code")))
    with pytest.raises(HTTPException) as exc:
        await mfa_router.mfa_verify(MfaVerifyRequest(code="123456"), admin_user)
    assert exc.value.detail == "Invalid TOTP code"

    monkeypatch.setattr(mfa_router.auth_service, "disable_totp", lambda *_args, **_kwargs: False)
    with pytest.raises(HTTPException) as exc:
        await mfa_router.mfa_disable(MfaDisableRequest(current_password="password123"), admin_user)
    assert exc.value.status_code == 400

    monkeypatch.setattr(mfa_router.auth_service, "disable_totp", lambda *_args, **_kwargs: True)
    assert await mfa_router.mfa_disable(MfaDisableRequest(code="123456"), admin_user) == {"message": "MFA disabled"}

    monkeypatch.setattr(mfa_router.auth_service, "reset_totp", lambda *_args: False)
    with pytest.raises(HTTPException) as exc:
        await mfa_router.admin_reset_user_mfa("u2", admin_user)
    assert exc.value.status_code == 404

    monkeypatch.setattr(mfa_router.auth_service, "reset_totp", lambda *_args: True)
    assert await mfa_router.admin_reset_user_mfa("u2", admin_user) == {"message": "User MFA reset"}
