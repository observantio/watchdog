import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/observantio_test")
os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "False")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

from models.grafana.grafana_datasource_models import Datasource, DatasourceCreate, DatasourceUpdate
from services.grafana.grafana_service import GrafanaService


@pytest.mark.asyncio
async def test_create_datasource_forwards_org_id_as_orgId(monkeypatch):
    service = GrafanaService(grafana_url="http://grafana.test", username="u", password="p", api_key="k")
    captured = {}

    async def _fake_mutating_request(method, path, **kwargs):
        captured["json"] = kwargs["json"]
        return {
            "datasource": {
                "id": 1,
                "uid": "ds-1",
                "orgId": 99,
                "name": "metrics",
                "type": "prometheus",
                "access": "proxy",
                "url": "http://prometheus:9090",
            }
        }

    monkeypatch.setattr(service, "_mutating_request", _fake_mutating_request)

    ds = await service.create_datasource(
        DatasourceCreate(name="metrics", type="prometheus", url="http://prometheus:9090", org_id="99")
    )

    assert captured["json"]["orgId"] == "99"
    assert ds is not None


@pytest.mark.asyncio
async def test_update_datasource_forwards_org_id_as_orgId(monkeypatch):
    service = GrafanaService(grafana_url="http://grafana.test", username="u", password="p", api_key="k")
    captured = {}

    async def _fake_get_datasource(uid):
        return Datasource(
            id=1,
            uid=uid,
            orgId=1,
            name="metrics",
            type="prometheus",
            access="proxy",
            url="http://prometheus:9090",
        )

    async def _fake_mutating_request(method, path, **kwargs):
        captured["json"] = kwargs["json"]
        return {
            "datasource": {
                "id": 1,
                "uid": "ds-1",
                "orgId": 42,
                "name": "metrics",
                "type": "prometheus",
                "access": "proxy",
                "url": "http://prometheus:9090",
            }
        }

    monkeypatch.setattr(service, "get_datasource", _fake_get_datasource)
    monkeypatch.setattr(service, "_mutating_request", _fake_mutating_request)

    updated = await service.update_datasource("ds-1", DatasourceUpdate(org_id="42"))

    assert captured["json"]["orgId"] == "42"
    assert updated is not None
