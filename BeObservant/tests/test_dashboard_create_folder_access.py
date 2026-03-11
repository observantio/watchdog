"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/observantio_test")
os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "False")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

from db_models import Base, GrafanaFolder, Group, Tenant, User
from models.grafana.grafana_dashboard_models import Dashboard, DashboardCreate
from services.grafana import dashboard_ops


class _GrafanaServiceStub:
    def __init__(self):
        self._next_uid = 1

    async def search_dashboards(self, **kwargs):
        return []

    async def get_folders(self):
        return [
            SimpleNamespace(id=11, uid="f-tenant", title="Tenant Folder"),
            SimpleNamespace(id=12, uid="f-group", title="Group Folder"),
            SimpleNamespace(id=13, uid="f-private", title="Private Folder"),
        ]

    async def create_dashboard(self, dashboard_create):
        uid = f"dash-{self._next_uid}"
        self._next_uid += 1
        return {
            "id": 100 + self._next_uid,
            "uid": uid,
            "dashboard": {
                "uid": uid,
                "title": dashboard_create.dashboard.title,
                "tags": dashboard_create.dashboard.tags,
            },
            "folderUid": next(
                (f.uid for f in await self.get_folders() if f.id == dashboard_create.folder_id),
                None,
            ),
        }


class _ProxyStub:
    def __init__(self):
        self.grafana_service = _GrafanaServiceStub()
        self.logger = SimpleNamespace(debug=lambda *args, **kwargs: None)

    def _validate_group_visibility(self, db, *, user_id=None, tenant_id, group_ids, shared_group_ids, is_admin):
        return []

    def _raise_http_from_grafana_error(self, exc):
        raise exc


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _payload(folder_id: int) -> DashboardCreate:
    return DashboardCreate(
        dashboard=Dashboard(
            title="Team Dashboard",
            tags=["ops"],
            panels=[{"targets": [{"expr": "up"}], "datasource": {"uid": "ds-1"}}],
        ),
        folderId=folder_id,
        overwrite=False,
    )


@pytest.mark.asyncio
async def test_create_dashboard_allows_non_owner_in_tenant_folder():
    db = _session()
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
    member = User(
        id="u2",
        tenant_id="t1",
        username="member",
        email="member@example.com",
        hashed_password="x",
        org_id="org-a",
        is_active=True,
    )
    folder = GrafanaFolder(
        tenant_id="t1",
        created_by="u1",
        grafana_uid="f-tenant",
        grafana_id=11,
        title="Tenant Folder",
        visibility="tenant",
        allow_dashboard_writes=True,
    )
    db.add_all([tenant, owner, member, folder])
    db.commit()

    service = _ProxyStub()
    result = await dashboard_ops.create_dashboard(
        service,
        db,
        _payload(11),
        user_id="u2",
        tenant_id="t1",
        group_ids=[],
        visibility="private",
        shared_group_ids=[],
        is_admin=False,
    )
    assert result is not None
    assert result.get("created_by") == "u2"


@pytest.mark.asyncio
async def test_create_dashboard_allows_non_owner_in_shared_group_folder():
    db = _session()
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
    member = User(
        id="u2",
        tenant_id="t1",
        username="member",
        email="member@example.com",
        hashed_password="x",
        org_id="org-a",
        is_active=True,
    )
    team = Group(id="g1", tenant_id="t1", name="Team A")
    team.members.append(member)
    folder = GrafanaFolder(
        tenant_id="t1",
        created_by="u1",
        grafana_uid="f-group",
        grafana_id=12,
        title="Group Folder",
        visibility="group",
        allow_dashboard_writes=True,
    )
    folder.shared_groups.append(team)
    db.add_all([tenant, owner, member, team, folder])
    db.commit()

    service = _ProxyStub()
    result = await dashboard_ops.create_dashboard(
        service,
        db,
        _payload(12),
        user_id="u2",
        tenant_id="t1",
        group_ids=["g1"],
        visibility="private",
        shared_group_ids=[],
        is_admin=False,
    )
    assert result is not None
    assert result.get("created_by") == "u2"


@pytest.mark.asyncio
async def test_create_dashboard_still_denies_non_owner_in_private_folder():
    db = _session()
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
    member = User(
        id="u2",
        tenant_id="t1",
        username="member",
        email="member@example.com",
        hashed_password="x",
        org_id="org-a",
        is_active=True,
    )
    folder = GrafanaFolder(
        tenant_id="t1",
        created_by="u1",
        grafana_uid="f-private",
        grafana_id=13,
        title="Private Folder",
        visibility="private",
    )
    db.add_all([tenant, owner, member, folder])
    db.commit()

    service = _ProxyStub()
    with pytest.raises(HTTPException) as exc:
        await dashboard_ops.create_dashboard(
            service,
            db,
            _payload(13),
            user_id="u2",
            tenant_id="t1",
            group_ids=[],
            visibility="private",
            shared_group_ids=[],
            is_admin=False,
        )
    assert exc.value.status_code == 403
    assert "folder access denied" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_create_dashboard_denies_non_owner_in_tenant_folder_when_owner_only():
    db = _session()
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
    member = User(
        id="u2",
        tenant_id="t1",
        username="member",
        email="member@example.com",
        hashed_password="x",
        org_id="org-a",
        is_active=True,
    )
    folder = GrafanaFolder(
        tenant_id="t1",
        created_by="u1",
        grafana_uid="f-tenant",
        grafana_id=11,
        title="Tenant Folder",
        visibility="tenant",
        allow_dashboard_writes=False,
    )
    db.add_all([tenant, owner, member, folder])
    db.commit()

    service = _ProxyStub()
    with pytest.raises(HTTPException) as exc:
        await dashboard_ops.create_dashboard(
            service,
            db,
            _payload(11),
            user_id="u2",
            tenant_id="t1",
            group_ids=[],
            visibility="private",
            shared_group_ids=[],
            is_admin=False,
        )
    assert exc.value.status_code == 403
    assert "owner-only" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_create_dashboard_allows_delegated_folder_create_without_create_permission():
    db = _session()
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
    member = User(
        id="u2",
        tenant_id="t1",
        username="member",
        email="member@example.com",
        hashed_password="x",
        org_id="org-a",
        is_active=True,
    )
    folder = GrafanaFolder(
        tenant_id="t1",
        created_by="u1",
        grafana_uid="f-tenant",
        grafana_id=11,
        title="Tenant Folder",
        visibility="tenant",
        allow_dashboard_writes=True,
    )
    db.add_all([tenant, owner, member, folder])
    db.commit()

    service = _ProxyStub()
    result = await dashboard_ops.create_dashboard(
        service,
        db,
        _payload(11),
        user_id="u2",
        tenant_id="t1",
        group_ids=[],
        visibility="private",
        shared_group_ids=[],
        is_admin=False,
        actor_permissions=["read:dashboards"],
    )
    assert result is not None
    assert result.get("created_by") == "u2"


@pytest.mark.asyncio
async def test_create_dashboard_denies_without_create_permission_when_not_delegated():
    db = _session()
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
    member = User(
        id="u2",
        tenant_id="t1",
        username="member",
        email="member@example.com",
        hashed_password="x",
        org_id="org-a",
        is_active=True,
    )
    folder = GrafanaFolder(
        tenant_id="t1",
        created_by="u1",
        grafana_uid="f-tenant",
        grafana_id=11,
        title="Tenant Folder",
        visibility="tenant",
        allow_dashboard_writes=False,
    )
    db.add_all([tenant, owner, member, folder])
    db.commit()

    service = _ProxyStub()
    with pytest.raises(HTTPException) as exc:
        await dashboard_ops.create_dashboard(
            service,
            db,
            _payload(11),
            user_id="u2",
            tenant_id="t1",
            group_ids=[],
            visibility="private",
            shared_group_ids=[],
            is_admin=False,
            actor_permissions=["read:dashboards"],
        )
    assert exc.value.status_code == 403
