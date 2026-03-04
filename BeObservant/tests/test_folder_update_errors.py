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
    async def update_folder(self, uid, title):
        raise GrafanaAPIError(412, {"message": "the folder has been changed by someone else"})


class _ProxyStub:
    def __init__(self):
        self.grafana_service = _GrafanaServiceStub()

    def _validate_group_visibility(self, db, *, tenant_id, group_ids, shared_group_ids, is_admin):
        return []

    def _raise_http_from_grafana_error(self, exc):
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
