"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from routers.access.auth_router import authentication as auth_routes

from .helpers import WorkflowState, patch_auth_service


def test_registration_login_password_and_mfa_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)

    class FakeQuery:
        def filter_by(self, **_kwargs):
            return self

        def first(self):
            return SimpleNamespace(id=state.tenant_id)

    class FakeDB:
        def query(self, *_args):
            return FakeQuery()

    class FakeCtx:
        def __enter__(self):
            return FakeDB()

        def __exit__(self, exc_type, exc, tb):
            return False

    async def _send_welcome(**kwargs):
        del kwargs
        return True

    monkeypatch.setattr(auth_routes, "get_db_session", lambda: FakeCtx())
    monkeypatch.setattr(auth_routes.notification_service, "send_user_welcome_email", _send_welcome)

    mode_response = client.get("/api/auth/mode")
    assert mode_response.status_code == 200
    assert mode_response.json()["registration_enabled"] is True

    oidc_authorize_disabled = client.post(
        "/api/auth/oidc/authorize-url",
        json={"redirect_uri": "https://app.example.com/callback", "state": "state-1"},
    )
    assert oidc_authorize_disabled.status_code == 400

    oidc_exchange_disabled = client.post(
        "/api/auth/oidc/exchange",
        json={"code": "code-1", "redirect_uri": "https://app.example.com/callback"},
    )
    assert oidc_exchange_disabled.status_code == 400

    register_response = client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "password123",
            "full_name": "Alice Example",
        },
    )
    assert register_response.status_code == 200
    alice_id = register_response.json()["id"]

    login_response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "password123"},
    )
    assert login_response.status_code == 200
    alice_token = login_response.json()["access_token"]

    me_response = client.get("/api/auth/me", headers=state.auth_header(alice_token))
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "alice"

    update_me_response = client.put(
        "/api/auth/me",
        headers=state.auth_header(alice_token),
        json={"full_name": "Alice Updated", "email": "alice.updated@example.com"},
    )
    assert update_me_response.status_code == 200
    assert update_me_response.json()["full_name"] == "Alice Updated"

    change_password_response = client.put(
        f"/api/auth/users/{alice_id}/password",
        headers=state.auth_header(alice_token),
        json={"current_password": "password123", "new_password": "new-password-123"},
    )
    assert change_password_response.status_code == 200

    old_login_response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "password123"},
    )
    assert old_login_response.status_code == 401

    new_login_response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "new-password-123"},
    )
    assert new_login_response.status_code == 200
    refreshed_token = new_login_response.json()["access_token"]

    enroll_response = client.post(
        "/api/auth/mfa/enroll",
        headers=state.auth_header(refreshed_token),
    )
    assert enroll_response.status_code == 200

    verify_response = client.post(
        "/api/auth/mfa/verify",
        headers=state.auth_header(refreshed_token),
        json={"code": "123456"},
    )
    assert verify_response.status_code == 200

    login_requires_mfa = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "new-password-123"},
    )
    assert login_requires_mfa.status_code == 401
    assert login_requires_mfa.json()["detail"] == "MFA required"

    login_with_mfa = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "new-password-123", "mfa_code": "123456"},
    )
    assert login_with_mfa.status_code == 200
    mfa_token = login_with_mfa.json()["access_token"]

    disable_mfa_response = client.post(
        "/api/auth/mfa/disable",
        headers=state.auth_header(mfa_token),
        json={"current_password": "new-password-123", "code": "123456"},
    )
    assert disable_mfa_response.status_code == 200

    logout_response = client.post("/api/auth/logout", headers=state.auth_header(mfa_token))
    assert logout_response.status_code == 200


def test_user_group_role_and_permission_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    admin_headers = state.auth_header("token-u-admin")

    viewer_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "viewer1", "email": "viewer1@example.com", "password": "password123", "role": "viewer"},
    )
    assert viewer_response.status_code == 200
    viewer_id = viewer_response.json()["id"]

    worker_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "worker1", "email": "worker1@example.com", "password": "password123", "role": "user"},
    )
    assert worker_response.status_code == 200
    worker_id = worker_response.json()["id"]

    list_users_response = client.get("/api/auth/users", headers=admin_headers)
    assert list_users_response.status_code == 200
    assert {item["username"] for item in list_users_response.json()} >= {"admin", "viewer1", "worker1"}

    permissions_response = client.get("/api/auth/permissions", headers=admin_headers)
    assert permissions_response.status_code == 200
    assert any(item["name"] == "create:groups" for item in permissions_response.json())

    role_defaults_response = client.get("/api/auth/role-defaults", headers=admin_headers)
    assert role_defaults_response.status_code == 200
    assert "admin" in role_defaults_response.json()

    update_permissions_response = client.put(
        f"/api/auth/users/{worker_id}/permissions",
        headers=admin_headers,
        json=["create:groups", "manage:groups", "update:group_members", "read:groups", "read:users"],
    )
    assert update_permissions_response.status_code == 200

    update_role_response = client.put(
        f"/api/auth/users/{viewer_id}",
        headers=admin_headers,
        json={"username": "viewer2", "role": "user"},
    )
    assert update_role_response.status_code == 200
    assert update_role_response.json()["username"] == "viewer2"

    worker_group_response = client.post(
        "/api/auth/groups",
        headers=state.auth_header(f"token-{worker_id}"),
        json={"name": "ops-group", "description": "Ops team"},
    )
    assert worker_group_response.status_code == 200
    group_id = worker_group_response.json()["id"]

    get_group_response = client.get(
        f"/api/auth/groups/{group_id}",
        headers=state.auth_header(f"token-{worker_id}"),
    )
    assert get_group_response.status_code == 200

    update_group_response = client.put(
        f"/api/auth/groups/{group_id}",
        headers=state.auth_header(f"token-{worker_id}"),
        json={"description": "Ops team updated"},
    )
    assert update_group_response.status_code == 200

    update_group_permissions_response = client.put(
        f"/api/auth/groups/{group_id}/permissions",
        headers=state.auth_header(f"token-{worker_id}"),
        json=["read:logs", "read:traces"],
    )
    assert update_group_permissions_response.status_code == 200

    update_group_members_response = client.put(
        f"/api/auth/groups/{group_id}/members",
        headers=state.auth_header(f"token-{worker_id}"),
        json={"user_ids": [viewer_id]},
    )
    assert update_group_members_response.status_code == 200

    list_groups_response = client.get("/api/auth/groups", headers=state.auth_header(f"token-{worker_id}"))
    assert list_groups_response.status_code == 200
    assert list_groups_response.json()[0]["id"] == group_id

    temp_password_response = client.post(
        f"/api/auth/users/{viewer_id}/password/reset-temp",
        headers=admin_headers,
    )
    assert temp_password_response.status_code == 200
    assert temp_password_response.json()["temporary_password"] == "Temp-Password-123"

    reset_mfa_response = client.post(
        f"/api/auth/users/{viewer_id}/mfa/reset",
        headers=admin_headers,
    )
    assert reset_mfa_response.status_code == 200

    delete_group_response = client.delete(
        f"/api/auth/groups/{group_id}",
        headers=state.auth_header(f"token-{worker_id}"),
    )
    assert delete_group_response.status_code == 200

    delete_user_response = client.delete(f"/api/auth/users/{viewer_id}", headers=admin_headers)
    assert delete_user_response.status_code == 200


def test_api_key_sharing_and_visibility_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)
    admin_headers = state.auth_header("token-u-admin")

    group_response = client.post(
        "/api/auth/groups",
        headers=admin_headers,
        json={"name": "share-group", "description": "Shared API keys"},
    )
    assert group_response.status_code == 200
    group_id = group_response.json()["id"]

    recipient_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "recipient", "email": "recipient@example.com", "password": "password123"},
    )
    recipient_id = recipient_response.json()["id"]

    member_response = client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "member", "email": "member@example.com", "password": "password123"},
    )
    member_id = member_response.json()["id"]

    client.put(
        f"/api/auth/groups/{group_id}/members",
        headers=admin_headers,
        json={"user_ids": [member_id]},
    )

    created_key_response = client.post(
        "/api/auth/api-keys",
        headers=admin_headers,
        json={"name": "primary-scope", "key": "scope-primary"},
    )
    assert created_key_response.status_code == 200
    key_id = created_key_response.json()["id"]

    list_keys_response = client.get("/api/auth/api-keys", headers=admin_headers)
    assert list_keys_response.status_code == 200
    assert list_keys_response.json()[0]["id"] == key_id

    update_key_response = client.patch(
        f"/api/auth/api-keys/{key_id}",
        headers=admin_headers,
        json={"name": "primary-renamed", "is_enabled": True},
    )
    assert update_key_response.status_code == 200
    assert update_key_response.json()["name"] == "primary-renamed"

    regenerate_response = client.post(
        f"/api/auth/api-keys/{key_id}/otlp-token/regenerate",
        headers=admin_headers,
    )
    assert regenerate_response.status_code == 200
    assert regenerate_response.json()["otlp_token"] == f"regen-{key_id}"

    share_response = client.put(
        f"/api/auth/api-keys/{key_id}/shares",
        headers=admin_headers,
        json={"user_ids": [recipient_id], "group_ids": [group_id]},
    )
    assert share_response.status_code == 200
    assert {item["user_id"] for item in share_response.json()} == {recipient_id}

    recipient_keys_response = client.get(
        "/api/auth/api-keys",
        headers=state.auth_header(f"token-{recipient_id}"),
    )
    assert recipient_keys_response.status_code == 200
    assert recipient_keys_response.json()[0]["is_shared"] is True

    member_keys_response = client.get(
        "/api/auth/api-keys",
        headers=state.auth_header(f"token-{member_id}"),
    )
    assert member_keys_response.status_code == 200
    assert member_keys_response.json()[0]["is_shared"] is True

    hide_shared_response = client.post(
        f"/api/auth/api-keys/{key_id}/hide",
        headers=state.auth_header(f"token-{recipient_id}"),
        json={"hidden": True},
    )
    assert hide_shared_response.status_code == 200

    hidden_default_response = client.get(
        "/api/auth/api-keys",
        headers=state.auth_header(f"token-{recipient_id}"),
    )
    assert hidden_default_response.status_code == 200
    assert hidden_default_response.json() == []

    hidden_explicit_response = client.get(
        "/api/auth/api-keys?show_hidden=true",
        headers=state.auth_header(f"token-{recipient_id}"),
    )
    assert hidden_explicit_response.status_code == 200
    assert hidden_explicit_response.json()[0]["is_hidden"] is True

    shares_list_response = client.get(f"/api/auth/api-keys/{key_id}/shares", headers=admin_headers)
    assert shares_list_response.status_code == 200
    assert shares_list_response.json()[0]["user_id"] == recipient_id

    remove_share_response = client.delete(
        f"/api/auth/api-keys/{key_id}/shares/{recipient_id}",
        headers=admin_headers,
    )
    assert remove_share_response.status_code == 200

    recipient_keys_after_removal = client.get(
        "/api/auth/api-keys",
        headers=state.auth_header(f"token-{recipient_id}"),
    )
    assert recipient_keys_after_removal.status_code == 200
    assert recipient_keys_after_removal.json() == []

    delete_key_response = client.delete(f"/api/auth/api-keys/{key_id}", headers=admin_headers)
    assert delete_key_response.status_code == 200