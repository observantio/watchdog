import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/observantio_test")
os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "False")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

from db_models import Base, GrafanaDashboard, GrafanaFolder, Tenant, User
from models.grafana.grafana_dashboard_models import Dashboard, DashboardUpdate
from services.grafana import dashboard_ops


class _GrafanaServiceStub:
    async def search_dashboards(self, **kwargs):
        return [SimpleNamespace(uid="d1")]

    async def update_dashboard(self, uid, payload):
        dash = getattr(payload, "dashboard", None)
        return {
            "uid": uid,
            "dashboard": {
                "uid": uid,
                "title": getattr(dash, "title", "Updated"),
                "tags": getattr(dash, "tags", []),
            },
        }

    async def get_folders(self):
        return [
            SimpleNamespace(id=11, uid="f-collab", title="Collaborative"),
            SimpleNamespace(id=12, uid="f-other", title="Other"),
        ]


class _ProxyStub:
    def __init__(self):
        self.grafana_service = _GrafanaServiceStub()

    def _validate_group_visibility(self, *args, **kwargs):
        return []

    def _raise_http_from_grafana_error(self, exc):
        raise exc


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _update_payload(title: str = "Updated by collaborator", folder_id=None):
    return DashboardUpdate(
        dashboard=Dashboard(
            uid="d1",
            title=title,
            tags=["ops"],
            panels=[{"targets": [{"expr": "up"}], "datasource": {"uid": "ds-1"}}],
        ),
        folderId=folder_id,
        overwrite=True,
    )


@pytest.mark.asyncio
async def test_non_owner_can_update_dashboard_when_folder_allows_dashboard_writes():
    db = _session()
    db.add_all([
        Tenant(id="t1", name="tenant-1", display_name="Tenant 1"),
        User(id="u1", tenant_id="t1", username="owner", email="o@example.com", hashed_password="x", org_id="org", is_active=True),
        User(id="u2", tenant_id="t1", username="member", email="m@example.com", hashed_password="x", org_id="org", is_active=True),
        GrafanaFolder(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="f-collab",
            grafana_id=11,
            title="Collaborative",
            visibility="tenant",
            allow_dashboard_writes=True,
        ),
        GrafanaDashboard(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="d1",
            grafana_id=101,
            title="Original",
            visibility="private",
            folder_uid="f-collab",
        ),
    ])
    db.commit()

    service = _ProxyStub()
    result = await dashboard_ops.update_dashboard(
        service,
        db,
        uid="d1",
        dashboard_update=_update_payload(),
        user_id="u2",
        tenant_id="t1",
        group_ids=[],
        visibility=None,
        shared_group_ids=None,
        is_admin=False,
        actor_permissions=["read:dashboards"],
    )
    assert result is not None
    row = db.query(GrafanaDashboard).filter_by(grafana_uid="d1", tenant_id="t1").first()
    assert row is not None
    assert row.title == "Updated by collaborator"


@pytest.mark.asyncio
async def test_non_owner_cannot_change_visibility_when_delegated_update_enabled():
    db = _session()
    db.add_all([
        Tenant(id="t1", name="tenant-1", display_name="Tenant 1"),
        User(id="u1", tenant_id="t1", username="owner", email="o@example.com", hashed_password="x", org_id="org", is_active=True),
        User(id="u2", tenant_id="t1", username="member", email="m@example.com", hashed_password="x", org_id="org", is_active=True),
        GrafanaFolder(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="f-collab",
            grafana_id=11,
            title="Collaborative",
            visibility="tenant",
            allow_dashboard_writes=True,
        ),
        GrafanaDashboard(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="d1",
            grafana_id=101,
            title="Original",
            visibility="private",
            folder_uid="f-collab",
        ),
    ])
    db.commit()

    service = _ProxyStub()
    with pytest.raises(HTTPException) as exc:
        await dashboard_ops.update_dashboard(
            service,
            db,
            uid="d1",
            dashboard_update=_update_payload(),
            user_id="u2",
            tenant_id="t1",
            group_ids=[],
            visibility="tenant",
            shared_group_ids=[],
            is_admin=False,
            actor_permissions=["read:dashboards"],
        )
    assert exc.value.status_code == 403
    assert "owners can change dashboard visibility" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_non_owner_cannot_move_dashboard_to_other_folder_when_delegated_update_enabled():
    db = _session()
    db.add_all([
        Tenant(id="t1", name="tenant-1", display_name="Tenant 1"),
        User(id="u1", tenant_id="t1", username="owner", email="o@example.com", hashed_password="x", org_id="org", is_active=True),
        User(id="u2", tenant_id="t1", username="member", email="m@example.com", hashed_password="x", org_id="org", is_active=True),
        GrafanaFolder(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="f-collab",
            grafana_id=11,
            title="Collaborative",
            visibility="tenant",
            allow_dashboard_writes=True,
        ),
        GrafanaFolder(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="f-other",
            grafana_id=12,
            title="Other",
            visibility="tenant",
            allow_dashboard_writes=True,
        ),
        GrafanaDashboard(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="d1",
            grafana_id=101,
            title="Original",
            visibility="private",
            folder_uid="f-collab",
        ),
    ])
    db.commit()

    service = _ProxyStub()
    with pytest.raises(HTTPException) as exc:
        await dashboard_ops.update_dashboard(
            service,
            db,
            uid="d1",
            dashboard_update=_update_payload(folder_id=12),
            user_id="u2",
            tenant_id="t1",
            group_ids=[],
            visibility=None,
            shared_group_ids=None,
            is_admin=False,
            actor_permissions=["read:dashboards"],
        )
    assert exc.value.status_code == 403
    assert "owners can move dashboards" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_dashboard_owner_can_update_in_shared_folder_when_writes_enabled():
    db = _session()
    db.add_all([
        Tenant(id="t1", name="tenant-1", display_name="Tenant 1"),
        User(id="u1", tenant_id="t1", username="folder-owner", email="o@example.com", hashed_password="x", org_id="org", is_active=True),
        User(id="u2", tenant_id="t1", username="member", email="m@example.com", hashed_password="x", org_id="org", is_active=True),
        GrafanaFolder(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="f-collab",
            grafana_id=11,
            title="Collaborative",
            visibility="tenant",
            allow_dashboard_writes=True,
        ),
        GrafanaDashboard(
            tenant_id="t1",
            created_by="u2",
            grafana_uid="d1",
            grafana_id=101,
            title="Original",
            visibility="private",
            folder_uid="f-collab",
        ),
    ])
    db.commit()

    service = _ProxyStub()
    result = await dashboard_ops.update_dashboard(
        service,
        db,
        uid="d1",
        dashboard_update=_update_payload(title="Owner edits own dashboard"),
        user_id="u2",
        tenant_id="t1",
        group_ids=[],
        visibility="private",
        shared_group_ids=[],
        is_admin=False,
        actor_permissions=["update:dashboards"],
    )
    assert result is not None
    row = db.query(GrafanaDashboard).filter_by(grafana_uid="d1", tenant_id="t1").first()
    assert row is not None
    assert row.title == "Owner edits own dashboard"


@pytest.mark.asyncio
async def test_non_owner_update_accepts_unchanged_visibility_query_params():
    db = _session()
    db.add_all([
        Tenant(id="t1", name="tenant-1", display_name="Tenant 1"),
        User(id="u1", tenant_id="t1", username="owner", email="o@example.com", hashed_password="x", org_id="org", is_active=True),
        User(id="u2", tenant_id="t1", username="member", email="m@example.com", hashed_password="x", org_id="org", is_active=True),
        GrafanaFolder(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="f-collab",
            grafana_id=11,
            title="Collaborative",
            visibility="tenant",
            allow_dashboard_writes=True,
        ),
        GrafanaDashboard(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="d1",
            grafana_id=101,
            title="Original",
            visibility="private",
            folder_uid="f-collab",
        ),
    ])
    db.commit()

    service = _ProxyStub()
    result = await dashboard_ops.update_dashboard(
        service,
        db,
        uid="d1",
        dashboard_update=_update_payload(title="Member edit with default visibility"),
        user_id="u2",
        tenant_id="t1",
        group_ids=[],
        visibility="private",
        shared_group_ids=[],
        is_admin=False,
        actor_permissions=["read:dashboards"],
    )
    assert result is not None
    row = db.query(GrafanaDashboard).filter_by(grafana_uid="d1", tenant_id="t1").first()
    assert row is not None
    assert row.title == "Member edit with default visibility"
