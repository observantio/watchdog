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

from db_models import Base, GrafanaFolder, Tenant, User
from services.grafana import folder_ops


class _GrafanaServiceStub:
    async def get_folders(self):
        return [SimpleNamespace(id=10, uid="f1", title="Folder 1")]


class _ProxyStub:
    def __init__(self):
        self.grafana_service = _GrafanaServiceStub()


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


@pytest.mark.asyncio
async def test_get_folders_hides_user_hidden_folder_by_default():
    db = _session()
    db.add_all([
        Tenant(id="t1", name="tenant-1", display_name="Tenant 1"),
        User(
            id="u1",
            tenant_id="t1",
            username="owner",
            email="owner@example.com",
            hashed_password="x",
            org_id="org-a",
            is_active=True,
        ),
        User(
            id="u2",
            tenant_id="t1",
            username="member",
            email="member@example.com",
            hashed_password="x",
            org_id="org-a",
            is_active=True,
        ),
        GrafanaFolder(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="f1",
            grafana_id=10,
            title="Folder 1",
            visibility="tenant",
            hidden_by=["u2"],
        ),
    ])
    db.commit()

    service = _ProxyStub()
    result = await folder_ops.get_folders(
        service,
        db,
        user_id="u2",
        tenant_id="t1",
        group_ids=[],
        show_hidden=False,
        is_admin=False,
    )
    assert result == []


@pytest.mark.asyncio
async def test_get_folders_can_include_hidden():
    db = _session()
    db.add_all([
        Tenant(id="t1", name="tenant-1", display_name="Tenant 1"),
        User(
            id="u1",
            tenant_id="t1",
            username="owner",
            email="owner@example.com",
            hashed_password="x",
            org_id="org-a",
            is_active=True,
        ),
        User(
            id="u2",
            tenant_id="t1",
            username="member",
            email="member@example.com",
            hashed_password="x",
            org_id="org-a",
            is_active=True,
        ),
        GrafanaFolder(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="f1",
            grafana_id=10,
            title="Folder 1",
            visibility="tenant",
            hidden_by=["u2"],
        ),
    ])
    db.commit()

    service = _ProxyStub()
    result = await folder_ops.get_folders(
        service,
        db,
        user_id="u2",
        tenant_id="t1",
        group_ids=[],
        show_hidden=True,
        is_admin=False,
    )
    assert len(result) == 1
    assert result[0].is_hidden is True


def test_toggle_folder_hidden_rejects_hiding_own_folder():
    db = _session()
    db.add_all([
        Tenant(id="t1", name="tenant-1", display_name="Tenant 1"),
        User(
            id="u1",
            tenant_id="t1",
            username="owner",
            email="owner@example.com",
            hashed_password="x",
            org_id="org-a",
            is_active=True,
        ),
        GrafanaFolder(
            tenant_id="t1",
            created_by="u1",
            grafana_uid="f1",
            grafana_id=10,
            title="Folder 1",
            visibility="tenant",
            hidden_by=[],
        ),
    ])
    db.commit()

    with pytest.raises(HTTPException) as exc:
        folder_ops.toggle_folder_hidden(db, "f1", "u1", "t1", True)
    assert exc.value.status_code == 400
    assert "cannot hide folders you own" in str(exc.value.detail).lower()
