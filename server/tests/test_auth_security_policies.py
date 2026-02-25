from tests._env import ensure_test_env

ensure_test_env()

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from middleware import dependencies
from models.access.auth_models import Role, TokenData
from models.access.user_models import UserUpdate
from routers.access import auth_router


def _token_data(*, role: Role = Role.USER, perms=None) -> TokenData:
    return TokenData(
        user_id="u1",
        username="user-1",
        tenant_id="tenant-a",
        org_id="tenant-a",
        role=role,
        is_superuser=False,
        permissions=list(perms or []),
        group_ids=[],
        iat=int(datetime.now(timezone.utc).timestamp()),
        is_mfa_setup=False,
    )


def _request_with_scope_header(org_id: str) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/",
        "headers": [(b"x-scope-orgid", org_id.encode("utf-8"))],
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "query_string": b"",
    }
    return Request(scope)


def test_session_revocation_requires_iat_when_invalid_before_set():
    user = SimpleNamespace(session_invalid_before=datetime.now(timezone.utc))
    token_data = _token_data()
    token_data.iat = None
    with pytest.raises(HTTPException) as exc:
        dependencies._enforce_session_revocation(user, token_data)
    assert exc.value.status_code == 401


def test_session_revocation_rejects_old_token():
    invalid_before = datetime.now(timezone.utc)
    old_iat = int((invalid_before - timedelta(minutes=1)).timestamp())
    user = SimpleNamespace(session_invalid_before=invalid_before)
    token_data = _token_data()
    token_data.iat = old_iat
    with pytest.raises(HTTPException) as exc:
        dependencies._enforce_session_revocation(user, token_data)
    assert exc.value.status_code == 401


def test_session_revocation_allows_newer_token():
    invalid_before = datetime.now(timezone.utc)
    new_iat = int((invalid_before + timedelta(minutes=1)).timestamp())
    user = SimpleNamespace(session_invalid_before=invalid_before)
    token_data = _token_data()
    token_data.iat = new_iat
    dependencies._enforce_session_revocation(user, token_data)


@pytest.mark.asyncio
async def test_reset_temp_password_blocks_admin_target(monkeypatch):
    async def _run_sync(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(auth_router, "run_in_threadpool", _run_sync)
    monkeypatch.setattr(
        auth_router.auth_service,
        "get_user_by_id_in_tenant",
        lambda _uid, _tenant_id: SimpleNamespace(id="u2", username="admin-user", role=Role.ADMIN),
    )

    current_user = _token_data(perms=["manage:users"])
    with pytest.raises(HTTPException) as exc:
        await auth_router.reset_user_password_temp("u2", current_user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_user_requires_admin_role():
    current_user = _token_data(perms=["manage:users"])
    with pytest.raises(HTTPException) as exc:
        await auth_router.delete_user("u2", current_user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_manage_tenants_update_restricted_to_active_flag():
    current_user = _token_data(perms=["manage:tenants"])
    with pytest.raises(HTTPException) as exc:
        await auth_router.update_user("u2", UserUpdate(email="new@example.com"), current_user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_change_role_org_or_groups():
    current_user = _token_data(role=Role.USER, perms=["update:users"])
    with pytest.raises(HTTPException) as exc:
        await auth_router.update_user("u2", UserUpdate(role=Role.ADMIN), current_user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_manage_tenants_cannot_reset_temp_password():
    current_user = _token_data(perms=["manage:tenants"])
    with pytest.raises(HTTPException) as exc:
        await auth_router.reset_user_password_temp("u2", current_user)
    assert exc.value.status_code == 403


def test_resolve_tenant_id_rejects_scope_conflict(monkeypatch):
    req = _request_with_scope_header("org-shared")
    current_user = _token_data()
    monkeypatch.setattr(
        dependencies,
        "_load_allowed_org_ids_for_user",
        lambda *, current_user, default_org_id: {"tenant-a", "org-shared"},
    )
    monkeypatch.setattr(
        dependencies,
        "_scope_exists_in_other_tenants",
        lambda *, org_id, tenant_id: True,
    )
    with pytest.raises(HTTPException) as exc:
        dependencies.resolve_tenant_id(req, current_user)
    assert exc.value.status_code == 403


def test_resolve_tenant_id_allows_non_conflicting_allowed_scope(monkeypatch):
    req = _request_with_scope_header("org-owned")
    current_user = _token_data()
    monkeypatch.setattr(
        dependencies,
        "_load_allowed_org_ids_for_user",
        lambda *, current_user, default_org_id: {"tenant-a", "org-owned"},
    )
    monkeypatch.setattr(
        dependencies,
        "_scope_exists_in_other_tenants",
        lambda *, org_id, tenant_id: False,
    )
    assert dependencies.resolve_tenant_id(req, current_user) == "org-owned"
