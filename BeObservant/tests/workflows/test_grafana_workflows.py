"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import pytest

from routers.observability.grafana_router import dashboards, datasources, folders, proxy as grafana_proxy_router

from .helpers import WorkflowState, patch_auth_service


def test_grafana_proxy_folder_and_dashboard_workflows(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)

    monkeypatch.setattr(dashboards, "parse_dashboard_create_payload", lambda raw: raw)
    monkeypatch.setattr(dashboards, "parse_dashboard_update_payload", lambda raw: raw)
    monkeypatch.setattr(dashboards.proxy, "get_dashboard_metadata", state.get_dashboard_metadata)
    monkeypatch.setattr(dashboards.proxy, "build_dashboard_search_context", state.build_dashboard_search_context)
    monkeypatch.setattr(dashboards.proxy, "create_dashboard", state.create_dashboard)
    monkeypatch.setattr(dashboards.proxy, "update_dashboard", state.update_dashboard)
    monkeypatch.setattr(dashboards.proxy, "delete_dashboard", state.delete_dashboard)
    monkeypatch.setattr(dashboards.proxy, "search_dashboards", state.search_dashboards)
    monkeypatch.setattr(dashboards.proxy, "get_dashboard", state.get_dashboard)
    monkeypatch.setattr(dashboards.proxy, "toggle_dashboard_hidden", state.toggle_dashboard_hidden)
    monkeypatch.setattr(folders.proxy, "create_folder", state.create_folder)
    monkeypatch.setattr(folders.proxy, "get_folders", state.get_folders)
    monkeypatch.setattr(folders.proxy, "get_folder", state.get_folder)
    monkeypatch.setattr(folders.proxy, "update_folder", state.update_folder)
    monkeypatch.setattr(folders.proxy, "delete_folder", state.delete_folder)
    monkeypatch.setattr(folders.proxy, "toggle_folder_hidden", state.toggle_folder_hidden)

    async def fake_authorize_proxy_request(**kwargs):
        return {"X-WEBAUTH-USER": kwargs["token"] or "cookie-user"}

    monkeypatch.setattr(grafana_proxy_router.proxy, "authorize_proxy_request", fake_authorize_proxy_request)

    admin_headers = state.auth_header("token-u-admin")

    group_response = client.post("/api/auth/groups", headers=admin_headers, json={"name": "grafana-shared", "description": "Grafana shared access"})
    group_id = group_response.json()["id"]
    user2_response = client.post("/api/auth/users", headers=admin_headers, json={"username": "grafana2", "email": "grafana2@example.com", "password": "password123"})
    user3_response = client.post("/api/auth/users", headers=admin_headers, json={"username": "grafana3", "email": "grafana3@example.com", "password": "password123"})
    user2_id = user2_response.json()["id"]
    user3_id = user3_response.json()["id"]
    client.put(
        f"/api/auth/users/{user2_id}/permissions",
        headers=admin_headers,
        json=["create:folders", "delete:folders", "read:dashboards", "update:dashboards", "write:dashboards", "read:folders"],
    )
    client.put(f"/api/auth/groups/{group_id}/members", headers=admin_headers, json={"user_ids": [user2_id]})

    auth_response = client.get("/api/grafana/auth", params={"token": "token-u-admin", "orig": "/grafana/d/team"})
    assert auth_response.status_code == 204
    assert auth_response.headers["x-webauth-user"] == "token-u-admin"

    bootstrap_response = client.post("/api/grafana/bootstrap-session", headers=admin_headers, json={"next": "/d/overview"})
    assert bootstrap_response.status_code == 200
    assert bootstrap_response.json() == {"launch_url": "/grafana/d/overview"}

    private_folder = client.post("/api/grafana/folders?visibility=private", headers=admin_headers, json={"title": "Private Folder", "allowDashboardWrites": False})
    group_folder = client.post(f"/api/grafana/folders?visibility=group&shared_group_ids={group_id}", headers=admin_headers, json={"title": "Group Folder", "allowDashboardWrites": True})
    tenant_folder = client.post("/api/grafana/folders?visibility=tenant", headers=admin_headers, json={"title": "Tenant Folder", "allowDashboardWrites": True})
    assert private_folder.status_code == 200
    assert group_folder.status_code == 200
    assert tenant_folder.status_code == 200
    group_folder_uid = group_folder.json()["uid"]
    tenant_folder_uid = tenant_folder.json()["uid"]

    folders_admin = client.get("/api/grafana/folders", headers=admin_headers)
    folders_user2 = client.get("/api/grafana/folders", headers=state.auth_header(f"token-{user2_id}"))
    folders_user3 = client.get("/api/grafana/folders", headers=state.auth_header(f"token-{user3_id}"))
    assert len(folders_admin.json()) == 3
    assert len(folders_user2.json()) == 2
    assert len(folders_user3.json()) == 1

    update_folder_response = client.put(
        f"/api/grafana/folders/{group_folder_uid}?visibility=group&shared_group_ids={group_id}",
        headers=admin_headers,
        json={"title": "Group Folder Updated", "allowDashboardWrites": True},
    )
    assert update_folder_response.status_code == 200

    hide_folder_response = client.post(
        f"/api/grafana/folders/{tenant_folder_uid}/hide",
        headers=state.auth_header(f"token-{user2_id}"),
        json={"hidden": True},
    )
    assert hide_folder_response.status_code == 200

    hidden_folders = client.get("/api/grafana/folders?show_hidden=true", headers=state.auth_header(f"token-{user2_id}"))
    assert hidden_folders.status_code == 200
    assert any(folder["isHidden"] is True for folder in hidden_folders.json())

    folder_lookup = client.get(f"/api/grafana/folders/{group_folder_uid}", headers=state.auth_header(f"token-{user2_id}"))
    assert folder_lookup.status_code == 200

    group_folder_id = group_folder.json()["id"]
    tenant_folder_id = tenant_folder.json()["id"]
    dashboard_private = client.post("/api/grafana/dashboards?visibility=private", headers=admin_headers, json={"dashboard": {"uid": "dash-private", "title": "Private Dashboard"}})
    dashboard_group = client.post(f"/api/grafana/dashboards?visibility=group&shared_group_ids={group_id}", headers=admin_headers, json={"dashboard": {"uid": "dash-group", "title": "Group Dashboard"}, "folderId": group_folder_id})
    dashboard_tenant = client.post("/api/grafana/dashboards?visibility=tenant", headers=admin_headers, json={"dashboard": {"uid": "dash-tenant", "title": "Tenant Dashboard"}, "folderId": tenant_folder_id})
    assert dashboard_private.status_code == 200
    assert dashboard_group.status_code == 200
    assert dashboard_tenant.status_code == 200

    save_from_ui_response = client.post(
        "/api/grafana/dashboards/db",
        headers=admin_headers,
        json={"dashboard": {"uid": "dash-group", "title": "Group Dashboard v2"}, "folderId": group_folder_id},
    )
    assert save_from_ui_response.status_code == 200

    dashboard_meta = client.get("/api/grafana/dashboards/meta/filters", headers=admin_headers)
    assert dashboard_meta.status_code == 200

    dashboards_admin = client.get("/api/grafana/dashboards/search", headers=admin_headers)
    dashboards_user2 = client.get("/api/grafana/dashboards/search", headers=state.auth_header(f"token-{user2_id}"))
    dashboards_user3 = client.get("/api/grafana/dashboards/search", headers=state.auth_header(f"token-{user3_id}"))
    assert len(dashboards_admin.json()) == 3
    assert len(dashboards_user2.json()) == 2
    assert len(dashboards_user3.json()) == 1

    assert client.get("/api/grafana/dashboards/dash-private", headers=state.auth_header(f"token-{user2_id}")).status_code == 404
    assert client.get("/api/grafana/dashboards/dash-group", headers=state.auth_header(f"token-{user2_id}")).status_code == 200
    assert client.get("/api/grafana/dashboards/dash-tenant", headers=state.auth_header(f"token-{user3_id}")).status_code == 200

    update_dashboard_response = client.put(
        f"/api/grafana/dashboards/dash-group?visibility=group&shared_group_ids={group_id}",
        headers=admin_headers,
        json={"dashboard": {"uid": "dash-group", "title": "Group Dashboard Updated"}, "folderId": group_folder_id},
    )
    assert update_dashboard_response.status_code == 200

    hide_dashboard_response = client.post(
        "/api/grafana/dashboards/dash-tenant/hide",
        headers=state.auth_header(f"token-{user2_id}"),
        json={"hidden": True},
    )
    assert hide_dashboard_response.status_code == 200

    hidden_dashboards = client.get("/api/grafana/dashboards/search?show_hidden=true", headers=state.auth_header(f"token-{user2_id}"))
    assert hidden_dashboards.status_code == 200
    assert any(item["is_hidden"] is True for item in hidden_dashboards.json())

    delete_dashboard_response = client.delete("/api/grafana/dashboards/dash-private", headers=admin_headers)
    assert delete_dashboard_response.status_code == 200
    delete_folder_response = client.delete(f"/api/grafana/folders/{tenant_folder_uid}", headers=admin_headers)
    assert delete_folder_response.status_code == 200


def test_grafana_datasource_query_and_visibility_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)

    monkeypatch.setattr(datasources.proxy, "enforce_datasource_query_access", state.enforce_datasource_query_access)
    monkeypatch.setattr(datasources.proxy, "query_datasource", state.query_datasource)
    monkeypatch.setattr(datasources.proxy, "get_datasource_metadata", state.get_datasource_metadata)
    monkeypatch.setattr(datasources.proxy, "build_datasource_list_context", state.build_datasource_list_context)
    monkeypatch.setattr(datasources.proxy, "get_datasource_by_name", state.get_datasource_by_name)
    monkeypatch.setattr(datasources.proxy, "get_datasources", state.get_datasources)
    monkeypatch.setattr(datasources.proxy, "get_datasource", state.get_datasource)
    monkeypatch.setattr(datasources.proxy, "create_datasource", state.create_datasource)
    monkeypatch.setattr(datasources.proxy, "update_datasource", state.update_datasource)
    monkeypatch.setattr(datasources.proxy, "delete_datasource", state.delete_datasource)
    monkeypatch.setattr(datasources.proxy, "toggle_datasource_hidden", state.toggle_datasource_hidden)

    admin_headers = state.auth_header("token-u-admin")
    group_response = client.post("/api/auth/groups", headers=admin_headers, json={"name": "ds-shared", "description": "Datasource sharing"})
    group_id = group_response.json()["id"]
    user_response = client.post("/api/auth/users", headers=admin_headers, json={"username": "dsuser", "email": "dsuser@example.com", "password": "password123"})
    user_id = user_response.json()["id"]
    client.put(
        f"/api/auth/users/{user_id}/permissions",
        headers=admin_headers,
        json=["create:datasources", "update:datasources", "read:datasources", "query:datasources"],
    )
    client.put(f"/api/auth/groups/{group_id}/members", headers=admin_headers, json={"user_ids": [user_id]})

    private_ds = client.post("/api/grafana/datasources?visibility=private", headers=admin_headers, json={"name": "private-loki", "type": "loki", "url": "http://loki"})
    group_ds = client.post(f"/api/grafana/datasources?visibility=group&shared_group_ids={group_id}", headers=admin_headers, json={"name": "group-tempo", "type": "tempo", "url": "http://tempo"})
    tenant_ds = client.post("/api/grafana/datasources?visibility=tenant", headers=admin_headers, json={"name": "tenant-prom", "type": "prometheus", "url": "http://prom"})
    assert private_ds.status_code == 200
    assert group_ds.status_code == 200
    assert tenant_ds.status_code == 200
    group_ds_uid = group_ds.json()["uid"]
    tenant_ds_uid = tenant_ds.json()["uid"]

    query_response = client.post("/api/grafana/ds/query", headers=admin_headers, json={"queries": [{"expr": "sum(rate(http_requests_total[5m]))"}]})
    assert query_response.status_code == 200
    assert query_response.json()["results"]["queries"][0]["expr"]

    metadata_response = client.get("/api/grafana/datasources/meta/filters", headers=admin_headers)
    assert metadata_response.status_code == 200
    assert metadata_response.json()["types"]

    get_by_name_response = client.get("/api/grafana/datasources/name/group-tempo", headers=state.auth_header(f"token-{user_id}"))
    assert get_by_name_response.status_code == 200

    list_user_ds = client.get("/api/grafana/datasources", headers=state.auth_header(f"token-{user_id}"))
    assert list_user_ds.status_code == 200
    assert len(list_user_ds.json()) == 2

    assert client.get(f"/api/grafana/datasources/{group_ds_uid}", headers=state.auth_header(f"token-{user_id}")).status_code == 200
    assert client.get(f"/api/grafana/datasources/{tenant_ds_uid}", headers=state.auth_header(f"token-{user_id}")).status_code == 200

    update_ds_response = client.put(
        f"/api/grafana/datasources/{group_ds_uid}?visibility=group&shared_group_ids={group_id}",
        headers=admin_headers,
        json={"name": "group-tempo-updated", "url": "http://tempo-updated"},
    )
    assert update_ds_response.status_code == 200

    hide_ds_response = client.post(
        f"/api/grafana/datasources/{tenant_ds_uid}/hide",
        headers=state.auth_header(f"token-{user_id}"),
        json={"hidden": True},
    )
    assert hide_ds_response.status_code == 200

    hidden_ds_response = client.get("/api/grafana/datasources?show_hidden=true", headers=state.auth_header(f"token-{user_id}"))
    assert hidden_ds_response.status_code == 200
    assert any(item["is_hidden"] is True for item in hidden_ds_response.json())

    delete_ds_response = client.delete(f"/api/grafana/datasources/{group_ds_uid}", headers=admin_headers)
    assert delete_ds_response.status_code == 200