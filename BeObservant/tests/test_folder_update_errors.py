"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import os

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/observantio_test")
os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "False")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

from db_models import Base, GrafanaFolder, Tenant, User
from services.grafana import folder_ops
from services.grafana.grafana_service import GrafanaAPIError


class _GrafanaServiceStub:
    async def create_folder(self, title):
        raise GrafanaAPIError(400, {"message": "Folder name cannot be the same as one of its dashboards"})

    async def update_folder(self, uid, title):
        raise GrafanaAPIError(412, {"message": "the folder has been changed by someone else"})


class _ProxyStub:
    def __init__(self):
        self.grafana_service = _GrafanaServiceStub()

    def _validate_group_visibility(self, db, *, user_id=None, tenant_id, group_ids, shared_group_ids, is_admin):
        return []

    def _raise_http_from_grafana_error(self, exc):
        if isinstance(exc, GrafanaAPIError):
            detail = (
                (isinstance(exc.body, dict) and (exc.body.get("message") or exc.body.get("error") or exc.body.get("detail")))
                or (isinstance(exc.body, str) and exc.body)
                or "Grafana API error"
            )
            raise HTTPException(status_code=exc.status, detail=detail)
        raise exc


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


@pytest.mark.asyncio
async def test_update_folder_maps_412_to_409():
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
            title="Ops",
            visibility="private",
        ),
    ])
    db.commit()

    service = _ProxyStub()

    with pytest.raises(HTTPException) as exc:
        await folder_ops.update_folder(
            service,
            db,
            uid="f1",
            user_id="u1",
            tenant_id="t1",
            group_ids=[],
            title="Ops",
            visibility="private",
            shared_group_ids=[],
            is_admin=False,
        )

    assert exc.value.status_code == 409
    assert "retry" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_create_folder_maps_grafana_400_to_http_400_with_message():
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
    ])
    db.commit()

    service = _ProxyStub()

    with pytest.raises(HTTPException) as exc:
        await folder_ops.create_folder(
            service,
            db,
            title="Duplicate title",
            user_id="u1",
            tenant_id="t1",
            group_ids=[],
            visibility="private",
            shared_group_ids=[],
            is_admin=False,
        )

    assert exc.value.status_code == 400
    assert "cannot be the same" in str(exc.value.detail).lower()
