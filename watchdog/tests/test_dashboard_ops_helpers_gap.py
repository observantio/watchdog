"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests._env import ensure_test_env

ensure_test_env()

from db_models import Base, GrafanaDashboard, Group, Tenant, User
from services.grafana import dashboard_ops


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db):
    db.add(Tenant(id="t1", name="tenant-1", display_name="Tenant 1"))
    owner = User(
        id="u1",
        tenant_id="t1",
        username="owner",
        email="owner@example.com",
        hashed_password="x",
        org_id="org-1",
        is_active=True,
    )
    viewer = User(
        id="u2",
        tenant_id="t1",
        username="viewer",
        email="viewer@example.com",
        hashed_password="x",
        org_id="org-2",
        is_active=True,
    )
    g1 = Group(id="g1", tenant_id="t1", name="Team-1", is_active=True)
    g1.members.append(viewer)
    db.add_all([owner, viewer, g1])
    db.commit()
    return owner, viewer, g1


def test_dashboard_helper_json_and_folder_id_parsers():
    assert dashboard_ops._json_dict({"a": 1}) == {"a": 1}
    assert dashboard_ops._json_dict([]) == {}
    assert dashboard_ops._json_dict_list([{"a": 1}, 1, "x"]) == [{"a": 1}]
    assert dashboard_ops._json_dict_list({"a": 1}) == []
    assert dashboard_ops._cap(10000, -2)[0] >= 1
    assert dashboard_ops._normalize_title(" CPU ") == "cpu"

    assert dashboard_ops._is_general_folder_id(0) is True
    assert dashboard_ops._is_general_folder_id("0") is True
    assert dashboard_ops._is_general_folder_id(-1) is True
    assert dashboard_ops._is_general_folder_id("abc") is False

    assert dashboard_ops._is_non_general_folder_id(1) is True
    assert dashboard_ops._is_non_general_folder_id("2") is True
    assert dashboard_ops._is_non_general_folder_id(0) is False
    assert dashboard_ops._is_non_general_folder_id(None) is False


def test_dashboard_has_datasource_detection_paths():
    templating = {"templating": {"list": [{"type": "datasource", "current": {"value": "ds-1"}}]}}
    assert dashboard_ops._dashboard_has_datasource(templating) is True

    panel_target = {"panels": [{"datasource": {"uid": "ds-2"}, "targets": [{"expr": "up"}]}]}
    assert dashboard_ops._dashboard_has_datasource(panel_target) is True

    missing = {"panels": [{"targets": [{"expr": "up"}]}]}
    assert dashboard_ops._dashboard_has_datasource(missing) is False

    no_query = {"panels": [{"targets": [{"legendFormat": "only-label"}]}]}
    assert dashboard_ops._dashboard_has_datasource(no_query) is True


@pytest.mark.asyncio
async def test_resolve_folder_uid_by_id_and_access_helpers():
    async def _get_folders():
        return [SimpleNamespace(id=1, uid="f1"), SimpleNamespace(id=2, uid="f2")]

    service = SimpleNamespace(
        grafana_service=SimpleNamespace(
            get_folders=_get_folders
        )
    )
    assert await dashboard_ops._resolve_folder_uid_by_id(service, None) is None
    assert await dashboard_ops._resolve_folder_uid_by_id(service, "bad") is None
    assert await dashboard_ops._resolve_folder_uid_by_id(service, 1) == "f1"
    assert await dashboard_ops._resolve_folder_uid_by_id(service, 999) is None


def test_dashboard_access_and_metadata_helpers():
    db = _session()
    owner, viewer, g1 = _seed(db)
    dash = GrafanaDashboard(
        tenant_id="t1",
        created_by=owner.id,
        grafana_uid="d1",
        grafana_id=101,
        title="Dash",
        visibility="group",
        hidden_by=[],
    )
    dash.shared_groups.append(g1)
    db.add(dash)
    db.commit()

    assert dashboard_ops.check_dashboard_access(db, "d1", owner.id, "t1", [], require_write=True) is not None
    assert dashboard_ops.check_dashboard_access(db, "d1", viewer.id, "t1", [], require_write=False) is None
    assert dashboard_ops.check_dashboard_access(db, "d1", viewer.id, "t1", ["g1"], require_write=False) is not None

    uids, allow_system = dashboard_ops.get_accessible_dashboard_uids(db, viewer.id, "t1", ["g1"])
    assert "d1" in uids
    assert allow_system is False

    ctx_by_uid = dashboard_ops.build_dashboard_search_context(db, tenant_id="t1", uid="d1")
    assert ctx_by_uid.get("uid_db_dashboard") is not None
    ctx_all = dashboard_ops.build_dashboard_search_context(db, tenant_id="t1")
    assert "d1" in ctx_all.get("all_registered_uids", set())

    assert dashboard_ops.toggle_dashboard_hidden(db, "d1", viewer.id, "t1", True) is True
    assert viewer.id in (db.query(GrafanaDashboard).filter_by(grafana_uid="d1").first().hidden_by or [])

    metadata = dashboard_ops.get_dashboard_metadata(db, "t1")
    assert metadata["team_ids"] == ["g1"]
