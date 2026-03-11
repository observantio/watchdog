"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Role, TokenData
from models.observability.grafana_request_models import GrafanaDashboardPayloadRequest
from routers.observability.grafana_router import shared as shared_router
from services.grafana import route_payloads, shared_ops


def _user(**kwargs) -> TokenData:
    payload = {
        "user_id": "u1",
        "username": "user",
        "tenant_id": "tenant",
        "org_id": "org",
        "role": Role.USER,
        "permissions": [],
        "group_ids": ["g1", "g2"],
        "is_superuser": False,
    }
    payload.update(kwargs)
    return TokenData(**payload)


def test_route_payload_helpers_cover_coercion_and_validation():
    current_user = _user()
    assert route_payloads.user_group_ids(current_user) == ["g1", "g2"]
    assert route_payloads.is_admin_user(current_user) is False
    assert route_payloads.is_admin_user(_user(role=Role.ADMIN)) is True
    assert route_payloads.is_admin_user(_user(role="admin")) is True
    assert route_payloads.is_admin_user(_user(is_superuser=True)) is True

    route_payloads.validate_visibility(None)
    route_payloads.validate_visibility("private")
    with pytest.raises(ValueError):
        route_payloads.validate_visibility("public")

    with pytest.raises(ValueError):
        route_payloads._ensure_dict([])
    assert route_payloads._coerce_int(None, 9) == 9
    assert route_payloads._coerce_int(True) == 1
    assert route_payloads._coerce_int(4.7) == 4
    assert route_payloads._coerce_int("7") == 7
    assert route_payloads._coerce_int("bad", 3) == 3
    assert route_payloads._coerce_int(object(), 4) == 4
    assert route_payloads._coerce_optional_str("x") == "x"
    assert route_payloads._coerce_optional_str(1) is None
    assert route_payloads._coerce_bool(2) is True
    assert route_payloads._coerce_bool("yes") is True
    assert route_payloads._coerce_bool("off", True) is False
    assert route_payloads._coerce_bool(object(), True) is True

    payload = {
        "dashboard": {"title": "Ops", "uid": "dash-1"},
        "folderId": "12",
        "overwrite": "true",
        "message": "save",
    }
    create_model = route_payloads.parse_dashboard_create_payload(payload)
    update_model = route_payloads.parse_dashboard_update_payload(payload)
    assert create_model.folder_id == 12
    assert create_model.overwrite is True
    assert update_model.message == "save"


def test_shared_router_and_shared_ops_helpers_cover_edge_branches(monkeypatch):
    current_user = _user(role=Role.ADMIN)
    monkeypatch.setattr(shared_router, "user_group_ids", lambda _user: ["g1"])
    monkeypatch.setattr(shared_router, "is_admin_user", lambda _user: True)
    assert shared_router.scope_context(current_user) == ("u1", "tenant", ["g1"], True)
    assert shared_router.hidden_toggle_context(current_user) == ("u1", "tenant")

    payload = GrafanaDashboardPayloadRequest.model_validate({"dashboard": {"uid": "dash-1"}, "folderId": 5})
    assert shared_router.dashboard_payload(payload) == {"dashboard": {"uid": "dash-1"}, "folderId": 5}
    assert shared_router.dashboard_uid({"dashboard": {"uid": "dash-1"}}) == "dash-1"
    assert shared_router.dashboard_uid({"dashboard": []}) == ""

    assert shared_ops.group_id_strs([1, "g2"]) == ["1", "g2"]
    assert shared_ops.update_hidden_members(["u2"], "u1", True) == ["u2", "u1"]
    assert shared_ops.update_hidden_members(["u1", "u2"], "u1", False) == ["u2"]

    events = []

    class FakeDB:
        def commit(self):
            events.append("commit")

        def rollback(self):
            events.append("rollback")

    shared_ops.commit_session(FakeDB())
    assert events == ["commit"]

    class BrokenDB:
        def commit(self):
            raise RuntimeError("boom")

        def rollback(self):
            events.append("rollback")

    with pytest.raises(RuntimeError):
        shared_ops.commit_session(BrokenDB())
    assert events[-1] == "rollback"