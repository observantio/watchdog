from tests._env import ensure_test_env

ensure_test_env()

import pytest
from fastapi import HTTPException

from models.access.auth_models import Role, TokenData
from routers.observability import alertmanager_router


def _user(*, user_id: str = "u1", groups=None, is_superuser: bool = False) -> TokenData:
    return TokenData(
        user_id=user_id,
        username="user-1",
        tenant_id="tenant-a",
        org_id="tenant-a",
        role=Role.USER,
        permissions=[
            "read:silences",
            "create:silences",
            "update:silences",
            "delete:silences",
            "write:alerts",
        ],
        group_ids=list(groups or []),
        is_superuser=is_superuser,
        is_mfa_setup=False,
    )


def test_validate_silence_payload_rejects_non_member_group():
    with pytest.raises(HTTPException) as exc:
        alertmanager_router._validate_and_normalize_silence_payload(
            {
                "visibility": "group",
                "sharedGroupIds": ["g2"],
            },
            _user(groups=["g1"]),
        )
    assert exc.value.status_code == 403
    assert "not a member" in str(exc.value.detail)


def test_validate_silence_payload_group_requires_groups():
    with pytest.raises(HTTPException) as exc:
        alertmanager_router._validate_and_normalize_silence_payload(
            {
                "visibility": "group",
                "sharedGroupIds": [],
            },
            _user(groups=["g1"]),
        )
    assert exc.value.status_code == 400
    assert "At least one group" in str(exc.value.detail)


def test_validate_silence_payload_non_group_clears_group_ids():
    payload = alertmanager_router._validate_and_normalize_silence_payload(
        {
            "visibility": "private",
            "sharedGroupIds": ["g1", "g2"],
        },
        _user(groups=["g1", "g2"]),
    )
    assert payload["sharedGroupIds"] == []
    assert payload["shared_group_ids"] == []


def test_assert_silence_owner_blocks_other_user():
    with pytest.raises(HTTPException) as exc:
        alertmanager_router._assert_silence_owner(
            _user(user_id="u1"),
            {"id": "s1", "created_by": "u2"},
        )
    assert exc.value.status_code == 403
    assert "only update or delete silences that you created" in str(exc.value.detail)


def test_assert_silence_owner_blocks_missing_owner():
    with pytest.raises(HTTPException) as exc:
        alertmanager_router._assert_silence_owner(
            _user(user_id="u1"),
            {"id": "s1", "visibility": "private"},
        )
    assert exc.value.status_code == 403
    assert "ownership metadata is missing" in str(exc.value.detail)


def test_assert_silence_owner_allows_creator():
    alertmanager_router._assert_silence_owner(
        _user(user_id="u1"),
        {"id": "s1", "created_by": "u1"},
    )


def test_unknown_alertmanager_route_fails_closed():
    required = alertmanager_router._required_permissions("totally/unknown/path", "POST")
    assert required is None
