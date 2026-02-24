from tests._env import ensure_test_env

ensure_test_env()

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

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
        "get_user_by_id",
        lambda _uid: SimpleNamespace(id="u2", username="admin-user", role=Role.ADMIN),
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

