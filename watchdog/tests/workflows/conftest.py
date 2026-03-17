"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests._env import ensure_test_env

ensure_test_env()

from config import config
from database import get_db
from main import app
from middleware import dependencies
from routers.access.auth_router import authentication as auth_routes
from routers.access.auth_router import users as user_routes
from routers.observability.grafana_router import proxy as grafana_proxy_router


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def _send_user_welcome_email(**kwargs: Any) -> bool:
        del kwargs
        return True

    async def _send_temporary_password_email(**kwargs: Any) -> bool:
        del kwargs
        return True

    monkeypatch.setattr(dependencies, "enforce_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(dependencies, "enforce_ip_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(auth_routes, "rate_limit_func", lambda *args, **kwargs: None)
    monkeypatch.setattr(grafana_proxy_router, "enforce_public_endpoint_security", lambda *args, **kwargs: None)
    monkeypatch.setattr(user_routes.notification_service, "send_user_welcome_email", _send_user_welcome_email)
    monkeypatch.setattr(user_routes.notification_service, "send_temporary_password_email", _send_temporary_password_email)
    monkeypatch.setattr(config, "SKIP_STARTUP_DB_INIT", True)
    app.dependency_overrides[get_db] = lambda: "db"
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()