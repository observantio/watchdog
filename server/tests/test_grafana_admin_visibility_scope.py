from tests._env import ensure_test_env
ensure_test_env()

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from models.access.auth_models import Role, TokenData
from models.grafana.grafana_datasource_models import Datasource
from services.grafana import dashboard_ops, datasource_ops, proxy_auth_ops
import services.grafana_proxy_service as gps_mod
from services.grafana_proxy_service import GrafanaProxyService


class _DummyDashboardResult:
    def __init__(self, uid: str, title: str):
        self.uid = uid
        self.title = title

    def model_dump(self):
        return {
            "id": 1,
            "uid": self.uid,
            "title": self.title,
            "uri": f"db/{self.uid}",
            "url": f"/d/{self.uid}",
            "slug": self.uid,
            "type": "dash-db",
            "tags": [],
            "isStarred": False,
            "folderId": None,
            "folderUid": None,
            "folderTitle": None,
        }


class _QueryStub:
    def filter(self, *args, **kwargs):
        return self

    def with_entities(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return []


@pytest.mark.asyncio
async def test_admin_dashboard_search_still_uses_visibility_scope():
    service = SimpleNamespace(
        grafana_service=SimpleNamespace(
            search_dashboards=AsyncMock(
                return_value=[
                    _DummyDashboardResult("allowed", "Allowed"),
                    _DummyDashboardResult("blocked", "Blocked"),
                ]
            )
        )
    )
    original = dashboard_ops.get_accessible_dashboard_uids
    dashboard_ops.get_accessible_dashboard_uids = lambda *args, **kwargs: (["allowed"], False)
    try:
        results = await dashboard_ops.search_dashboards(
            service,
            db=object(),
            user_id="admin-user",
            tenant_id="tenant-1",
            group_ids=[],
            is_admin=True,
            search_context={"all_registered_uids": {"allowed", "blocked"}, "db_dashboards": {}},
        )
    finally:
        dashboard_ops.get_accessible_dashboard_uids = original

    assert [r.uid for r in results] == ["allowed"]


def test_accessible_uids_do_not_allow_unregistered_system_dashboards():
    result_uids, allow_system = dashboard_ops.get_accessible_dashboard_uids(
        service=SimpleNamespace(),
        db=SimpleNamespace(query=lambda *args, **kwargs: _QueryStub()),
        user_id="u1",
        tenant_id="t1",
        group_ids=[],
    )
    assert result_uids == []
    assert allow_system is False


@pytest.mark.asyncio
async def test_admin_datasource_list_still_uses_visibility_scope():
    service = SimpleNamespace(
        grafana_service=SimpleNamespace(
            get_datasources=AsyncMock(
                return_value=[
                    Datasource(uid="allowed", name="Allowed DS", type="loki", url="http://loki"),
                    Datasource(uid="blocked", name="Blocked DS", type="tempo", url="http://tempo"),
                ]
            )
        )
    )
    original = datasource_ops.get_accessible_datasource_uids
    datasource_ops.get_accessible_datasource_uids = lambda *args, **kwargs: (["allowed"], False)
    try:
        results = await datasource_ops.get_datasources(
            service,
            db=object(),
            user_id="admin-user",
            tenant_id="tenant-1",
            group_ids=[],
            is_admin=True,
            datasource_context={"all_registered_uids": {"allowed", "blocked"}, "db_entries": {}},
        )
    finally:
        datasource_ops.get_accessible_datasource_uids = original

    assert [d.uid for d in results] == ["allowed"]


def test_accessible_uids_allow_system_fallback_but_not_implicit_uids():
    result_uids, allow_system = datasource_ops.get_accessible_datasource_uids(
        service=SimpleNamespace(),
        db=SimpleNamespace(query=lambda *args, **kwargs: _QueryStub()),
        user_id="u1",
        tenant_id="t1",
        group_ids=[],
    )
    assert result_uids == []
    assert allow_system is True


@pytest.mark.asyncio
async def test_datasource_list_only_includes_safe_unregistered_system_datasources():
    service = SimpleNamespace(
        grafana_service=SimpleNamespace(
            get_datasources=AsyncMock(
                return_value=[
                    Datasource(uid="default-safe", name="Default DS", type="prometheus", url="http://prom", isDefault=True),
                    Datasource(uid="read-only-safe", name="ReadOnly DS", type="loki", url="http://loki", readOnly=True),
                    Datasource(uid="unsafe", name="Unsafe DS", type="tempo", url="http://tempo"),
                ]
            )
        )
    )
    original = datasource_ops.get_accessible_datasource_uids
    datasource_ops.get_accessible_datasource_uids = lambda *args, **kwargs: ([], True)
    try:
        results = await datasource_ops.get_datasources(
            service,
            db=object(),
            user_id="user-1",
            tenant_id="tenant-1",
            group_ids=[],
            datasource_context={"all_registered_uids": set(), "db_entries": {}},
        )
    finally:
        datasource_ops.get_accessible_datasource_uids = original

    assert [d.uid for d in results] == ["default-safe", "read-only-safe"]


def test_admin_cannot_access_other_users_private_resource_in_proxy_checks():
    token_data = TokenData(
        user_id="admin-user",
        username="admin",
        role=Role.ADMIN,
        tenant_id="tenant-1",
        org_id="org-1",
        permissions=[],
        group_ids=[],
        is_superuser=False,
    )
    private_resource = SimpleNamespace(
        tenant_id="tenant-1",
        created_by="other-user",
        visibility="private",
        hidden_by=[],
        shared_groups=[],
    )
    tenant_resource = SimpleNamespace(
        tenant_id="tenant-1",
        created_by="other-user",
        visibility="tenant",
        hidden_by=[],
        shared_groups=[],
    )

    assert proxy_auth_ops.is_resource_accessible(SimpleNamespace(), private_resource, token_data) is False
    assert proxy_auth_ops.is_resource_accessible(SimpleNamespace(), tenant_resource, token_data) is True


@pytest.mark.asyncio
async def test_proxy_service_enforces_datasource_query_access_for_admin():
    svc = GrafanaProxyService()
    original = gps_mod.enforce_datasource_query_access
    probe = AsyncMock()
    gps_mod.enforce_datasource_query_access = probe
    try:
        await svc.enforce_datasource_query_access(
            db=object(),
            payload={"queries": []},
            user_id="admin-user",
            tenant_id="tenant-1",
            group_ids=[],
            is_admin=True,
        )
    finally:
        gps_mod.enforce_datasource_query_access = original

    assert probe.await_count == 1


@pytest.mark.asyncio
async def test_proxy_denies_unregistered_dashboard_even_for_admin():
    token_data = TokenData(
        user_id="admin-user",
        username="admin",
        role=Role.ADMIN,
        tenant_id="tenant-1",
        org_id="org-1",
        permissions=["read:dashboards"],
        group_ids=[],
        is_superuser=False,
    )

    class _Auth:
        def decode_token(self, _token):
            return token_data

        def get_user_by_id(self, _user_id):
            return SimpleNamespace(is_active=True, org_id="org-1", groups=[])

        def get_user_permissions(self, _user):
            return ["read:dashboards"]

    class _Req:
        headers = {"X-Original-URI": "/grafana/d/unknown-uid/test", "X-Original-Method": "GET"}
        cookies = {}
        method = "GET"

    class _DB:
        def query(self, _model):
            return SimpleNamespace(
                options=lambda *args, **kwargs: SimpleNamespace(
                    filter=lambda *a, **k: SimpleNamespace(first=lambda: None)
                )
            )

    with pytest.raises(HTTPException) as exc:
        await proxy_auth_ops.authorize_proxy_request(
            service=GrafanaProxyService(),
            request=_Req(),
            db=_DB(),
            auth_service=_Auth(),
            token="t",
            orig="/grafana/d/unknown-uid/test",
        )
    assert exc.value.status_code == 403
