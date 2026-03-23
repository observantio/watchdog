"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import pytest
import httpx

from tests._env import ensure_test_env

ensure_test_env()

from models.grafana.grafana_dashboard_models import Dashboard, DashboardUpdate
from models.grafana.grafana_datasource_models import Datasource, DatasourceUpdate
from services.grafana.grafana_service import GrafanaAPIError, GrafanaService


class _Response:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.request = httpx.Request("GET", "https://grafana.local")

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=self.request, response=httpx.Response(self.status_code, request=self.request))


@pytest.mark.asyncio
async def test_request_falls_back_to_basic_auth_after_api_key_401():
    service = GrafanaService(grafana_url="http://grafana.local", username="u", password="p", api_key="key")

    calls = []

    class _Client:
        async def request(self, method, url, headers=None, params=None, json=None):
            calls.append(headers.get("Authorization", ""))
            if len(calls) == 1:
                return _Response(status_code=401, payload={"message": "bad key"})
            return _Response(status_code=200, payload={"ok": True})

    service._client = _Client()
    response = await service._request("GET", "/api/search")
    assert response.status_code == 200
    assert calls[0].startswith("Bearer ")
    assert calls[1].startswith("Basic ")


@pytest.mark.asyncio
async def test_safe_and_mutating_request_error_and_default_paths():
    service = GrafanaService(grafana_url="http://grafana.local", username="u", password="p", api_key="key")

    async def req_invalid(*_args, **_kwargs):
        return _Response(status_code=200, payload=object())

    service._request = req_invalid
    assert await service._safe_request("GET", "/api/search", default=[]) == []

    async def req_http_error(*_args, **_kwargs):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", "http://grafana.local"))

    service._request = req_http_error
    assert await service._safe_request("GET", "/api/search", default={"fallback": True}) == {"fallback": True}

    async def req_status_error(*_args, **_kwargs):
        req = httpx.Request("POST", "http://grafana.local")
        resp = httpx.Response(409, request=req, json={"message": "conflict"})
        # Return a response object where raise_for_status() produces HTTPStatusError
        return resp

    service._request = req_status_error
    with pytest.raises(GrafanaAPIError) as exc:
        await service._mutating_request("POST", "/api/dashboards/db", json={"x": 1})
    assert exc.value.status == 409


@pytest.mark.asyncio
async def test_update_dashboard_update_datasource_and_update_folder_branches(monkeypatch):
    service = GrafanaService(grafana_url="http://grafana.local", username="u", password="p", api_key="key")

    async def no_dashboard(_uid):
        return None

    service.get_dashboard = no_dashboard
    update = DashboardUpdate(dashboard=Dashboard(title="x", tags=[]), overwrite=True)
    assert await service.update_dashboard("missing", update) is None

    get_calls = {"count": 0}

    async def get_ds(uid):
        get_calls["count"] += 1
        return Datasource(
            id=1,
            uid=uid,
            orgId=1,
            name="metrics",
            type="prometheus",
            access="proxy",
            url="http://prometheus",
        )

    async def put_ds(*_args, **_kwargs):
        # No "datasource" payload -> function should fall back to get_datasource(uid)
        return {"status": "ok"}

    service.get_datasource = get_ds
    service._mutating_request = put_ds
    out = await service.update_datasource("ds-1", DatasourceUpdate(org_id="2"))
    assert out is not None
    assert get_calls["count"] == 2

    async def get_folder(uid):
        return type("FolderStub", (), {"id": 1, "uid": uid, "version": 3, "title": "Ops"})()

    async def fail_folder(*_args, **_kwargs):
        raise GrafanaAPIError(500, {"message": "server error"})

    service.get_folder = get_folder
    service._mutating_request = fail_folder
    with pytest.raises(GrafanaAPIError):
        await service.update_folder("f-1", "New")
