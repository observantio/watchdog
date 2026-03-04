import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/observantio_test")
os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "False")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

from services.grafana.grafana_service import GrafanaAPIError, GrafanaService
from models.grafana.grafana_folder_models import Folder


@pytest.mark.asyncio
async def test_update_folder_retries_once_on_version_mismatch(monkeypatch):
    service = GrafanaService(grafana_url="http://grafana.test", username="u", password="p", api_key="k")

    state = {"calls": 0}

    async def _fake_get_folder(uid):
        return Folder(id=10, uid=uid, title="Ops", version=3 if state["calls"] == 0 else 4)

    async def _fake_mutating_request(method, path, **kwargs):
        payload = kwargs.get("json") or {}
        if state["calls"] == 0:
            state["calls"] += 1
            raise GrafanaAPIError(412, {"message": "the folder has been changed by someone else"})
        assert payload.get("overwrite") is True
        assert payload.get("version") == 4
        return {"id": 10, "uid": "f1", "title": "New Ops", "version": 5}

    monkeypatch.setattr(service, "get_folder", _fake_get_folder)
    monkeypatch.setattr(service, "_mutating_request", _fake_mutating_request)

    updated = await service.update_folder("f1", "New Ops")

    assert updated is not None
    assert updated.title == "New Ops"
