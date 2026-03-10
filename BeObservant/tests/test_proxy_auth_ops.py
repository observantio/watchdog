"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import os
import time
from types import SimpleNamespace

import pytest
from starlette.requests import Request

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/observantio_test")
os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "False")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

from services.grafana import proxy_auth_ops
from models.access.auth_models import Permission, Role, TokenData
from fastapi import HTTPException


class _GrafanaServiceStub:
    def __init__(self, *, datasource=None, datasources=None):
        self._datasource = datasource
        self._datasources = list(datasources or [])

    async def get_datasource(self, uid: str):
        return self._datasource

    async def get_datasources(self):
        return self._datasources


class _ProxyStub:
    def __init__(self, grafana_service):
        self.grafana_service = grafana_service


class _DsObj:
    def __init__(self, *, uid=None, ds_id=None, is_default=False, read_only=False):
        self.uid = uid
        self.id = ds_id
        self.is_default = is_default
        self.read_only = read_only


class _GrafanaDashServiceStub(_GrafanaServiceStub):
    def __init__(self, *, dashboard=None, datasource=None, datasources=None):
        super().__init__(datasource=datasource, datasources=datasources)
        self._dashboard = dashboard or {}

    async def get_dashboard(self, uid: str):
        return self._dashboard


@pytest.mark.asyncio
async def test_lookup_safe_system_datasource_by_uid_allows_default():
    service = _ProxyStub(_GrafanaServiceStub(datasource=_DsObj(uid="default-prom", is_default=True)))

    allowed = await proxy_auth_ops._lookup_safe_system_datasource(
        service,
        datasource_uid="default-prom",
        datasource_id=None,
    )

    assert allowed is True


@pytest.mark.asyncio
async def test_lookup_safe_system_datasource_by_id_allows_read_only():
    service = _ProxyStub(_GrafanaServiceStub(datasources=[_DsObj(ds_id=12, read_only=True)]))

    allowed = await proxy_auth_ops._lookup_safe_system_datasource(
        service,
        datasource_uid=None,
        datasource_id=12,
    )

    assert allowed is True


@pytest.mark.asyncio
async def test_lookup_safe_system_datasource_rejects_non_system():
    service = _ProxyStub(_GrafanaServiceStub(datasource=_DsObj(uid="private-ds", is_default=False, read_only=False)))

    allowed = await proxy_auth_ops._lookup_safe_system_datasource(
        service,
        datasource_uid="private-ds",
        datasource_id=None,
    )

    assert allowed is False


def test_blocked_proxy_path_disallows_public_dashboards_and_snapshots():
    assert proxy_auth_ops._is_blocked_proxy_path("/grafana/public-dashboards/abcd1234")
    assert proxy_auth_ops._is_blocked_proxy_path("/grafana/dashboard/snapshot/xyz")
    assert proxy_auth_ops._is_blocked_proxy_path("/grafana/api/public/dashboards/uid/abcd")
    assert proxy_auth_ops._is_blocked_proxy_path("/grafana/api/snapshots/abcd")
    assert not proxy_auth_ops._is_blocked_proxy_path("/grafana/d/private-uid/private-dash")


def _request(path: str, *, method: str = "GET", headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "path": path,
            "headers": headers or [],
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
            "query_string": b"",
        }
    )


def _token_data(**overrides) -> TokenData:
    values = {
        "user_id": "u1",
        "username": "alice",
        "tenant_id": "tenant-a",
        "org_id": "org-a",
        "role": Role.USER,
        "permissions": [Permission.READ_DASHBOARDS.value],
        "group_ids": ["g1"],
        "is_superuser": False,
    }
    values.update(overrides)
    return TokenData(**values)


def test_proxy_role_helpers_accept_string_roles():
    assert proxy_auth_ops.is_admin_user(_token_data(role="admin")) is True
    assert proxy_auth_ops.is_admin_user(_token_data(role="user")) is False


def test_proxy_permission_gate_blocks_invalid_paths_and_folder_writes():
    with pytest.raises(HTTPException, match="Public/snapshot dashboard links are disabled"):
        proxy_auth_ops._enforce_proxy_permission_gate(
            _token_data(),
            original_path="/grafana/public-dashboards/uid/abc",
            original_method="GET",
        )

    with pytest.raises(HTTPException, match="Direct Grafana folder write API is disabled"):
        proxy_auth_ops._enforce_proxy_permission_gate(
            _token_data(permissions=[Permission.CREATE_FOLDERS.value]),
            original_path="/grafana/api/folders",
            original_method="POST",
        )

    proxy_auth_ops._enforce_proxy_permission_gate(
        _token_data(role="admin", permissions=[Permission.CREATE_FOLDERS.value]),
        original_path="/grafana/api/folders",
        original_method="POST",
    )


def test_proxy_small_helper_branches(monkeypatch):
    assert proxy_auth_ops._json_dict({"a": 1}) == {"a": 1}
    assert proxy_auth_ops._json_dict([]) == {}
    assert proxy_auth_ops._normalize_cache_path("") == "/"
    assert proxy_auth_ops._normalize_cache_path("grafana/API/search?x=1") == "/grafana/api/search"
    assert proxy_auth_ops._sanitize_header_value("a\r\nb\x00c") == "abc"
    assert proxy_auth_ops._is_static_path("/grafana/public/build/app.js") is True
    assert proxy_auth_ops._is_static_path("/grafana/private") is False

    proxy_auth_ops.clear_proxy_auth_cache()
    monkeypatch.setattr(time, "monotonic", lambda: 10.0)
    proxy_auth_ops._cache_set("tok", "GET", "/grafana/api/search", "tenant-a", {"x": "1"})
    assert proxy_auth_ops._cache_get("tok", "GET", "/grafana/api/search", "tenant-a") == {"x": "1"}
    monkeypatch.setattr(time, "monotonic", lambda: 1000.0)
    assert proxy_auth_ops._cache_get("tok", "GET", "/grafana/api/search", "tenant-a") is None

    proxy_auth_ops.clear_proxy_auth_cache()
    proxy_auth_ops.PROXY_AUTH_CACHE["stale"] = {"expires": 0.0, "headers": {"stale": "1"}}
    monkeypatch.setattr(proxy_auth_ops, "proxy_auth_cache_ops", proxy_auth_ops.PROXY_AUTH_CACHE_GC_EVERY - 1)
    monkeypatch.setattr(time, "monotonic", lambda: 5.0)
    proxy_auth_ops._cache_set("tok-2", "GET", "/grafana/api/search", "tenant-a", {"fresh": "1"})
    assert "stale" not in proxy_auth_ops.PROXY_AUTH_CACHE

    assert proxy_auth_ops._has_any_permission(_token_data(), set()) is True
    assert proxy_auth_ops._has_any_permission(_token_data(is_superuser=True, permissions=[]), {"missing"}) is True
    assert proxy_auth_ops._has_any_permission(_token_data(permissions=[]), {"missing"}) is False
    assert proxy_auth_ops._required_permissions_for_path("/grafana/api/query-history", "GET") == {
        Permission.QUERY_DATASOURCES.value,
        Permission.READ_DASHBOARDS.value,
    }
    assert proxy_auth_ops._required_permissions_for_path("/grafana/api/query-history", "POST") == {
        Permission.QUERY_DATASOURCES.value,
    }
    assert proxy_auth_ops._required_permissions_for_path("/unknown", "POST") == set()
    assert proxy_auth_ops._is_dashboard_write_intent("/grafana/api/dashboards/uid/abc", "PATCH") is True
    assert proxy_auth_ops._is_dashboard_write_intent("/grafana/d/abc", "GET") is False
    assert proxy_auth_ops._is_datasource_write_intent("/grafana/api/datasources/uid/abc", "DELETE") is True
    assert proxy_auth_ops._is_datasource_write_intent("/grafana/api/datasources", "GET") is False
    assert proxy_auth_ops._is_folder_write_intent("/grafana/api/folders", "PATCH") is True
    assert proxy_auth_ops._is_folder_write_intent("/grafana/api/search", "GET") is False


@pytest.mark.parametrize(
    ("path", "method", "expected"),
    [
        ("/grafana/api/ds/query", "POST", {Permission.QUERY_DATASOURCES.value}),
        ("/grafana/api/datasources/proxy/uid/ds-1", "GET", {Permission.QUERY_DATASOURCES.value}),
        ("/grafana/api/datasources/proxy/uid/ds-1", "POST", {Permission.QUERY_DATASOURCES.value}),
        ("/grafana/api/datasources/uid/ds-1/resources", "GET", {Permission.READ_DATASOURCES.value}),
        ("/grafana/api/datasources/uid/ds-1/resources", "POST", {Permission.QUERY_DATASOURCES.value}),
        ("/grafana/api/datasources/uid/ds-1", "GET", {Permission.READ_DATASOURCES.value}),
        ("/grafana/api/datasources/uid/ds-1", "PUT", {Permission.UPDATE_DATASOURCES.value}),
        ("/grafana/api/datasources/uid/ds-1", "DELETE", {Permission.DELETE_DATASOURCES.value}),
        ("/grafana/api/datasources", "GET", {Permission.READ_DATASOURCES.value}),
        ("/grafana/api/datasources", "POST", {Permission.CREATE_DATASOURCES.value}),
        ("/grafana/api/folders", "GET", {Permission.READ_FOLDERS.value}),
        ("/grafana/api/folders", "POST", {Permission.CREATE_FOLDERS.value}),
        ("/grafana/api/folders", "DELETE", {Permission.DELETE_FOLDERS.value}),
        ("/grafana/api/live/ws", "GET", {Permission.READ_DASHBOARDS.value}),
        (
            "/grafana/api/dashboards/db",
            "POST",
            {
                Permission.CREATE_DASHBOARDS.value,
                Permission.UPDATE_DASHBOARDS.value,
                Permission.WRITE_DASHBOARDS.value,
            },
        ),
        ("/grafana/api/dashboards/uid/d-1", "GET", {Permission.READ_DASHBOARDS.value}),
        ("/grafana/api/dashboards/uid/d-1", "DELETE", {Permission.DELETE_DASHBOARDS.value}),
    ],
)
def test_required_permissions_for_path_matrix(path, method, expected):
    assert proxy_auth_ops._required_permissions_for_path(path, method) == expected


def test_proxy_access_extraction_and_headers():
    group = SimpleNamespace(id="g1")
    assert proxy_auth_ops.is_resource_accessible(None, _token_data()) is False
    assert proxy_auth_ops.is_resource_accessible(
        SimpleNamespace(tenant_id="tenant-b", hidden_by=[], created_by="u1", is_default=False, read_only=False, visibility="private", shared_groups=[]),
        _token_data(),
    ) is False
    assert proxy_auth_ops.is_resource_accessible(
        SimpleNamespace(tenant_id="tenant-a", hidden_by=["u1"], created_by="u2", is_default=False, read_only=False, visibility="tenant", shared_groups=[]),
        _token_data(),
    ) is False
    assert proxy_auth_ops.is_resource_accessible(
        SimpleNamespace(tenant_id="tenant-a", hidden_by=[], created_by="u1", is_default=False, read_only=False, visibility="private", shared_groups=[]),
        _token_data(),
    ) is True
    assert proxy_auth_ops.is_resource_accessible(
        SimpleNamespace(tenant_id="tenant-a", hidden_by=[], created_by="u2", is_default=True, read_only=False, visibility="private", shared_groups=[]),
        _token_data(),
    ) is True
    assert proxy_auth_ops.is_resource_accessible(
        SimpleNamespace(tenant_id="tenant-a", hidden_by=[], created_by="u2", is_default=False, read_only=False, visibility="tenant", shared_groups=[]),
        _token_data(),
    ) is True
    assert proxy_auth_ops.is_resource_accessible(
        SimpleNamespace(tenant_id="tenant-a", hidden_by=[], created_by="u2", is_default=False, read_only=False, visibility="group", shared_groups=[group]),
        _token_data(group_ids=["g1"]),
    ) is True
    assert proxy_auth_ops.is_resource_accessible(
        SimpleNamespace(tenant_id="tenant-a", hidden_by=[], created_by="u2", is_default=False, read_only=False, visibility="private", shared_groups=[]),
        _token_data(),
    ) is False
    assert proxy_auth_ops.is_resource_accessible(
        SimpleNamespace(tenant_id="tenant-a", hidden_by=[], created_by="u2", is_default=False, read_only=False, visibility="tenant", shared_groups=[]),
        _token_data(),
        require_write=True,
    ) is False

    assert proxy_auth_ops.extract_dashboard_uid("/grafana/d/uid-a/name") == "uid-a"
    assert proxy_auth_ops.extract_dashboard_uid("/grafana/api/dashboards/uid/uid-b?x=1") == "uid-b"
    assert proxy_auth_ops.extract_dashboard_uid("/grafana/nope") is None
    assert proxy_auth_ops.extract_datasource_uid("/grafana/connections/datasources/edit/ds-1") == "ds-1"
    assert proxy_auth_ops.extract_datasource_uid("/grafana/nope") is None
    assert proxy_auth_ops.extract_datasource_id("/grafana/api/datasources/proxy/12/query") == 12
    assert proxy_auth_ops.extract_datasource_id("/grafana/api/datasources/proxy/nope") is None
    assert proxy_auth_ops.extract_folder_uid("/grafana/api/folders/fold-1") == "fold-1"
    assert proxy_auth_ops.extract_folder_uid("/grafana/api/folders/search") is None
    assert proxy_auth_ops.extract_folder_uid("/grafana/api/folders/id") is None

    header_request = _request("/", headers=[(b"authorization", b"Bearer bearer-token")])
    assert proxy_auth_ops.extract_proxy_token(header_request) == "bearer-token"
    cookie_request = Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/",
        "headers": [(b"cookie", b"access_token=cookie-token")],
        "client": ("127.0.0.1", 1),
        "scheme": "http",
        "query_string": b"",
    })
    assert proxy_auth_ops.extract_proxy_token(cookie_request) == "cookie-token"
    header_token_request = _request("/", headers=[(b"x-auth-token", b"header-token")])
    assert proxy_auth_ops.extract_proxy_token(header_token_request) == "header-token"
    assert proxy_auth_ops.extract_proxy_token(_request("/"), token="fallback-token") == "fallback-token"

    assert proxy_auth_ops._grafana_role(_token_data(role="admin")) == "Admin"
    assert proxy_auth_ops._grafana_role(_token_data(permissions=[Permission.UPDATE_DASHBOARDS.value])) == "Editor"
    assert proxy_auth_ops._grafana_role(_token_data(permissions=[Permission.READ_DASHBOARDS.value])) == "Viewer"
    headers = proxy_auth_ops._headers_for(_token_data(username="al\r\nice", tenant_id="tenant\n-a"))
    assert headers == {
        "X-WEBAUTH-USER": "alice",
        "X-WEBAUTH-TENANT": "tenant-a",
        "X-WEBAUTH-ROLE": "Viewer",
    }


def test_proxy_db_helpers_cover_loader_and_update_paths(monkeypatch):
    class QueryStub:
        def __init__(self, value):
            self.value = value

        def options(self, *args, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return self.value

    dash = SimpleNamespace(folder_uid="fold-1")
    folder = SimpleNamespace(grafana_uid="fold-1")
    orm_user = SimpleNamespace(is_active=True, org_id="scope-a", groups=[SimpleNamespace(id="g1"), SimpleNamespace(id=" ")])

    class DbStub:
        def __init__(self, values):
            self.values = iter(values)

        def query(self, model):
            return QueryStub(next(self.values))

    class AuthStub:
        def _collect_permissions(self, orm_user):
            return [Permission.READ_DASHBOARDS.value]

    def session_factory(values):
        from contextlib import contextmanager

        @contextmanager
        def session():
            yield DbStub(values)

        return session

    monkeypatch.setattr(
        proxy_auth_ops,
        "get_db_session",
        session_factory([orm_user, dash, folder]),
    )
    _, context = proxy_auth_ops._db_load_context(AuthStub(), _token_data(), "dash-1", None, None, None)
    assert context.org_id == "scope-a"
    assert context.permissions == [Permission.READ_DASHBOARDS.value]
    assert context.group_ids == ["g1"]
    assert context.dashboard is dash
    assert context.folder is folder

    monkeypatch.setattr(proxy_auth_ops, "get_db_session", session_factory([None]))
    with pytest.raises(HTTPException, match="User access denied"):
        proxy_auth_ops._db_load_context(AuthStub(), _token_data(), None, None, None, None)

    monkeypatch.setattr(proxy_auth_ops, "get_db_session", session_factory([orm_user]))
    _, context = proxy_auth_ops._db_load_context(AuthStub(), _token_data(), None, None, None, None)
    assert context.dashboard is None
    assert context.folder is None

    dash_obj = SimpleNamespace(folder_uid=None)
    monkeypatch.setattr(proxy_auth_ops, "get_db_session", session_factory([dash_obj]))
    proxy_auth_ops._db_set_dashboard_folder_uid("tenant-a", "dash-1", "fold-9")
    assert dash_obj.folder_uid == "fold-9"
    proxy_auth_ops._db_clear_dashboard_folder_uid("tenant-a", "dash-1")
    assert dash_obj.folder_uid is None

    monkeypatch.setattr(proxy_auth_ops, "get_db_session", session_factory([None]))
    proxy_auth_ops._db_set_dashboard_folder_uid("tenant-a", "missing", "fold-1")
    proxy_auth_ops._db_clear_dashboard_folder_uid("tenant-a", "missing")

    assert proxy_auth_ops._db_load_folder("tenant-a", None) is None
    assert proxy_auth_ops._db_load_folder_by_id("tenant-a", None) is None
    assert proxy_auth_ops._db_load_folder_by_id("tenant-a", "bad") is None
    assert proxy_auth_ops._db_load_folder_by_id("tenant-a", 0) is None


@pytest.mark.asyncio
async def test_enforce_writable_datasource_allows_missing_or_writable():
    await proxy_auth_ops._enforce_writable_datasource(_ProxyStub(_GrafanaServiceStub(datasource=None)), "ds-1")
    await proxy_auth_ops._enforce_writable_datasource(
        _ProxyStub(_GrafanaServiceStub(datasource=_DsObj(uid="ds-1", is_default=False, read_only=False))),
        "ds-1",
    )


@pytest.mark.asyncio
async def test_proxy_authorization_helper_branches(monkeypatch):
    async def fake_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(proxy_auth_ops, "run_in_threadpool", fake_run_in_threadpool)

    service = _ProxyStub(_GrafanaDashServiceStub(dashboard={"meta": {"folderUid": "fold-1"}}))
    folder_obj = SimpleNamespace(grafana_uid="fold-1", tenant_id="tenant-a", hidden_by=[], created_by="u1", is_default=False, read_only=False, visibility="tenant", shared_groups=[])
    set_calls = []
    monkeypatch.setattr(proxy_auth_ops, "_db_load_folder", lambda tenant_id, folder_uid: folder_obj)
    monkeypatch.setattr(proxy_auth_ops, "_db_set_dashboard_folder_uid", lambda tenant_id, dashboard_uid, folder_uid: set_calls.append((tenant_id, dashboard_uid, folder_uid)))
    resolved_folder = await proxy_auth_ops._resolve_dashboard_folder_context(service, _token_data(), dashboard_uid="dash-1", folder_obj=None)
    assert resolved_folder is folder_obj
    assert set_calls == [("tenant-a", "dash-1", "fold-1")]

    service = _ProxyStub(_GrafanaDashServiceStub(dashboard={"meta": {"folderId": 3}}))
    monkeypatch.setattr(proxy_auth_ops, "_db_load_folder_by_id", lambda tenant_id, folder_id: SimpleNamespace(grafana_uid="fold-3"))
    folder = await proxy_auth_ops._resolve_dashboard_folder_context(service, _token_data(), dashboard_uid="dash-2", folder_obj=None)
    assert getattr(folder, "grafana_uid") == "fold-3"

    service = _ProxyStub(_GrafanaDashServiceStub(dashboard={"meta": {"folderId": 3}}))
    monkeypatch.setattr(proxy_auth_ops, "_db_load_folder_by_id", lambda tenant_id, folder_id: SimpleNamespace(grafana_uid=""))
    with pytest.raises(HTTPException, match="Folder access denied"):
        await proxy_auth_ops._resolve_dashboard_folder_context(service, _token_data(), dashboard_uid="dash-3", folder_obj=None)

    clear_calls = []
    service = _ProxyStub(_GrafanaDashServiceStub(dashboard={"meta": {}}))
    monkeypatch.setattr(proxy_auth_ops, "_db_clear_dashboard_folder_uid", lambda tenant_id, dashboard_uid: clear_calls.append((tenant_id, dashboard_uid)))
    assert await proxy_auth_ops._resolve_dashboard_folder_context(service, _token_data(), dashboard_uid="dash-4", folder_obj=None) is None
    assert clear_calls == [("tenant-a", "dash-4")]

    assert await proxy_auth_ops._authorize_dashboard_access(
        _ProxyStub(_GrafanaDashServiceStub()),
        _token_data(),
        dashboard_uid=None,
        dashboard_obj=None,
        folder_obj=folder_obj,
        original_path="/grafana/api/search",
        original_method="GET",
    ) is folder_obj

    dashboard_obj = SimpleNamespace(tenant_id="tenant-a", hidden_by=[], created_by="u1", is_default=False, read_only=False, visibility="tenant", shared_groups=[])

    async def resolve_folder(*args, **kwargs):
        return folder_obj

    monkeypatch.setattr(proxy_auth_ops, "_resolve_dashboard_folder_context", resolve_folder)
    assert await proxy_auth_ops._authorize_dashboard_access(
        _ProxyStub(_GrafanaDashServiceStub()),
        _token_data(),
        dashboard_uid="dash-5",
        dashboard_obj=dashboard_obj,
        folder_obj=folder_obj,
        original_path="/grafana/api/dashboards/uid/dash-5",
        original_method="GET",
    ) is folder_obj

    with pytest.raises(HTTPException, match="Dashboard access denied"):
        await proxy_auth_ops._authorize_dashboard_access(
            _ProxyStub(_GrafanaDashServiceStub()),
            _token_data(),
            dashboard_uid="dash-5",
            dashboard_obj=None,
            folder_obj=folder_obj,
            original_path="/grafana/api/dashboards/uid/dash-5",
            original_method="GET",
        )

    hidden_folder = SimpleNamespace(tenant_id="tenant-a", hidden_by=["u1"], created_by="u2", is_default=False, read_only=False, visibility="tenant", shared_groups=[])

    async def resolve_hidden_folder(*args, **kwargs):
        return hidden_folder

    monkeypatch.setattr(proxy_auth_ops, "_resolve_dashboard_folder_context", resolve_hidden_folder)
    with pytest.raises(HTTPException, match="Folder access denied"):
        await proxy_auth_ops._authorize_dashboard_access(
            _ProxyStub(_GrafanaDashServiceStub()),
            _token_data(),
            dashboard_uid="dash-5",
            dashboard_obj=dashboard_obj,
            folder_obj=folder_obj,
            original_path="/grafana/api/dashboards/uid/dash-5",
            original_method="GET",
        )


@pytest.mark.asyncio
async def test_proxy_datasource_and_request_error_branches(monkeypatch):
    writable_calls = []

    async def enforce_writable(service, datasource_uid):
        writable_calls.append(datasource_uid)

    monkeypatch.setattr(proxy_auth_ops, "_enforce_writable_datasource", enforce_writable)

    ds_obj = SimpleNamespace(grafana_uid="ds-1", tenant_id="tenant-a", hidden_by=[], created_by="u1", is_default=False, read_only=False, visibility="tenant", shared_groups=[])
    await proxy_auth_ops._authorize_datasource_access(
        _ProxyStub(_GrafanaServiceStub()),
        _token_data(),
        datasource_uid="ds-1",
        datasource_id=None,
        datasource_by_uid=ds_obj,
        datasource_by_id=None,
        original_path="/grafana/api/datasources/uid/ds-1",
        original_method="PUT",
    )
    assert writable_calls == ["ds-1"]

    with pytest.raises(HTTPException, match="Datasource access denied"):
        await proxy_auth_ops._authorize_datasource_access(
            _ProxyStub(_GrafanaServiceStub()),
            _token_data(),
            datasource_uid="ds-1",
            datasource_id=None,
            datasource_by_uid=None,
            datasource_by_id=None,
            original_path="/grafana/api/datasources/uid/ds-1",
            original_method="GET",
        )

    async def lookup_safe(*args, **kwargs):
        return True

    monkeypatch.setattr(proxy_auth_ops, "_lookup_safe_system_datasource", lookup_safe)
    with pytest.raises(HTTPException, match="Default/read-only datasources are view/query only"):
        await proxy_auth_ops._authorize_datasource_access(
            _ProxyStub(_GrafanaServiceStub()),
            _token_data(),
            datasource_uid="ds-1",
            datasource_id=None,
            datasource_by_uid=None,
            datasource_by_id=None,
            original_path="/grafana/api/datasources/uid/ds-1",
            original_method="PUT",
        )

    proxy_auth_ops._authorize_folder_access(_token_data(), folder_uid=None, folder_obj=None)
    with pytest.raises(HTTPException, match="Folder access denied"):
        proxy_auth_ops._authorize_folder_access(_token_data(), folder_uid="fold-1", folder_obj=None)

    proxy_auth_ops.clear_proxy_auth_cache()
    service = _ProxyStub(_GrafanaServiceStub())
    auth_service = SimpleNamespace(decode_token=lambda token: None)

    async def fake_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(proxy_auth_ops, "run_in_threadpool", fake_run_in_threadpool)

    with pytest.raises(HTTPException, match="You need to log in"):
        await proxy_auth_ops.authorize_proxy_request(service, _request("/grafana/api/search"), auth_service)

    invalid_request = _request("/grafana/api/search", headers=[(b"authorization", b"Bearer bad")])
    with pytest.raises(HTTPException, match="expired or your token is invalid"):
        await proxy_auth_ops.authorize_proxy_request(service, invalid_request, auth_service)

    valid_token = _token_data()
    auth_service = SimpleNamespace(decode_token=lambda token: valid_token)
    with pytest.raises(HTTPException, match="Missing original URI context"):
        await proxy_auth_ops.authorize_proxy_request(
            service,
            _request("/grafana/api/search", headers=[(b"authorization", b"Bearer ok")]),
            auth_service,
        )

    monkeypatch.setattr(proxy_auth_ops, "_cache_get", lambda *args, **kwargs: {"cached": "1"})
    cached = await proxy_auth_ops.authorize_proxy_request(
        service,
        _request(
            "/grafana/api/search",
            headers=[
                (b"authorization", b"Bearer ok"),
                (b"x-original-uri", b"/grafana/api/search"),
                (b"x-original-method", b"GET"),
            ],
        ),
        auth_service,
    )
    assert cached == {"cached": "1"}


@pytest.mark.asyncio
async def test_authorize_proxy_request_applies_db_context(monkeypatch):
    proxy_auth_ops.clear_proxy_auth_cache()
    token_data = _token_data(permissions=[Permission.READ_DASHBOARDS.value])
    auth_service = SimpleNamespace(decode_token=lambda token: token_data)
    service = _ProxyStub(_GrafanaServiceStub())

    async def fake_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    context = proxy_auth_ops.ProxyAuthorizationContext(
        org_id="scoped-org",
        permissions=[Permission.READ_DASHBOARDS.value, Permission.READ_FOLDERS.value],
        group_ids=["g9"],
        dashboard=None,
        datasource_by_uid=None,
        datasource_by_id=None,
        folder=None,
    )

    monkeypatch.setattr(proxy_auth_ops, "run_in_threadpool", fake_run_in_threadpool)
    monkeypatch.setattr(proxy_auth_ops, "_db_load_context", lambda *args, **kwargs: (object(), context))

    async def noop_async(*args, **kwargs):
        return None

    monkeypatch.setattr(proxy_auth_ops, "_authorize_dashboard_access", noop_async)
    monkeypatch.setattr(proxy_auth_ops, "_authorize_datasource_access", noop_async)
    monkeypatch.setattr(proxy_auth_ops, "_authorize_folder_access", lambda *args, **kwargs: None)

    request = _request(
        "/grafana/api/search",
        headers=[
            (b"authorization", b"Bearer token-1"),
            (b"x-original-uri", b"/grafana/api/search"),
            (b"x-original-method", b"GET"),
        ],
    )

    headers = await proxy_auth_ops.authorize_proxy_request(service, request, auth_service)

    assert headers["X-WEBAUTH-USER"] == "alice"
    assert headers["X-WEBAUTH-TENANT"] == "tenant-a"
    assert token_data.org_id == "scoped-org"
    assert token_data.permissions == [Permission.READ_DASHBOARDS.value, Permission.READ_FOLDERS.value]
    assert token_data.group_ids == ["g9"]


@pytest.mark.asyncio
async def test_authorize_proxy_request_allows_static_paths_without_db_lookup(monkeypatch):
    proxy_auth_ops.clear_proxy_auth_cache()
    token_data = _token_data(username="bob")
    auth_service = SimpleNamespace(decode_token=lambda token: token_data)
    service = _ProxyStub(_GrafanaServiceStub())

    async def fake_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(proxy_auth_ops, "run_in_threadpool", fake_run_in_threadpool)

    def fail_db(*args, **kwargs):
        raise AssertionError("db lookup should not happen for static paths")

    monkeypatch.setattr(proxy_auth_ops, "_db_load_context", fail_db)

    request = _request(
        "/grafana/public/build/app.js",
        headers=[
            (b"authorization", b"Bearer token-2"),
            (b"x-original-uri", b"/grafana/public/build/app.js"),
            (b"x-original-method", b"GET"),
        ],
    )

    headers = await proxy_auth_ops.authorize_proxy_request(service, request, auth_service)

    assert headers == {
        "X-WEBAUTH-USER": "bob",
        "X-WEBAUTH-TENANT": "tenant-a",
        "X-WEBAUTH-ROLE": "Viewer",
    }
