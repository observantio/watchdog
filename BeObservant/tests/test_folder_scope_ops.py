"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import os
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/observantio_test")
os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "False")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

from db_models import Base, GrafanaDashboard, GrafanaFolder, Tenant, User
from models.grafana.grafana_dashboard_models import DashboardSearchResult
from services.grafana import dashboard_ops, folder_ops


class _GrafanaServiceStub:
    def __init__(self, *, folders=None, created_folder=None, updated_folder=None, dashboards=None):
        self._folders = list(folders or [])
        self._created_folder = created_folder
        self._updated_folder = updated_folder
        self._dashboards = list(dashboards or [])

    async def get_folders(self):
        return self._folders

    async def create_folder(self, title):
        return self._created_folder

    async def update_folder(self, uid, title):
        return self._updated_folder

    async def search_dashboards(self, **kwargs):
        return self._dashboards


class _ProxyStub:
    def __init__(self, grafana_service):
        self.grafana_service = grafana_service

    def _validate_group_visibility(self, db, *, user_id=None, tenant_id, group_ids, shared_group_ids, is_admin):
        return []


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    tenant = Tenant(id="t1", name="tenant-1", display_name="Tenant 1")
    owner = User(
        id="u1",
        tenant_id="t1",
        username="owner",
        email="owner@example.com",
        hashed_password="x",
        org_id="org-a",
        is_active=True,
    )
    other = User(
        id="u2",
        tenant_id="t1",
        username="other",
        email="other@example.com",
        hashed_password="x",
        org_id="org-b",
        is_active=True,
    )
    db.add_all([tenant, owner, other])
    db.commit()
    return db


@pytest.mark.asyncio
async def test_create_folder_persists_visibility_scope(db_session):
    created = SimpleNamespace(id=10, uid="f-private", title="Private Folder")
    service = _ProxyStub(_GrafanaServiceStub(created_folder=created))

    result = await folder_ops.create_folder(
        service,
        db_session,
        title="Private Folder",
        user_id="u1",
        tenant_id="t1",
        group_ids=[],
        visibility="private",
        shared_group_ids=[],
        is_admin=False,
    )

    assert result is not None
    db_row = db_session.query(GrafanaFolder).filter_by(grafana_uid="f-private", tenant_id="t1").first()
    assert db_row is not None
    assert db_row.visibility == "private"
    assert db_row.created_by == "u1"
    assert db_row.allow_dashboard_writes is False


@pytest.mark.asyncio
async def test_create_folder_persists_allow_dashboard_writes_flag(db_session):
    created = SimpleNamespace(id=12, uid="f-collab", title="Collaborative Folder")
    service = _ProxyStub(_GrafanaServiceStub(created_folder=created))

    result = await folder_ops.create_folder(
        service,
        db_session,
        title="Collaborative Folder",
        user_id="u1",
        tenant_id="t1",
        group_ids=[],
        visibility="tenant",
        shared_group_ids=[],
        allow_dashboard_writes=True,
        is_admin=False,
    )

    assert result is not None
    db_row = db_session.query(GrafanaFolder).filter_by(grafana_uid="f-collab", tenant_id="t1").first()
    assert db_row is not None
    assert db_row.allow_dashboard_writes is True


@pytest.mark.asyncio
async def test_get_folders_hides_private_folder_from_non_owner(db_session):
    db_session.add(
        GrafanaFolder(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="f-private",
            grafana_id=10,
            title="Private Folder",
            visibility="private",
        )
    )
    db_session.commit()

    service = _ProxyStub(
        _GrafanaServiceStub(folders=[SimpleNamespace(id=10, uid="f-private", title="Private Folder")])
    )

    folders = await folder_ops.get_folders(
        service,
        db_session,
        user_id="u2",
        tenant_id="t1",
        group_ids=[],
        is_admin=False,
    )

    assert folders == []


@pytest.mark.asyncio
async def test_get_folders_hides_private_folder_from_admin_when_not_owner(db_session):
    db_session.add(
        GrafanaFolder(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="f-private",
            grafana_id=10,
            title="Private Folder",
            visibility="private",
        )
    )
    db_session.commit()

    service = _ProxyStub(
        _GrafanaServiceStub(folders=[SimpleNamespace(id=10, uid="f-private", title="Private Folder")])
    )

    folders = await folder_ops.get_folders(
        service,
        db_session,
        user_id="u2",
        tenant_id="t1",
        group_ids=[],
        is_admin=True,
    )

    assert folders == []


@pytest.mark.asyncio
async def test_dashboard_search_respects_folder_scope(db_session):
    db_session.add_all([
        GrafanaFolder(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="f-private",
            grafana_id=10,
            title="Private Folder",
            visibility="private",
        ),
        GrafanaDashboard(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="d-1",
            grafana_id=100,
            title="CPU",
            folder_uid="f-private",
            visibility="tenant",
        ),
    ])
    db_session.commit()

    dash = DashboardSearchResult(
        id=100,
        uid="d-1",
        title="CPU",
        uri="db/cpu",
        url="/d/d-1",
        slug="cpu",
        type="dash-db",
        tags=[],
        folderId=10,
        folderUid="f-private",
        folderTitle="Private Folder",
    )
    service = _ProxyStub(_GrafanaServiceStub(dashboards=[dash]))

    results = await dashboard_ops.search_dashboards(
        service,
        db_session,
        user_id="u2",
        tenant_id="t1",
        group_ids=[],
    )

    assert results == []


@pytest.mark.asyncio
async def test_update_folder_visibility_and_scope(db_session):
    db_session.add(
        GrafanaFolder(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="f-tenant",
            grafana_id=11,
            title="Team Folder",
            visibility="tenant",
        )
    )
    db_session.commit()

    updated = SimpleNamespace(id=11, uid="f-tenant", title="Team Folder")
    service = _ProxyStub(_GrafanaServiceStub(updated_folder=updated))

    result = await folder_ops.update_folder(
        service,
        db_session,
        uid="f-tenant",
        user_id="u1",
        tenant_id="t1",
        group_ids=[],
        title="Team Folder",
        visibility="private",
        shared_group_ids=[],
        allow_dashboard_writes=True,
        is_admin=False,
    )

    assert result is not None
    db_row = db_session.query(GrafanaFolder).filter_by(grafana_uid="f-tenant").first()
    assert db_row.visibility == "private"
    assert db_row.allow_dashboard_writes is True

    visible_to_other = folder_ops.is_folder_accessible(
        db_session, "f-tenant", "u2", "t1", [], require_write=False, is_admin=False
    )
    assert visible_to_other is False
