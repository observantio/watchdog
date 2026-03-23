"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import httpx
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests._env import ensure_test_env

ensure_test_env()

from db_models import Base, GrafanaDashboard, GrafanaFolder, Group, Tenant, User
from models.grafana.grafana_dashboard_models import Dashboard, DashboardCreate, DashboardUpdate, DashboardSearchResult
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
        org_id="org",
        is_active=True,
    )
    other = User(
        id="u2",
        tenant_id="t1",
        username="other",
        email="other@example.com",
        hashed_password="x",
        org_id="org",
        is_active=True,
    )
    g1 = Group(id="g1", tenant_id="t1", name="Team-1", is_active=True)
    db.add_all([owner, other, g1])
    db.commit()
    return owner, other, g1


def _create_payload(uid: str | None = "d1", folder_id: int = 0):
    return DashboardCreate(
        dashboard=Dashboard(uid=uid, title="CPU", tags=["ops"], panels=[{"targets": [{"expr": "up"}], "datasource": {"uid": "ds-1"}}]),
        folderId=folder_id,
        overwrite=False,
    )


@pytest.mark.asyncio
async def test_create_dashboard_none_no_uid_and_folder_resolution_error(monkeypatch):
    db = _session()
    _seed(db)

    class _GS:
        def __init__(self):
            self.mode = "none"

        async def create_dashboard(self, _payload):
            if self.mode == "none":
                return None
            if self.mode == "nouid":
                return {"status": "ok", "dashboard": {"title": "CPU"}}
            return {"uid": "d1", "id": 1, "dashboard": {"uid": "d1", "title": "CPU", "tags": []}}

        async def search_dashboards(self, **_kwargs):
            return []

        async def get_folders(self):
            raise RuntimeError("boom")

    gs = _GS()
    service = SimpleNamespace(
        grafana_service=gs,
        logger=SimpleNamespace(debug=lambda *args, **kwargs: None),
        _validate_group_visibility=lambda *args, **kwargs: [],
        _raise_http_from_grafana_error=lambda exc: (_ for _ in ()).throw(HTTPException(status_code=500, detail=str(exc))),
    )

    async def no_conflict(*_args, **_kwargs):
        return False

    monkeypatch.setattr(dashboard_ops, "_has_accessible_title_conflict", no_conflict)

    assert await dashboard_ops.create_dashboard(service, db, _create_payload(), "u1", "t1", []) is None

    gs.mode = "nouid"
    out = await dashboard_ops.create_dashboard(service, db, _create_payload(uid=None), "u1", "t1", [])
    assert out == {"status": "ok", "dashboard": {"title": "CPU"}}

    async def _resolve_none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(dashboard_ops, "_resolve_folder_uid_by_id", _resolve_none)
    gs.mode = "ok"
    out2 = await dashboard_ops.create_dashboard(service, db, _create_payload(folder_id=7), "u1", "t1", [])
    assert out2 and out2.get("uid") == "d1"


@pytest.mark.asyncio
async def test_update_dashboard_owner_folder_access_and_result_paths(monkeypatch):
    db = _session()
    owner, _, g1 = _seed(db)
    folder = GrafanaFolder(
        tenant_id="t1",
        created_by=owner.id,
        grafana_uid="f1",
        grafana_id=11,
        title="Folder",
        visibility="group",
        allow_dashboard_writes=True,
    )
    folder.shared_groups.append(g1)
    dash = GrafanaDashboard(
        tenant_id="t1",
        created_by=owner.id,
        grafana_uid="d1",
        grafana_id=1,
        title="CPU",
        visibility="group",
        folder_uid="f1",
    )
    dash.shared_groups.append(g1)
    db.add_all([folder, dash])
    db.commit()

    class _GS:
        async def update_dashboard(self, _uid, _payload):
            return {"uid": "d1", "dashboard": {"title": "Updated", "tags": ["a"]}}

        async def get_folders(self):
            return [SimpleNamespace(id=11, uid="f1")]

    mapped = {"count": 0}

    def _map(_exc):
        mapped["count"] += 1
        raise HTTPException(status_code=502, detail="mapped")

    service = SimpleNamespace(grafana_service=_GS(), _raise_http_from_grafana_error=_map, _validate_group_visibility=lambda *args, **kwargs: [g1])

    async def no_conflict(*_args, **_kwargs):
        return False

    monkeypatch.setattr(dashboard_ops, "_has_accessible_title_conflict", no_conflict)

    # owner folder access denied branch
    monkeypatch.setattr(dashboard_ops, "check_folder_access", lambda *args, **kwargs: None)
    with pytest.raises(HTTPException, match="Folder access denied"):
        await dashboard_ops.update_dashboard(
            service,
            db,
            "d1",
            DashboardUpdate(dashboard=Dashboard(title="U", tags=[], panels=[{"targets": [{"expr": "up"}], "datasource": {"uid": "ds"}}]), folderId=11, overwrite=True),
            owner.id,
            "t1",
            ["g1"],
        )

    # normal update with visibility change to group and then tenant clear branch
    monkeypatch.setattr(dashboard_ops, "check_folder_access", lambda *args, **kwargs: folder)
    out = await dashboard_ops.update_dashboard(
        service,
        db,
        "d1",
        DashboardUpdate(dashboard=Dashboard(title="U", tags=[], panels=[{"targets": [{"expr": "up"}], "datasource": {"uid": "ds"}}]), folderId=11, overwrite=True),
        owner.id,
        "t1",
        ["g1"],
        visibility="group",
        shared_group_ids=["g1"],
    )
    assert out and out.get("visibility") == "group"

    out2 = await dashboard_ops.update_dashboard(
        service,
        db,
        "d1",
        DashboardUpdate(dashboard=Dashboard(title="U2", tags=[], panels=[{"targets": [{"expr": "up"}], "datasource": {"uid": "ds"}}]), folderId=0, overwrite=True),
        owner.id,
        "t1",
        ["g1"],
        visibility="tenant",
    )
    assert out2 and out2.get("visibility") == "tenant"

    # upstream error mapping path + None result path
    async def update_err(_uid, _payload):
        raise httpx.ConnectError("x", request=httpx.Request("POST", "http://x"))

    service.grafana_service.update_dashboard = update_err
    with pytest.raises(HTTPException, match="mapped"):
        await dashboard_ops.update_dashboard(
            service,
            db,
            "d1",
            DashboardUpdate(dashboard=Dashboard(title="U", tags=[], panels=[{"targets": [{"expr": "up"}], "datasource": {"uid": "ds"}}]), overwrite=True),
            owner.id,
            "t1",
            ["g1"],
        )

    async def update_none(_uid, _payload):
        return None

    service.grafana_service.update_dashboard = update_none
    assert await dashboard_ops.update_dashboard(
        service,
        db,
        "d1",
        DashboardUpdate(dashboard=Dashboard(title="U", tags=[], panels=[{"targets": [{"expr": "up"}], "datasource": {"uid": "ds"}}]), overwrite=True),
        owner.id,
        "t1",
        ["g1"],
    ) is None


@pytest.mark.asyncio
async def test_search_get_delete_additional_branches(monkeypatch):
    db = _session()
    owner, other, g1 = _seed(db)
    dash = GrafanaDashboard(
        tenant_id="t1",
        created_by=owner.id,
        grafana_uid="d1",
        grafana_id=1,
        title="CPU",
        visibility="group",
        folder_uid=None,
    )
    dash.shared_groups.append(g1)
    db.add(dash)
    db.commit()

    class _GS:
        async def search_dashboards(self, **_kwargs):
            class _Dash:
                uid = "d1"
                folder_uid = None
                folderUid = None

                def model_dump(self):
                    return {
                        "id": 1,
                        "uid": "d1",
                        "title": "CPU",
                        "uri": "db/cpu",
                        "url": "/d/d1/cpu",
                        "slug": "cpu",
                        "type": "dash-db",
                        "tags": [],
                        "folderId": "bad-int",
                        "folderUid": None,
                        "folderTitle": None,
                    }
            return [
                _Dash()
            ]

        async def get_dashboard(self, uid):
            if uid == "d1":
                return {"meta": {"folderId": 99}, "dashboard": {"title": "CPU", "tags": []}}
            return None

        async def delete_dashboard(self, _uid):
            return False

    service = SimpleNamespace(grafana_service=_GS())

    monkeypatch.setattr(dashboard_ops, "is_folder_accessible", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_ops, "get_accessible_dashboard_uids", lambda *args, **kwargs: (["d1"], False))
    monkeypatch.setattr(dashboard_ops, "_to_search_result", lambda *args, **kwargs: SimpleNamespace(uid="d1"))
    listed = await dashboard_ops.search_dashboards(service, db, owner.id, "t1", ["g1"], team_id="g1")
    assert len(listed) == 1
    # team_id mismatch filtered
    listed2 = await dashboard_ops.search_dashboards(service, db, owner.id, "t1", ["g1"], team_id="g2")
    assert listed2 == []

    # get_dashboard non-general folder unresolved -> None
    monkeypatch.setattr(dashboard_ops, "is_folder_accessible", lambda *args, **kwargs: False)
    assert await dashboard_ops.get_dashboard(service, db, "d1", other.id, "t1", ["g1"]) is None

    # delete_dashboard false path when upstream delete returns false
    assert await dashboard_ops.delete_dashboard(service, db, "d1", owner.id, "t1", ["g1"]) is False
