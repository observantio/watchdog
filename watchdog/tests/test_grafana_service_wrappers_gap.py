"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import pytest

from tests._env import ensure_test_env

ensure_test_env()

from models.grafana.grafana_dashboard_models import Dashboard, DashboardCreate, DashboardUpdate
from models.grafana.grafana_datasource_models import DatasourceCreate, DatasourceUpdate
from services.grafana.grafana_service import GrafanaService


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_grafana_service_wrapper_methods_and_return_shapes(monkeypatch):
    service = GrafanaService(grafana_url="http://grafana.local", username="u", password="p", api_key="k")

    async def safe(method, path, default=None, **kwargs):
        if method == "DELETE":
            return default
        if path == "/api/search":
            return [
                {
                    "id": 1,
                    "uid": "d1",
                    "title": "CPU",
                    "uri": "db/cpu",
                    "url": "/d/d1/cpu",
                    "slug": "cpu",
                    "type": "dash-db",
                    "tags": [],
                }
            ]
        if path == "/api/dashboards/uid/d1":
            return {"dashboard": {"uid": "d1"}}
        if path == "/api/dashboards/uid/missing":
            return None
        if path == "/api/datasources":
            return [{"id": 1, "uid": "ds1", "orgId": 1, "name": "Prom", "type": "prometheus", "access": "proxy", "url": "http://prom"}]
        if path == "/api/datasources/uid/ds1":
            return {"id": 1, "uid": "ds1", "orgId": 1, "name": "Prom", "type": "prometheus", "access": "proxy", "url": "http://prom"}
        if path == "/api/datasources/name/Prom":
            return {"id": 1, "uid": "ds1", "orgId": 1, "name": "Prom", "type": "prometheus", "access": "proxy", "url": "http://prom"}
        if path == "/api/folders":
            return [{"id": 5, "uid": "f1", "title": "Ops"}]
        if path == "/api/folders/f1":
            return {"id": 5, "uid": "f1", "title": "Ops", "version": 2}
        return default

    async def mutating(method, path, **kwargs):
        if path == "/api/dashboards/db":
            return {"id": 1, "uid": "d1", "dashboard": {"uid": "d1", "title": "CPU", "tags": []}}
        if path == "/api/datasources":
            return {
                "datasource": {
                    "id": 1,
                    "uid": "ds1",
                    "orgId": 1,
                    "name": "Prom",
                    "type": "prometheus",
                    "access": "proxy",
                    "url": "http://prom",
                }
            }
        if path == "/api/datasources/uid/ds1":
            return {
                "datasource": {
                    "id": 1,
                    "uid": "ds1",
                    "orgId": 1,
                    "name": "Prom2",
                    "type": "prometheus",
                    "access": "proxy",
                    "url": "http://prom",
                }
            }
        if path == "/api/folders":
            return {"id": 5, "uid": "f1", "title": "Ops"}
        if path == "/api/folders/f1":
            return {"id": 5, "uid": "f1", "title": "Ops2", "version": 3}
        return None

    async def get_dash(uid):
        return {"dashboard": {"uid": uid}} if uid == "d1" else None

    async def request(method, path, **kwargs):
        if path == "/api/ds/query":
            return _Resp({})
        return _Resp({})

    monkeypatch.setattr(service, "_safe_request", safe)
    monkeypatch.setattr(service, "_mutating_request", mutating)
    monkeypatch.setattr(service, "_request", request)
    monkeypatch.setattr(service, "get_dashboard", get_dash)

    results = await service.search_dashboards(query="cpu", starred=True)
    assert len(results) == 1 and results[0].uid == "d1"

    assert await service.get_dashboard("d1") is not None
    created = await service.create_dashboard(DashboardCreate(dashboard=Dashboard(title="CPU", tags=[]), overwrite=False))
    assert created and created.get("uid") == "d1"
    updated = await service.update_dashboard("d1", DashboardUpdate(dashboard=Dashboard(title="CPU2", tags=[]), overwrite=True))
    assert updated and updated.get("uid") == "d1"
    assert await service.update_dashboard("missing", DashboardUpdate(dashboard=Dashboard(title="x", tags=[]), overwrite=True)) is None

    assert await service.delete_dashboard("d1") is False
    assert (await service.query_datasource({"queries": []})) == {}

    datasources = await service.get_datasources()
    assert len(datasources) == 1 and datasources[0].uid == "ds1"
    assert (await service.get_datasource("ds1")).uid == "ds1"
    assert (await service.get_datasource_by_name("Prom")).uid == "ds1"
    assert (await service.create_datasource(DatasourceCreate(name="Prom", type="prometheus", url="http://prom"))).uid == "ds1"
    assert (await service.update_datasource("ds1", DatasourceUpdate(name="Prom2"))).name == "Prom2"
    assert await service.delete_datasource("ds1") is False

    folders = await service.get_folders()
    assert len(folders) == 1 and folders[0].uid == "f1"
    assert (await service.create_folder("Ops")).uid == "f1"
    assert (await service.get_folder("f1")).uid == "f1"
    assert (await service.update_folder("f1", "Ops2")).title == "Ops2"
    assert await service.delete_folder("f1") is False
