"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import importlib
import json
import runpy
import sys
import types

import pytest

from tests._env import ensure_test_env

ensure_test_env()


def _load_main(monkeypatch):
    if "main" in sys.modules:
        del sys.modules["main"]

    import config as config_module
    import database as database_module

    monkeypatch.setattr(config_module.config, "SKIP_STARTUP_DB_INIT", True)
    monkeypatch.setattr(config_module.config, "ENABLE_API_DOCS", True)
    monkeypatch.setattr(config_module.config, "HOST", "127.0.0.1")
    monkeypatch.setattr(config_module.config, "PORT", 4319)
    monkeypatch.setattr(config_module.config, "LOG_LEVEL", "info")
    monkeypatch.setattr(config_module.config, "CORS_ORIGINS", ["http://localhost:5173"])
    monkeypatch.setattr(config_module.config, "CORS_ALLOW_CREDENTIALS", True)
    monkeypatch.setattr(config_module.config, "MAX_REQUEST_BYTES", 1024)
    monkeypatch.setattr(config_module.config, "MAX_CONCURRENT_REQUESTS", 2)
    monkeypatch.setattr(config_module.config, "CONCURRENCY_ACQUIRE_TIMEOUT", 0.1)
    monkeypatch.setattr(database_module, "connection_test", lambda: True)
    return importlib.import_module("main")


@pytest.mark.asyncio
async def test_root_health_and_ready(monkeypatch):
    main_module = _load_main(monkeypatch)
    root_payload = await main_module.root()
    assert root_payload["service"]
    assert root_payload["health"] == "/health"

    health_payload = await main_module.health()
    assert health_payload["status"] == "Healthy"

    monkeypatch.setattr(main_module, "connection_test", lambda: True)

    async def ok_reachable(url):
        return True

    monkeypatch.setattr(main_module, "_upstream_reachable", ok_reachable)
    ready_response = await main_module.ready()
    assert ready_response.status_code == 200
    assert json.loads(ready_response.body.decode("utf-8"))["status"] == "ready"

    async def failing_reachable(url):
        return False

    monkeypatch.setattr(main_module, "_upstream_reachable", failing_reachable)
    not_ready = await main_module.ready()
    assert not_ready.status_code == 503


@pytest.mark.asyncio
async def test_upstream_reachable_and_lifespan_cleanup(monkeypatch):
    main_module = _load_main(monkeypatch)

    class FakeClient:
        def __init__(self, response=None, error=None, *args, **kwargs):
            self.response = response
            self.error = error

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            if self.error:
                raise self.error
            return self.response

    monkeypatch.setattr(main_module.httpx, "AsyncClient", lambda **kwargs: FakeClient(response=types.SimpleNamespace(status_code=204)))
    assert await main_module._upstream_reachable("http://tempo") is True
    monkeypatch.setattr(main_module.httpx, "AsyncClient", lambda **kwargs: FakeClient(error=main_module.httpx.ConnectError("down")))
    assert await main_module._upstream_reachable("http://tempo") is False

    class Closable:
        def __init__(self):
            self.closed = 0

        async def aclose(self):
            self.closed += 1

    shared = Closable()
    extra = Closable()
    monkeypatch.setattr(main_module.tempo_router, "tempo_service", types.SimpleNamespace(_client=shared), raising=False)
    monkeypatch.setattr(main_module.loki_router, "loki_service", types.SimpleNamespace(_client=shared), raising=False)
    monkeypatch.setattr(main_module.alertmanager_router, "alertmanager_service", types.SimpleNamespace(_client=extra), raising=False)
    monkeypatch.setattr(main_module.alertmanager_router, "notification_service", types.SimpleNamespace(), raising=False)
    monkeypatch.setattr(main_module.grafana_router, "grafana_service", types.SimpleNamespace(_client=None, _mimir_client=extra), raising=False)
    monkeypatch.setattr(main_module.agents_router, "_mimir_client", extra, raising=False)

    async with main_module.lifespan(main_module.app):
        pass

    assert shared.closed == 1
    assert extra.closed == 1


@pytest.mark.asyncio
async def test_lifespan_without_clients_is_a_noop(monkeypatch):
    main_module = _load_main(monkeypatch)
    monkeypatch.setattr(main_module.tempo_router, "tempo_service", types.SimpleNamespace(_client=None), raising=False)
    monkeypatch.setattr(main_module.loki_router, "loki_service", None, raising=False)
    monkeypatch.setattr(main_module.alertmanager_router, "alertmanager_service", None, raising=False)
    monkeypatch.setattr(main_module.alertmanager_router, "notification_service", None, raising=False)
    monkeypatch.setattr(main_module.grafana_router, "grafana_service", types.SimpleNamespace(_client=None, _mimir_client=None), raising=False)
    monkeypatch.setattr(main_module.agents_router, "_mimir_client", None, raising=False)

    async with main_module.lifespan(main_module.app):
        pass


def test_dunder_main_runs_uvicorn(monkeypatch):
    _load_main(monkeypatch)
    captured = {}
    monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=lambda app, **kwargs: captured.update({"app": app, **kwargs})))
    runpy.run_module("main", run_name="__main__")
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 4319
    assert captured["loop"] == "uvloop"