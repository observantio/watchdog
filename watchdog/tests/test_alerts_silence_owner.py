"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from tests._env import ensure_test_env

ensure_test_env()

import pytest
from fastapi import HTTPException

from models.access.auth_models import Role, TokenData
from services.alerts.helpers import assert_silence_owner


def _user() -> TokenData:
    return TokenData(
        user_id="u-123",
        username="alice",
        tenant_id="t-1",
        org_id="t-1",
        role=Role.USER,
        permissions=["delete:silences"],
        group_ids=[],
        is_superuser=False,
        is_mfa_setup=False,
    )


def test_assert_silence_owner_allows_user_id_match():
    assert_silence_owner(_user(), {"createdBy": "u-123"})


def test_assert_silence_owner_rejects_username_match():
    with pytest.raises(HTTPException) as exc:
        assert_silence_owner(_user(), {"createdBy": "alice"})
    assert exc.value.status_code == 403


def test_assert_silence_owner_rejects_other_owner():
    with pytest.raises(HTTPException) as exc:
        assert_silence_owner(_user(), {"createdBy": "bob"})
    assert exc.value.status_code == 403
    assert "You can only update or delete silences" in str(exc.value.detail)
