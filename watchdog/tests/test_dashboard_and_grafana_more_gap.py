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
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests._env import ensure_test_env

ensure_test_env()

from db_models import Base, GrafanaDashboard, Tenant, User
from models.grafana.grafana_dashboard_models import DashboardSearchResult
from services.grafana import dashboard_ops
from services.grafana.grafana_service import GrafanaService


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db):
    db.add(Tenant(id="t1", name="tenant-1", display_name="Tenant 1"))
    db.add(
        User(
            id="u1",
            tenant_id="t1",
            username="owner",
            email="owner@example.com",
            hashed_password="x",
            org_id="org",
            is_active=True,
        )
    )
    db.commit()


@pytest.mark.asyncio
async def test_dashboard_ops_get_delete_toggle_and_uid_search_paths():
    db = _session()
    _seed(db)
    db.add(
        GrafanaDashboard(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="d1",
            grafana_id=101,
            title="CPU",
            visibility="private",
        )
    )
    db.commit()

    class _Svc:
        async def get_dashboard(self, uid):
            if uid == "d1":
                return {"meta": {"folderId": 0, "url": "/d/d1", "slug": "cpu"}, "dashboard": {"title": "CPU", "tags": []}}
            return None

        async def search_dashboards(self, **_kwargs):
            return [
                DashboardSearchResult(
                    id=101,
                    uid="d1",
                    title="CPU",
                    uri="db/cpu",
                    url="/d/d1/cpu",
                    slug="cpu",
                    type="dash-db",
                    tags=[],
                    folderId=None,
                    folderUid=None,
                    folderTitle=None,
                )
            ]

        async def delete_dashboard(self, uid):
            return uid == "d1"

    service = SimpleNamespace(grafana_service=_Svc())
    payload = await dashboard_ops.get_dashboard(service, db, "d1", "u1", "t1", [])
    assert payload is not None and payload.get("is_owned") is True
    assert await dashboard_ops.get_dashboard(service, db, "missing", "u1", "t1", []) is None

    listed = await dashboard_ops.search_dashboards(service, db, "u1", "t1", [], uid="d1")
    assert len(listed) == 1 and listed[0].uid == "d1"

    assert await dashboard_ops.delete_dashboard(service, db, "missing", "u1", "t1", []) is False
    assert await dashboard_ops.delete_dashboard(service, db, "d1", "u1", "t1", []) is True
    assert dashboard_ops.toggle_dashboard_hidden(db, "missing", "u1", "t1", True) is False


@pytest.mark.asyncio
async def test_grafana_service_parse_error_and_update_folder_refreshed_none(monkeypatch):
    service = GrafanaService(grafana_url="http://grafana.local", username="u", password="p", api_key="k")

    req = httpx.Request("GET", "http://grafana.local")

    class _BrokenJsonResponse(httpx.Response):
        def json(self, **kwargs):  # type: ignore[override]
            raise ValueError("bad")

    response = _BrokenJsonResponse(500, request=req, text="plain-text")
    err = httpx.HTTPStatusError("bad", request=req, response=response)
    assert service._parse_error_body(err) == "plain-text"

    async def get_folder(_uid):
        return type("Folder", (), {"id": 1, "uid": "f1", "version": 1})()

    async def mutating(_method, _path, **_kwargs):
        raise Exception("unexpected")

    # 412 path where refresh returns None
    async def mutating_412(_method, _path, **_kwargs):
        from services.grafana.grafana_service import GrafanaAPIError

        raise GrafanaAPIError(412, {"message": "version"})

    service.get_folder = get_folder
    service._mutating_request = mutating_412
    async def get_none(_uid):
        return None
    service.get_folder = get_none
    assert await service.update_folder("f1", "New") is None

    service._mutating_request = mutating
    service.get_folder = get_folder
    with pytest.raises(Exception, match="unexpected"):
        await service.update_folder("f1", "New")
