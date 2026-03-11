
"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/observantio_test")
os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "False")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

from db_models import Base, GrafanaDashboard, GrafanaFolder, Tenant, User
from models.grafana.grafana_dashboard_models import Dashboard, DashboardUpdate
from models.grafana.grafana_dashboard_models import DashboardSearchResult
from services.grafana import dashboard_ops


class _GrafanaServiceStub:
    def __init__(self, *, get_dashboard_result=None, search_results=None):
        self._get_dashboard_result = get_dashboard_result
        self._search_results = list(search_results or [])
        self.last_search_kwargs = None

    async def get_dashboard(self, uid: str):
        return self._get_dashboard_result

    async def search_dashboards(self, **kwargs):
        self.last_search_kwargs = kwargs
        return self._search_results

    async def update_dashboard(self, uid: str, payload):
        dashboard = getattr(payload, "dashboard", None)
        return {
            "uid": uid,
            "dashboard": {
                "uid": uid,
                "title": getattr(dashboard, "title", "Updated"),
                "tags": getattr(dashboard, "tags", []),
            },
        }


class _ProxyStub:
    def __init__(self, grafana_service):
        self.grafana_service = grafana_service


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_user_and_dashboard(db):
    tenant = Tenant(id="t1", name="tenant-1", display_name="Tenant 1")
    user = User(
        id="u1",
        tenant_id="t1",
        username="user1",
        email="u1@example.com",
        hashed_password="x",
        org_id="org-a",
        is_active=True,
    )
    dash = GrafanaDashboard(
        tenant_id="t1",
        created_by="u1",
        grafana_uid="dash-uid-1",
        grafana_id=101,
        title="CPU Overview",
        visibility="private",
    )
    db.add_all([tenant, user, dash])
    db.commit()


@pytest.mark.asyncio
async def test_get_dashboard_prunes_deleted_grafana_dashboard_record():
    db = _session()
    _seed_user_and_dashboard(db)

    service = _ProxyStub(_GrafanaServiceStub(get_dashboard_result=None))

    result = await dashboard_ops.get_dashboard(
        service,
        db,
        uid="dash-uid-1",
        user_id="u1",
        tenant_id="t1",
        group_ids=[],
    )

    assert result is None
    assert db.query(GrafanaDashboard).filter(GrafanaDashboard.grafana_uid == "dash-uid-1").first() is None


@pytest.mark.asyncio
async def test_accessible_title_conflict_ignores_stale_db_rows():
    db = _session()
    _seed_user_and_dashboard(db)

    service = _ProxyStub(_GrafanaServiceStub(search_results=[]))

    has_conflict = await dashboard_ops._has_accessible_title_conflict(
        service,
        db,
        tenant_id="t1",
        user_id="u1",
        group_ids=[],
        title="CPU Overview",
    )

    assert has_conflict is False


@pytest.mark.asyncio
async def test_accessible_title_conflict_detects_live_dashboard():
    db = _session()
    _seed_user_and_dashboard(db)

    class _DashObj:
        uid = "dash-uid-1"
        title = "CPU Overview"

    service = _ProxyStub(_GrafanaServiceStub(search_results=[_DashObj()]))

    has_conflict = await dashboard_ops._has_accessible_title_conflict(
        service,
        db,
        tenant_id="t1",
        user_id="u1",
        group_ids=[],
        title="CPU Overview",
    )

    assert has_conflict is True


@pytest.mark.asyncio
async def test_accessible_title_conflict_ignores_stale_db_title_when_live_title_changed():
    db = _session()
    _seed_user_and_dashboard(db)

    class _DashObj:
        uid = "dash-uid-1"
        title = "Renamed Dashboard"

    service = _ProxyStub(_GrafanaServiceStub(search_results=[_DashObj()]))

    has_conflict = await dashboard_ops._has_accessible_title_conflict(
        service,
        db,
        tenant_id="t1",
        user_id="u1",
        group_ids=[],
        title="CPU Overview",
    )

    assert has_conflict is False


@pytest.mark.asyncio
async def test_search_dashboards_deduplicates_same_uid_results():
    db = _session()
    _seed_user_and_dashboard(db)
    db.add(
        GrafanaFolder(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="folder-uid-7",
            grafana_id=7,
            title="Ops",
            visibility="tenant",
        )
    )
    db.commit()

    results = [
        DashboardSearchResult(
            id=101,
            uid="dash-uid-1",
            title="CPU Overview",
            uri="db/cpu-overview",
            url="/d/dash-uid-1/cpu-overview",
            slug="cpu-overview",
            type="dash-db",
            tags=[],
            folderId=None,
            folderUid=None,
            folderTitle=None,
        ),
        DashboardSearchResult(
            id=101,
            uid="dash-uid-1",
            title="CPU Overview",
            uri="db/cpu-overview",
            url="/d/dash-uid-1/cpu-overview",
            slug="cpu-overview",
            type="dash-db",
            tags=[],
            folderId=7,
            folderUid="folder-uid-7",
            folderTitle="Ops",
        ),
    ]
    service = _ProxyStub(_GrafanaServiceStub(search_results=results))

    dashboards = await dashboard_ops.search_dashboards(
        service,
        db,
        user_id="u1",
        tenant_id="t1",
        group_ids=[],
    )

    assert len(dashboards) == 1
    assert dashboards[0].uid == "dash-uid-1"


@pytest.mark.asyncio
async def test_search_dashboards_uses_db_folder_scope_when_folder_uid_missing_in_search_row():
    db = _session()
    _seed_user_and_dashboard(db)
    db.add(
        GrafanaFolder(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="folder-private",
            grafana_id=42,
            title="Private Folder",
            visibility="private",
        )
    )
    db_dash = db.query(GrafanaDashboard).filter_by(grafana_uid="dash-uid-1").first()
    db_dash.folder_uid = "folder-private"
    db_dash.visibility = "tenant"
    db.commit()

    # Simulate Grafana search row missing folderUid/folderUid metadata.
    results = [
        DashboardSearchResult(
            id=101,
            uid="dash-uid-1",
            title="CPU Overview",
            uri="db/cpu-overview",
            url="/d/dash-uid-1/cpu-overview",
            slug="cpu-overview",
            type="dash-db",
            tags=[],
            folderId=None,
            folderUid=None,
            folderTitle=None,
        )
    ]
    service = _ProxyStub(_GrafanaServiceStub(search_results=results))

    dashboards = await dashboard_ops.search_dashboards(
        service,
        db,
        user_id="u2",
        tenant_id="t1",
        group_ids=[],
    )

    assert dashboards == []


@pytest.mark.asyncio
async def test_search_dashboards_skips_non_general_folder_when_folder_scope_unknown():
    db = _session()
    _seed_user_and_dashboard(db)
    db_dash = db.query(GrafanaDashboard).filter_by(grafana_uid="dash-uid-1").first()
    db_dash.folder_uid = None
    db.commit()

    results = [
        DashboardSearchResult(
            id=101,
            uid="dash-uid-1",
            title="CPU Overview",
            uri="db/cpu-overview",
            url="/d/dash-uid-1/cpu-overview",
            slug="cpu-overview",
            type="dash-db",
            tags=[],
            folderId=22,
            folderUid=None,
            folderTitle="Leaky Folder",
        )
    ]
    service = _ProxyStub(_GrafanaServiceStub(search_results=results))

    dashboards = await dashboard_ops.search_dashboards(
        service,
        db,
        user_id="u2",
        tenant_id="t1",
        group_ids=[],
    )

    assert dashboards == []


@pytest.mark.asyncio
async def test_search_dashboards_honors_folder_ids_filter():
    db = _session()
    _seed_user_and_dashboard(db)
    db.add(
        GrafanaFolder(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="folder-uid-7",
            grafana_id=7,
            title="Ops",
            visibility="tenant",
        )
    )
    db.commit()

    results = [
        DashboardSearchResult(
            id=101,
            uid="dash-uid-1",
            title="CPU Overview",
            uri="db/cpu-overview",
            url="/d/dash-uid-1/cpu-overview",
            slug="cpu-overview",
            type="dash-db",
            tags=[],
            folderId=7,
            folderUid="folder-uid-7",
            folderTitle="Ops",
        ),
        DashboardSearchResult(
            id=102,
            uid="dash-uid-2",
            title="Memory",
            uri="db/memory",
            url="/d/dash-uid-2/memory",
            slug="memory",
            type="dash-db",
            tags=[],
            folderId=12,
            folderUid="folder-uid-12",
            folderTitle="Other",
        ),
    ]
    gs = _GrafanaServiceStub(search_results=results)
    service = _ProxyStub(gs)

    dashboards = await dashboard_ops.search_dashboards(
        service,
        db,
        user_id="u1",
        tenant_id="t1",
        group_ids=[],
        folder_ids=[7],
    )

    assert [d.uid for d in dashboards] == ["dash-uid-1"]
    assert gs.last_search_kwargs.get("folder_ids") == [7]


@pytest.mark.asyncio
async def test_search_dashboards_general_folder_filter_includes_dashboards_without_folder_id():
    db = _session()
    _seed_user_and_dashboard(db)

    results = [
        DashboardSearchResult(
            id=101,
            uid="dash-uid-1",
            title="CPU Overview",
            uri="db/cpu-overview",
            url="/d/dash-uid-1/cpu-overview",
            slug="cpu-overview",
            type="dash-db",
            tags=[],
            folderId=None,
            folderUid=None,
            folderTitle=None,
        )
    ]
    gs = _GrafanaServiceStub(search_results=results)
    service = _ProxyStub(gs)

    dashboards = await dashboard_ops.search_dashboards(
        service,
        db,
        user_id="u1",
        tenant_id="t1",
        group_ids=[],
        folder_ids=[0],
    )

    assert [d.uid for d in dashboards] == ["dash-uid-1"]
    assert gs.last_search_kwargs.get("folder_ids") == [0]


@pytest.mark.asyncio
async def test_search_dashboards_excludes_foldered_when_requested_for_proxy_root_listing():
    db = _session()
    _seed_user_and_dashboard(db)
    db.add(
        GrafanaFolder(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="folder-uid-7",
            grafana_id=7,
            title="Ops",
            visibility="tenant",
        )
    )
    db_dash = db.query(GrafanaDashboard).filter_by(grafana_uid="dash-uid-1").first()
    db_dash.folder_uid = "folder-uid-7"
    db.commit()

    results = [
        DashboardSearchResult(
            id=101,
            uid="dash-uid-1",
            title="CPU Overview",
            uri="db/cpu-overview",
            url="/d/dash-uid-1/cpu-overview",
            slug="cpu-overview",
            type="dash-db",
            tags=[],
            folderId=7,
            folderUid="folder-uid-7",
            folderTitle="Ops",
        )
    ]
    service = _ProxyStub(_GrafanaServiceStub(search_results=results))

    dashboards = await dashboard_ops.search_dashboards(
        service,
        db,
        user_id="u1",
        tenant_id="t1",
        group_ids=[],
        exclude_foldered_dashboards=True,
    )

    assert dashboards == []


@pytest.mark.asyncio
async def test_search_dashboards_honors_folder_uids_filter():
    db = _session()
    _seed_user_and_dashboard(db)
    db.add(
        GrafanaFolder(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="folder-uid-7",
            grafana_id=7,
            title="Ops",
            visibility="tenant",
        )
    )
    db.commit()

    results = [
        DashboardSearchResult(
            id=101,
            uid="dash-uid-1",
            title="CPU Overview",
            uri="db/cpu-overview",
            url="/d/dash-uid-1/cpu-overview",
            slug="cpu-overview",
            type="dash-db",
            tags=[],
            folderId=7,
            folderUid="folder-uid-7",
            folderTitle="Ops",
        )
    ]
    gs = _GrafanaServiceStub(search_results=results)
    service = _ProxyStub(gs)

    dashboards = await dashboard_ops.search_dashboards(
        service,
        db,
        user_id="u1",
        tenant_id="t1",
        group_ids=[],
        folder_uids=["folder-uid-7"],
    )

    assert [d.uid for d in dashboards] == ["dash-uid-1"]
    assert gs.last_search_kwargs.get("folder_uids") == ["folder-uid-7"]


@pytest.mark.asyncio
async def test_search_dashboards_honors_dashboard_uid_filters():
    db = _session()
    _seed_user_and_dashboard(db)
    results = [
        DashboardSearchResult(
            id=101,
            uid="dash-uid-1",
            title="CPU Overview",
            uri="db/cpu-overview",
            url="/d/dash-uid-1/cpu-overview",
            slug="cpu-overview",
            type="dash-db",
            tags=[],
            folderId=None,
            folderUid=None,
            folderTitle=None,
        ),
        DashboardSearchResult(
            id=102,
            uid="dash-uid-2",
            title="Memory",
            uri="db/memory",
            url="/d/dash-uid-2/memory",
            slug="memory",
            type="dash-db",
            tags=[],
            folderId=None,
            folderUid=None,
            folderTitle=None,
        ),
    ]
    gs = _GrafanaServiceStub(search_results=results)
    service = _ProxyStub(gs)

    dashboards = await dashboard_ops.search_dashboards(
        service,
        db,
        user_id="u1",
        tenant_id="t1",
        group_ids=[],
        dashboard_uids=["dash-uid-1"],
    )

    assert [d.uid for d in dashboards] == ["dash-uid-1"]
    assert gs.last_search_kwargs.get("dashboard_uids") == ["dash-uid-1"]


@pytest.mark.asyncio
async def test_filtered_search_does_not_purge_non_matching_dashboards():
    db = _session()
    _seed_user_and_dashboard(db)
    db.add(
        GrafanaDashboard(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="dash-uid-2",
            grafana_id=102,
            title="Memory",
            visibility="private",
        )
    )
    db.commit()

    gs = _GrafanaServiceStub(
        search_results=[
            DashboardSearchResult(
                id=101,
                uid="dash-uid-1",
                title="CPU Overview",
                uri="db/cpu-overview",
                url="/d/dash-uid-1/cpu-overview",
                slug="cpu-overview",
                type="dash-db",
                tags=[],
                folderId=7,
                folderUid="folder-uid-7",
                folderTitle="Ops",
            )
        ]
    )
    service = _ProxyStub(gs)

    _ = await dashboard_ops.search_dashboards(
        service,
        db,
        user_id="u1",
        tenant_id="t1",
        group_ids=[],
        folder_uids=["folder-uid-7"],
    )

    still_present = db.query(GrafanaDashboard).filter_by(grafana_uid="dash-uid-2").first()
    assert still_present is not None


@pytest.mark.asyncio
async def test_general_dashboards_with_negative_folder_id_are_not_excluded():
    db = _session()
    _seed_user_and_dashboard(db)
    results = [
        DashboardSearchResult(
            id=101,
            uid="dash-uid-1",
            title="CPU Overview",
            uri="db/cpu-overview",
            url="/d/dash-uid-1/cpu-overview",
            slug="cpu-overview",
            type="dash-db",
            tags=[],
            folderId=-1,
            folderUid=None,
            folderTitle="General",
        )
    ]
    service = _ProxyStub(_GrafanaServiceStub(search_results=results))

    dashboards = await dashboard_ops.search_dashboards(
        service,
        db,
        user_id="u1",
        tenant_id="t1",
        group_ids=[],
        exclude_foldered_dashboards=True,
    )

    assert [d.uid for d in dashboards] == ["dash-uid-1"]


@pytest.mark.asyncio
async def test_search_dashboards_clears_stale_folder_uid_when_dashboard_moves_to_general():
    db = _session()
    _seed_user_and_dashboard(db)
    db_dash = db.query(GrafanaDashboard).filter_by(grafana_uid="dash-uid-1").first()
    db_dash.folder_uid = "stale-folder-uid"
    db.commit()

    results = [
        DashboardSearchResult(
            id=101,
            uid="dash-uid-1",
            title="CPU Overview",
            uri="db/cpu-overview",
            url="/d/dash-uid-1/cpu-overview",
            slug="cpu-overview",
            type="dash-db",
            tags=[],
            folderId=0,
            folderUid=None,
            folderTitle=None,
        )
    ]
    service = _ProxyStub(_GrafanaServiceStub(search_results=results))

    dashboards = await dashboard_ops.search_dashboards(
        service,
        db,
        user_id="u1",
        tenant_id="t1",
        group_ids=[],
        exclude_foldered_dashboards=True,
    )

    assert [d.uid for d in dashboards] == ["dash-uid-1"]
    refreshed = db.query(GrafanaDashboard).filter_by(grafana_uid="dash-uid-1").first()
    assert refreshed.folder_uid is None


@pytest.mark.asyncio
async def test_update_dashboard_clears_folder_uid_when_moved_to_general():
    db = _session()
    _seed_user_and_dashboard(db)
    dash = db.query(GrafanaDashboard).filter_by(grafana_uid="dash-uid-1").first()
    dash.folder_uid = "folder-uid-7"
    db.commit()

    service = _ProxyStub(_GrafanaServiceStub())
    update_payload = DashboardUpdate(
        dashboard=Dashboard(title="CPU Overview", tags=[]),
        folderId=0,
        overwrite=True,
    )

    updated = await dashboard_ops.update_dashboard(
        service,
        db,
        uid="dash-uid-1",
        dashboard_update=update_payload,
        user_id="u1",
        tenant_id="t1",
        group_ids=[],
    )

    assert updated is not None
    refreshed = db.query(GrafanaDashboard).filter_by(grafana_uid="dash-uid-1").first()
    assert refreshed.folder_uid is None
