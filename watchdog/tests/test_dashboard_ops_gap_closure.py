"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests._env import ensure_test_env

ensure_test_env()

from db_models import Base, GrafanaDashboard, Tenant, User
from models.grafana.grafana_dashboard_models import Dashboard, DashboardCreate, DashboardUpdate
from services.grafana import dashboard_ops
from services.grafana.grafana_service import GrafanaAPIError


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_minimal(db):
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


def _dashboard_create(uid="dash-fixed"):
    return DashboardCreate(
        dashboard=Dashboard(
            uid=uid,
            title="CPU",
            tags=["ops"],
            panels=[{"targets": [{"expr": "up"}], "datasource": {"uid": "ds-1"}}],
        ),
        folderId=0,
        overwrite=False,
    )


async def _no_conflict(*_args, **_kwargs):
    return False


@pytest.mark.asyncio
async def test_create_dashboard_retries_uid_on_conflict_and_then_succeeds(monkeypatch):
    db = _session()
    _seed_minimal(db)
    calls = []

    class _GrafanaService:
        async def create_dashboard(self, payload):
            calls.append(payload.dashboard.uid)
            if len(calls) == 1:
                raise GrafanaAPIError(409, {"message": "uid exists"})
            return {
                "uid": payload.dashboard.uid,
                "id": 11,
                "dashboard": {"uid": payload.dashboard.uid, "title": payload.dashboard.title, "tags": payload.dashboard.tags},
            }

        async def search_dashboards(self, **_kwargs):
            return []

        async def get_folders(self):
            return []

    service = SimpleNamespace(
        grafana_service=_GrafanaService(),
        logger=SimpleNamespace(debug=lambda *args, **kwargs: None),
        _validate_group_visibility=lambda *args, **kwargs: [],
        _raise_http_from_grafana_error=lambda exc: (_ for _ in ()).throw(
            HTTPException(status_code=500, detail=str(exc))
        ),
    )
    monkeypatch.setattr(dashboard_ops, "_has_accessible_title_conflict", _no_conflict)

    out = await dashboard_ops.create_dashboard(
        service,
        db,
        _dashboard_create(),
        user_id="u1",
        tenant_id="t1",
        group_ids=[],
    )
    assert out is not None
    assert len(calls) == 2
    assert calls[0] == "dash-fixed"
    assert calls[1].startswith("dash-fixed-")


@pytest.mark.asyncio
async def test_create_dashboard_maps_grafana_error_after_failed_retry(monkeypatch):
    db = _session()
    _seed_minimal(db)
    created = {"mapped": False}

    class _GrafanaService:
        async def create_dashboard(self, _payload):
            raise GrafanaAPIError(412, {"message": "conflict"})

        async def search_dashboards(self, **_kwargs):
            return []

        async def get_folders(self):
            return []

    def map_error(_exc):
        created["mapped"] = True
        raise HTTPException(status_code=412, detail="mapped")

    service = SimpleNamespace(
        grafana_service=_GrafanaService(),
        logger=SimpleNamespace(debug=lambda *args, **kwargs: None),
        _validate_group_visibility=lambda *args, **kwargs: [],
        _raise_http_from_grafana_error=map_error,
    )
    monkeypatch.setattr(dashboard_ops, "_has_accessible_title_conflict", _no_conflict)

    with pytest.raises(HTTPException, match="mapped"):
        await dashboard_ops.create_dashboard(
            service,
            db,
            _dashboard_create(uid="dash-existing"),
            user_id="u1",
            tenant_id="t1",
            group_ids=[],
        )
    assert created["mapped"] is True


@pytest.mark.asyncio
async def test_update_dashboard_maps_upstream_errors(monkeypatch):
    db = _session()
    _seed_minimal(db)
    db.add(
        GrafanaDashboard(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="d1",
            grafana_id=101,
            title="Original",
            visibility="private",
        )
    )
    db.commit()

    class _GrafanaService:
        async def update_dashboard(self, _uid, _payload):
            raise GrafanaAPIError(502, {"message": "upstream"})

    mapped = {"value": False}

    def map_error(_exc):
        mapped["value"] = True
        raise HTTPException(status_code=502, detail="mapped-upstream")

    service = SimpleNamespace(
        grafana_service=_GrafanaService(),
        _raise_http_from_grafana_error=map_error,
        _validate_group_visibility=lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(dashboard_ops, "_has_accessible_title_conflict", _no_conflict)

    with pytest.raises(HTTPException, match="mapped-upstream"):
        await dashboard_ops.update_dashboard(
            service,
            db,
            uid="d1",
            dashboard_update=DashboardUpdate(dashboard=Dashboard(title="x", tags=[]), overwrite=True),
            user_id="u1",
            tenant_id="t1",
            group_ids=[],
        )
    assert mapped["value"] is True
