"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Permission, Role, TokenData
from models.grafana.grafana_datasource_models import DatasourceCreate, DatasourceUpdate
from models.observability.grafana_request_models import (
    GrafanaCreateFolderRequest,
    GrafanaDashboardPayloadRequest,
    GrafanaDatasourceQueryRequest,
    GrafanaHiddenToggleRequest,
    GrafanaUpdateFolderRequest,
)
from routers.observability.grafana_router import dashboards, datasources, folders


async def _rtp(func, *args, **kwargs):
    value = func(*args, **kwargs)
    if inspect.isawaitable(value):
        return await value
    return value


def _user() -> TokenData:
    return TokenData(
        user_id="u1",
        username="user",
        tenant_id="tenant",
        org_id="org",
        role=Role.ADMIN,
        permissions=[permission.value for permission in Permission],
        group_ids=["g1"],
        is_superuser=True,
    )


@pytest.fixture(autouse=True)
def _patch_threadpool(monkeypatch):
    monkeypatch.setattr(dashboards, "rtp", _rtp)
    monkeypatch.setattr(datasources, "rtp", _rtp)
    monkeypatch.setattr(folders, "rtp", _rtp)


@pytest.mark.asyncio
async def test_dashboard_routes_cover_success_and_failure_paths(monkeypatch):
    current_user = _user()
    monkeypatch.setattr(dashboards, "scope_context", lambda _user: ("u1", "tenant", ["g1"], True))
    monkeypatch.setattr(dashboards, "validate_visibility", lambda _visibility: None)
    monkeypatch.setattr(dashboards, "dashboard_payload", lambda payload: payload.model_dump(exclude_none=True))
    monkeypatch.setattr(dashboards, "dashboard_uid", lambda raw: str(raw.get("dashboard", {}).get("uid") or ""))
    monkeypatch.setattr(dashboards, "parse_dashboard_create_payload", lambda raw: {"create": raw})
    monkeypatch.setattr(dashboards, "parse_dashboard_update_payload", lambda raw: {"update": raw})
    monkeypatch.setattr(dashboards.proxy, "get_dashboard_metadata", lambda **_kwargs: {"folder": ["f1"]})
    monkeypatch.setattr(dashboards.proxy, "build_dashboard_search_context", lambda *_args, **_kwargs: {"uid_db_dashboard": object()})

    async def fake_search_dashboards(**kwargs):
        return [{"uid": "dash-1", "query": kwargs["query"]}]

    async def fake_get_dashboard(**kwargs):
        return {"uid": kwargs["uid"]} if kwargs["uid"] == "dash-1" else None

    async def fake_create_dashboard(**kwargs):
        return {"uid": "created", "visibility": kwargs["visibility"]} if kwargs["visibility"] != "broken" else None

    async def fake_update_dashboard(**kwargs):
        return {"uid": kwargs["uid"], "updated": True} if kwargs["uid"] != "missing" else None

    async def fake_delete_dashboard(**kwargs):
        return kwargs["uid"] == "dash-1"

    monkeypatch.setattr(dashboards.proxy, "search_dashboards", fake_search_dashboards)
    monkeypatch.setattr(dashboards.proxy, "get_dashboard", fake_get_dashboard)
    monkeypatch.setattr(dashboards.proxy, "create_dashboard", fake_create_dashboard)
    monkeypatch.setattr(dashboards.proxy, "update_dashboard", fake_update_dashboard)
    monkeypatch.setattr(dashboards.proxy, "delete_dashboard", fake_delete_dashboard)
    monkeypatch.setattr(dashboards.proxy, "toggle_dashboard_hidden", lambda **_kwargs: True)

    meta = await dashboards.get_dashboard_filter_metadata(current_user, db="db")
    assert meta == {"folder": ["f1"]}

    searched = await dashboards.search_dashboards(query="latency", current_user=current_user, db="db")
    assert searched[0]["query"] == "latency"

    assert await dashboards.get_dashboard("dash-1", current_user, db="db") == {"uid": "dash-1"}
    with pytest.raises(HTTPException) as exc:
        await dashboards.get_dashboard("missing", current_user, db="db")
    assert exc.value.status_code == 404

    payload = GrafanaDashboardPayloadRequest.model_validate({"dashboard": {"uid": "dash-1", "title": "Latency"}})
    assert (await dashboards.create_dashboard(payload, visibility="private", shared_group_ids=["g1"], current_user=current_user, db="db"))["uid"] == "created"
    assert (await dashboards.save_dashboard_from_grafana_ui(payload, current_user=current_user, db="db"))["updated"] is True

    monkeypatch.setattr(dashboards.proxy, "build_dashboard_search_context", lambda *_args, **_kwargs: {"uid_db_dashboard": None})
    created_from_ui = await dashboards.save_dashboard_from_grafana_ui(payload, current_user=current_user, db="db")
    assert created_from_ui["uid"] == "created"

    assert (await dashboards.update_dashboard("dash-1", payload, visibility="group", shared_group_ids=["g1"], current_user=current_user, db="db"))["updated"] is True
    with pytest.raises(HTTPException) as exc:
        await dashboards.update_dashboard("missing", payload, current_user=current_user, db="db")
    assert exc.value.status_code == 404

    assert await dashboards.delete_dashboard("dash-1", current_user=current_user, db="db") == {"status": "success", "message": "Dashboard dash-1 deleted"}
    with pytest.raises(HTTPException) as exc:
        await dashboards.delete_dashboard("missing", current_user=current_user, db="db")
    assert exc.value.status_code == 404

    monkeypatch.setattr(dashboards, "hidden_toggle_context", lambda _user: ("u1", "tenant"))
    assert await dashboards.hide_dashboard("dash-1", GrafanaHiddenToggleRequest(hidden=False), current_user=current_user, db="db") == {"status": "success", "hidden": False}
    monkeypatch.setattr(dashboards.proxy, "toggle_dashboard_hidden", lambda **_kwargs: False)
    with pytest.raises(HTTPException) as exc:
        await dashboards.hide_dashboard("missing", GrafanaHiddenToggleRequest(), current_user=current_user, db="db")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_datasource_routes_cover_success_and_failure_paths(monkeypatch):
    current_user = _user()
    monkeypatch.setattr(datasources, "scope_context", lambda _user: ("u1", "tenant", ["g1"], True))
    monkeypatch.setattr(datasources, "hidden_toggle_context", lambda _user: ("u1", "tenant"))
    monkeypatch.setattr(datasources, "validate_visibility", lambda _visibility: None)
    async def fake_enforce_datasource_query_access(**_kwargs):
        return None

    async def fake_query_datasource(payload):
        return {"queried": payload}

    monkeypatch.setattr(datasources.proxy, "enforce_datasource_query_access", fake_enforce_datasource_query_access)
    monkeypatch.setattr(datasources.proxy, "query_datasource", fake_query_datasource)
    monkeypatch.setattr(datasources.proxy, "get_datasource_metadata", lambda **_kwargs: {"types": ["loki"]})
    monkeypatch.setattr(datasources.proxy, "build_datasource_list_context", lambda *_args, **_kwargs: {"context": True})

    async def fake_get_datasource_by_name(**kwargs):
        return {"name": kwargs["name"]} if kwargs["name"] == "main" else None

    async def fake_get_datasources(**kwargs):
        return [{"uid": "ds-1", "show_hidden": kwargs["show_hidden"]}]

    async def fake_get_datasource(**kwargs):
        return {"uid": kwargs["uid"]} if kwargs["uid"] == "ds-1" else None

    async def fake_create_datasource(**kwargs):
        return {"uid": "created", "visibility": kwargs["visibility"]} if kwargs["visibility"] else None

    async def fake_update_datasource(**kwargs):
        return {"uid": kwargs["uid"], "updated": True} if kwargs["uid"] == "ds-1" else None

    async def fake_delete_datasource(**kwargs):
        return kwargs["uid"] == "ds-1"

    monkeypatch.setattr(datasources.proxy, "get_datasource_by_name", fake_get_datasource_by_name)
    monkeypatch.setattr(datasources.proxy, "get_datasources", fake_get_datasources)
    monkeypatch.setattr(datasources.proxy, "get_datasource", fake_get_datasource)
    monkeypatch.setattr(datasources.proxy, "create_datasource", fake_create_datasource)
    monkeypatch.setattr(datasources.proxy, "update_datasource", fake_update_datasource)
    monkeypatch.setattr(datasources.proxy, "delete_datasource", fake_delete_datasource)
    monkeypatch.setattr(datasources.proxy, "toggle_datasource_hidden", lambda **_kwargs: True)

    payload = GrafanaDatasourceQueryRequest.model_validate({"queries": [{"expr": "up"}]})
    assert (await datasources.datasource_query(payload, current_user=current_user, db="db"))["queried"]["queries"][0]["expr"] == "up"
    assert await datasources.get_datasource_filter_metadata(current_user, db="db") == {"types": ["loki"]}
    assert await datasources.get_datasource_by_name("main", current_user, db="db") == {"name": "main"}
    with pytest.raises(HTTPException) as exc:
        await datasources.get_datasource_by_name("missing", current_user, db="db")
    assert exc.value.status_code == 404

    listed = await datasources.get_datasources(show_hidden=True, current_user=current_user, db="db")
    assert listed == [{"uid": "ds-1", "show_hidden": True}]
    assert await datasources.get_datasource_by_uid("ds-1", current_user, db="db") == {"uid": "ds-1"}
    with pytest.raises(HTTPException) as exc:
        await datasources.get_datasource_by_uid("missing", current_user, db="db")
    assert exc.value.status_code == 404

    create_payload = DatasourceCreate(name="loki", type="loki", url="http://loki")
    update_payload = DatasourceUpdate(name="renamed")
    assert (await datasources.create_datasource(create_payload, visibility="private", shared_group_ids=["g1"], current_user=current_user, db="db"))["uid"] == "created"
    assert (await datasources.update_datasource("ds-1", update_payload, visibility="group", shared_group_ids=["g1"], current_user=current_user, db="db"))["updated"] is True
    with pytest.raises(HTTPException) as exc:
        await datasources.update_datasource("missing", update_payload, current_user=current_user, db="db")
    assert exc.value.status_code == 404

    assert await datasources.delete_datasource("ds-1", current_user=current_user, db="db") == {"status": "success", "message": "Datasource ds-1 deleted"}
    with pytest.raises(HTTPException) as exc:
        await datasources.delete_datasource("missing", current_user=current_user, db="db")
    assert exc.value.status_code == 404

    assert await datasources.hide_datasource("ds-1", GrafanaHiddenToggleRequest(hidden=False), current_user=current_user, db="db") == {"status": "success", "hidden": False}
    monkeypatch.setattr(datasources.proxy, "toggle_datasource_hidden", lambda **_kwargs: False)
    with pytest.raises(HTTPException) as exc:
        await datasources.hide_datasource("missing", GrafanaHiddenToggleRequest(), current_user=current_user, db="db")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_folder_routes_cover_success_and_failure_paths(monkeypatch):
    current_user = _user()
    monkeypatch.setattr(folders, "scope_context", lambda _user: ("u1", "tenant", ["g1"], True))
    monkeypatch.setattr(folders, "hidden_toggle_context", lambda _user: ("u1", "tenant"))
    monkeypatch.setattr(folders, "validate_visibility", lambda _visibility: None)

    async def fake_get_folders(**kwargs):
        return [{"uid": "folder-1", "show_hidden": kwargs["show_hidden"]}]

    async def fake_get_folder(**kwargs):
        return {"uid": kwargs["uid"]} if kwargs["uid"] == "folder-1" else None

    async def fake_create_folder(**kwargs):
        return {"uid": "created-folder", "visibility": kwargs["visibility"]} if kwargs["visibility"] else None

    async def fake_delete_folder(**kwargs):
        return kwargs["uid"] == "folder-1"

    async def fake_update_folder(**kwargs):
        return {"uid": kwargs["uid"], "updated": True} if kwargs["uid"] == "folder-1" else None

    monkeypatch.setattr(folders.proxy, "get_folders", fake_get_folders)
    monkeypatch.setattr(folders.proxy, "get_folder", fake_get_folder)
    monkeypatch.setattr(folders.proxy, "create_folder", fake_create_folder)
    monkeypatch.setattr(folders.proxy, "delete_folder", fake_delete_folder)
    monkeypatch.setattr(folders.proxy, "update_folder", fake_update_folder)
    monkeypatch.setattr(folders.proxy, "toggle_folder_hidden", lambda **_kwargs: True)

    assert await folders.get_folders(show_hidden=True, current_user=current_user, db="db") == [{"uid": "folder-1", "show_hidden": True}]
    assert await folders.get_folder_by_uid("folder-1", current_user=current_user, db="db") == {"uid": "folder-1"}
    with pytest.raises(HTTPException) as exc:
        await folders.get_folder_by_uid("missing", current_user=current_user, db="db")
    assert exc.value.status_code == 404

    create_payload = GrafanaCreateFolderRequest.model_validate({"title": "Ops", "allowDashboardWrites": True})
    update_payload = GrafanaUpdateFolderRequest.model_validate({"title": "Ops 2", "allowDashboardWrites": False})
    assert (await folders.create_folder(create_payload, visibility="group", shared_group_ids=["g1"], current_user=current_user, db="db"))["uid"] == "created-folder"
    assert await folders.delete_folder("folder-1", current_user=current_user, db="db") == {"status": "success", "message": "Folder folder-1 deleted"}
    with pytest.raises(HTTPException) as exc:
        await folders.delete_folder("missing", current_user=current_user, db="db")
    assert exc.value.status_code == 404

    assert (await folders.update_folder("folder-1", update_payload, visibility="private", shared_group_ids=["g1"], current_user=current_user, db="db"))["updated"] is True
    with pytest.raises(HTTPException) as exc:
        await folders.update_folder("missing", update_payload, current_user=current_user, db="db")
    assert exc.value.status_code == 404

    assert await folders.hide_folder("folder-1", GrafanaHiddenToggleRequest(hidden=False), current_user=current_user, db="db") == {"status": "success", "hidden": False}
    monkeypatch.setattr(folders.proxy, "toggle_folder_hidden", lambda **_kwargs: False)
    with pytest.raises(HTTPException) as exc:
        await folders.hide_folder("missing", GrafanaHiddenToggleRequest(), current_user=current_user, db="db")
    assert exc.value.status_code == 404