"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
"""

import types
import os

from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/observantio_test")
os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "False")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

import middleware.dependencies as deps
from models.access.auth_models import Role, TokenData


def _request() -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/api/alertmanager/rules",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "query_string": b"",
    }
    return Request(scope)


def test_get_current_user_refreshes_group_ids_from_live_user(monkeypatch):
    token_data = TokenData(
        user_id="u1",
        username="user1",
        tenant_id="t1",
        org_id="org-a",
        role=Role.USER,
        is_superuser=False,
        permissions=["read:rules"],
        group_ids=["stale-group"],
    )

    live_user = types.SimpleNamespace(
        id="u1",
        tenant_id="t1",
        is_active=True,
        org_id="org-a",
        group_ids=["g1", "g2"],
        session_invalid_before=None,
    )

    auth_stub = types.SimpleNamespace(
        decode_token=lambda token: token_data,
        get_user_by_id=lambda user_id: live_user,
        get_user_permissions=lambda user: ["read:rules"],
    )

    monkeypatch.setattr(deps, "auth_service", auth_stub)
    monkeypatch.setattr(deps, "enforce_rate_limit", lambda **kwargs: None)

    resolved = deps.get_current_user(
        _request(),
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
    )

    assert resolved.group_ids == ["g1", "g2"]
