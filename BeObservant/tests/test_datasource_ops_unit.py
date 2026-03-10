"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests._env import ensure_test_env

ensure_test_env()

from db_models import ApiKeyShare, Base, GrafanaDatasource, Group, Tenant, User, UserApiKey
from models.grafana.grafana_datasource_models import DatasourceCreate, DatasourceUpdate
from services.grafana import datasource_ops
from services.grafana.grafana_service import GrafanaAPIError


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class FakeGrafanaDatasource:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def model_dump(self):
        return dict(self.__dict__)


class GrafanaServiceStub:
    def __init__(self):
        self.items = {}
        self.by_name = {}
        self.create_calls = []
        self.update_calls = []
        self.delete_calls = []
        self.query_result = {"ok": True}
        self.create_errors = []
        self.update_errors = []

    async def get_datasources(self):
        return list(self.items.values())

    async def get_datasource(self, uid):
        return self.items.get(uid)

    async def get_datasource_by_name(self, name):
        return self.by_name.get(name)

    async def create_datasource(self, payload):
        self.create_calls.append(payload)
        if self.create_errors:
            raise self.create_errors.pop(0)
        result = FakeGrafanaDatasource(
            id=101,
            uid="uid-created",
            orgId=1,
            name=payload.name,
            type=payload.type,
            url=payload.url,
            access=payload.access,
            isDefault=False,
            readOnly=False,
            jsonData=getattr(payload, "json_data", None),
            secureJsonData=getattr(payload, "secure_json_data", None),
        )
        self.items[result.uid] = result
        self.by_name[result.name] = result
        return result

    async def update_datasource(self, uid, payload):
        self.update_calls.append((uid, payload))
        if self.update_errors:
            raise self.update_errors.pop(0)
        current = self.items[uid]
        for key in ["name", "url", "access"]:
            value = getattr(payload, key, None)
            if value is not None:
                setattr(current, key, value)
        if getattr(payload, "json_data", None) is not None:
            current.jsonData = payload.json_data
        if getattr(payload, "secure_json_data", None) is not None:
            current.secureJsonData = payload.secure_json_data
        return current

    async def delete_datasource(self, uid):
        self.delete_calls.append(uid)
        return self.items.pop(uid, None) is not None

    async def query_datasource(self, payload):
        return self.query_result


def _service(stub):
    def _validate_group_visibility(db, *, shared_group_ids, **kwargs):
        return db.query(Group).filter(Group.id.in_(shared_group_ids or [])).all()

    def _raise_http_from_grafana_error(exc):
        raise HTTPException(status_code=exc.status, detail=str(exc.body))

    return SimpleNamespace(
        grafana_service=stub,
        _validate_group_visibility=_validate_group_visibility,
        _raise_http_from_grafana_error=_raise_http_from_grafana_error,
    )


def _seed(db):
    tenant = Tenant(id="t1", name="tenant-1", display_name="Tenant 1", is_active=True)
    tenant2 = Tenant(id="t2", name="tenant-2", display_name="Tenant 2", is_active=True)
    owner = User(id="u1", tenant_id="t1", username="owner", email="owner@example.com", hashed_password="x", org_id="org-owner", is_active=True)
    viewer = User(id="u2", tenant_id="t1", username="viewer", email="viewer@example.com", hashed_password="x", org_id="org-viewer", is_active=True)
    outsider = User(id="u3", tenant_id="t1", username="outsider", email="outsider@example.com", hashed_password="x", org_id="org-outsider", is_active=True)
    foreign = User(id="u4", tenant_id="t2", username="foreign", email="foreign@example.com", hashed_password="x", org_id="foreign-org", is_active=True)
    group = Group(id="g1", tenant_id="t1", name="Ops", is_active=True)
    group.members.append(viewer)
    key_owned = UserApiKey(id="k1", tenant_id="t1", user_id="u1", name="owned", key="scope-owned", is_enabled=False, is_default=False)
    key_shared = UserApiKey(id="k2", tenant_id="t1", user_id="u1", name="shared", key="scope-shared", is_enabled=False, is_default=False)
    key_foreign = UserApiKey(id="k3", tenant_id="t2", user_id="u4", name="foreign", key="scope-collide", is_enabled=True, is_default=False)
    share = ApiKeyShare(id="s1", tenant_id="t1", api_key_id="k2", owner_user_id="u1", shared_user_id="u2", can_use=True)
    ds_private = GrafanaDatasource(id="d1", tenant_id="t1", created_by="u1", grafana_uid="uid-private", grafana_id=11, name="Private", type="prometheus", visibility="private", hidden_by=[])
    ds_group = GrafanaDatasource(id="d2", tenant_id="t1", created_by="u1", grafana_uid="uid-group", grafana_id=12, name="Grouped", type="loki", visibility="group", hidden_by=["u3"])
    ds_group.shared_groups.append(group)
    ds_tenant = GrafanaDatasource(id="d3", tenant_id="t1", created_by="u1", grafana_uid="uid-tenant", grafana_id=13, name="TenantWide", type="tempo", visibility="tenant", hidden_by=[])
    db.add_all([tenant, tenant2, owner, viewer, outsider, foreign, group, key_owned, key_shared, key_foreign, share, ds_private, ds_group, ds_tenant])
    db.commit()
    return owner, viewer, outsider, group, ds_private, ds_group, ds_tenant


def test_datasource_helper_functions(monkeypatch):
    assert datasource_ops._cap(None, -5)[1] == 0
    assert datasource_ops._sanitize_datasource_payload({"password": "p", "basicAuthPassword": "b", "secureJsonData": {"x": 1}}, is_owner=False)["password"] is None
    assert datasource_ops._sanitize_datasource_payload({"password": "p"}, is_owner=True)["password"] == "p"
    assert datasource_ops._is_safe_system_datasource(SimpleNamespace(is_default=True)) is True
    assert datasource_ops._is_safe_system_datasource(SimpleNamespace(readOnly=True)) is True
    assert datasource_ops._normalize_name("  TeSt ") == "test"
    monkeypatch.setattr(uuid, "uuid4", lambda: SimpleNamespace(hex="abcdef123456"))
    assert datasource_ops._build_internal_name("Display", "user-12345678").startswith("Display__bo_user-123_")


def test_datasource_access_scope_and_metadata_helpers():
    db = _session()
    owner, viewer, outsider, group, ds_private, ds_group, ds_tenant = _seed(db)

    assert datasource_ops._db_datasource_by_uid(db, "t1", ds_private.grafana_uid).id == ds_private.id
    default_scope, scopes = datasource_ops._load_allowed_scope_org_ids(db, user_id=viewer.id, tenant_id="t1")
    assert default_scope == viewer.org_id
    assert "scope-shared" in scopes
    assert datasource_ops._scope_conflicts_with_other_tenants(db, org_id="scope-collide", tenant_id="t1") is True

    assert datasource_ops.check_datasource_access(db, ds_private.grafana_uid, owner.id, "t1", []) is not None
    assert datasource_ops.check_datasource_access(db, ds_private.grafana_uid, viewer.id, "t1", [group.id]) is None
    assert datasource_ops.check_datasource_access(db, ds_group.grafana_uid, viewer.id, "t1", [group.id]).id == ds_group.id
    assert datasource_ops.check_datasource_access(db, ds_group.grafana_uid, viewer.id, "t1", [group.id], require_write=True) is None
    assert datasource_ops.check_datasource_access_by_id(db, ds_tenant.grafana_id, viewer.id, "t1", []).id == ds_tenant.id

    accessible, allow_system = datasource_ops.get_accessible_datasource_uids(SimpleNamespace(), db, viewer.id, "t1", [group.id])
    assert set(accessible) == {"uid-group", "uid-tenant"}
    assert allow_system is True
    context = datasource_ops.build_datasource_list_context(SimpleNamespace(), db, tenant_id="t1")
    assert "uid-private" in context["db_entries"]
    assert datasource_ops.collect_datasource_refs_from_query_payload({"queries": [{"datasourceUid": "uid-group"}, {"datasource": {"uid": "uid-tenant"}}]}) == {"uid-group", "uid-tenant"}
    assert datasource_ops.toggle_datasource_hidden(db, ds_group.grafana_uid, viewer.id, "t1", True) is True
    assert viewer.id in db.query(GrafanaDatasource).filter_by(id=ds_group.id).first().hidden_by
    assert datasource_ops.get_datasource_metadata(db, "t1") == {"team_ids": [group.id]}


def test_enforce_query_access_and_read_paths():
    db = _session()
    owner, viewer, outsider, group, ds_private, ds_group, ds_tenant = _seed(db)
    stub = GrafanaServiceStub()
    stub.items = {
        "uid-private": FakeGrafanaDatasource(id=11, uid="uid-private", name="Private", type="prometheus", url="http://x", access="proxy", isDefault=False, readOnly=False),
        "uid-group": FakeGrafanaDatasource(id=12, uid="uid-group", name="Grouped", type="loki", url="http://x", access="proxy", isDefault=False, readOnly=False),
        "uid-tenant": FakeGrafanaDatasource(id=13, uid="uid-tenant", name="TenantWide", type="tempo", url="http://x", access="proxy", isDefault=False, readOnly=False),
        "uid-system": FakeGrafanaDatasource(id=14, uid="uid-system", name="System", type="prometheus", url="http://x", access="proxy", isDefault=True, readOnly=False),
    }
    stub.by_name = {"Grouped": stub.items["uid-group"]}
    service = _service(stub)

    asyncio.run(datasource_ops.enforce_datasource_query_access(service, db, viewer.id, "t1", [group.id], "/api/ds/query", "GET", {}))
    asyncio.run(datasource_ops.enforce_datasource_query_access(service, db, viewer.id, "t1", [group.id], "/api/ds/query", "POST", {"queries": [{"datasourceUid": "uid-group"}]}))
    asyncio.run(datasource_ops.enforce_datasource_query_access(service, db, viewer.id, "t1", [group.id], "/api/datasources/proxy/14", "POST", {}))

    with pytest.raises(HTTPException, match="access denied"):
        asyncio.run(datasource_ops.enforce_datasource_query_access(service, db, outsider.id, "t1", [], "/api/ds/query", "POST", {"queries": [{"datasourceUid": "uid-group"}]}))

    visible = asyncio.run(datasource_ops.get_datasources(service, db, viewer.id, "t1", [group.id]))
    assert {item.uid for item in visible} == {"uid-group", "uid-tenant", "uid-system"}
    hidden_filtered = asyncio.run(datasource_ops.get_datasources(service, db, outsider.id, "t1", [group.id]))
    assert all(item.uid != "uid-group" for item in hidden_filtered)
    grouped_only = asyncio.run(datasource_ops.get_datasources(service, db, viewer.id, "t1", [group.id], team_id=group.id))
    assert [item.uid for item in grouped_only] == ["uid-group"]
    single = asyncio.run(datasource_ops.get_datasources(service, db, viewer.id, "t1", [group.id], uid="uid-group"))
    assert single[0].uid == "uid-group"
    assert asyncio.run(datasource_ops.get_datasource(service, db, "uid-private", viewer.id, "t1", [group.id])) is None
    assert asyncio.run(datasource_ops.get_datasource_by_name(service, db, "Grouped", viewer.id, "t1", [group.id])).uid == "uid-group"
    assert asyncio.run(datasource_ops.query_datasource(service, {"a": 1})) == {"ok": True}
    stub.query_result = [1]
    assert asyncio.run(datasource_ops.query_datasource(service, {"a": 1})) == {}


def test_create_update_and_delete_datasource_branches(monkeypatch):
    db = _session()
    owner, viewer, outsider, group, ds_private, ds_group, ds_tenant = _seed(db)
    stub = GrafanaServiceStub()
    stub.items = {
        "uid-existing": FakeGrafanaDatasource(id=21, uid="uid-existing", name="Existing", type="prometheus", url="http://x", access="proxy", isDefault=False, readOnly=False),
        "uid-group": FakeGrafanaDatasource(id=12, uid="uid-group", name="Grouped", type="loki", url="http://x", access="proxy", isDefault=False, readOnly=False),
    }
    service = _service(stub)
    monkeypatch.setattr(datasource_ops.uuid, "uuid4", lambda: SimpleNamespace(hex="abcdef123456"))

    with pytest.raises(HTTPException, match="already exists"):
        asyncio.run(
            datasource_ops.create_datasource(
                service,
                db,
                DatasourceCreate(name="Grouped", type="graphite", url="http://new"),
                viewer.id,
                "t1",
                [group.id],
            )
        )

    stub.create_errors = [GrafanaAPIError(409, {"message": "dup"})]
    created = asyncio.run(
        datasource_ops.create_datasource(
            service,
            db,
            DatasourceCreate(name="Metrics", type="prometheus", url="http://new", orgId="scope-shared"),
            viewer.id,
            "t1",
            [group.id],
            visibility="group",
            shared_group_ids=[group.id],
        )
    )
    assert created.name == "Metrics"
    assert created.visibility == "group"
    assert created.shared_group_ids == [group.id]
    assert stub.create_calls[-1].name.startswith("Metrics__bo_")

    db_owned = db.query(GrafanaDatasource).filter_by(grafana_uid="uid-created").first()
    assert db_owned is not None
    stub.items["uid-created"] = FakeGrafanaDatasource(id=101, uid="uid-created", name="Metrics", type="prometheus", url="http://new", access="proxy", isDefault=False, readOnly=False, jsonData={}, secureJsonData={})

    with pytest.raises(HTTPException, match="cannot be modified"):
        stub.items["uid-created"].isDefault = True
        asyncio.run(datasource_ops.update_datasource(service, db, "uid-created", DatasourceUpdate(name="Nope"), viewer.id, "t1", [group.id]))
    stub.items["uid-created"].isDefault = False

    stub.update_errors = [GrafanaAPIError(409, {"message": "dup"})]
    updated = asyncio.run(
        datasource_ops.update_datasource(
            service,
            db,
            "uid-created",
            DatasourceUpdate(name="Renamed", orgId="scope-shared"),
            viewer.id,
            "t1",
            [group.id],
            visibility="tenant",
        )
    )
    assert updated.name == "Renamed"
    assert updated.visibility == "tenant"
    assert db.query(GrafanaDatasource).filter_by(grafana_uid="uid-created").first().visibility == "tenant"

    assert asyncio.run(datasource_ops.delete_datasource(service, db, "missing", viewer.id, "t1", [group.id])) is False
    stub.items["uid-created"].readOnly = True
    with pytest.raises(HTTPException, match="cannot be deleted"):
        asyncio.run(datasource_ops.delete_datasource(service, db, "uid-created", viewer.id, "t1", [group.id]))
    stub.items["uid-created"].readOnly = False
    assert asyncio.run(datasource_ops.delete_datasource(service, db, "uid-created", viewer.id, "t1", [group.id])) is True
