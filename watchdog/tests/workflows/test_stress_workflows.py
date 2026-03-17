"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.responses import JSONResponse

from config import config
from database import get_db
from main import app
from middleware import dependencies
from routers.access.auth_router import authentication as auth_routes
from routers.access.auth_router import users as user_routes
from routers.observability import alertmanager_router, loki_router, tempo_router
from routers.observability.grafana_router import proxy as grafana_proxy_router

from .helpers import WorkflowState, patch_auth_service


@pytest.mark.asyncio
async def test_concurrent_50_user_regression_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)

    class FakeQuery:
        def filter_by(self, **_kwargs: Any) -> FakeQuery:
            return self

        def first(self) -> SimpleNamespace:
            return SimpleNamespace(id=state.tenant_id)

    class FakeDB:
        def query(self, *_args: Any) -> FakeQuery:
            return FakeQuery()

    class FakeCtx:
        def __enter__(self) -> FakeDB:
            return FakeDB()

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            del exc_type, exc, tb
            return False

    async def _send_user_welcome_email(**kwargs: Any) -> bool:
        del kwargs
        return True

    async def _send_temporary_password_email(**kwargs: Any) -> bool:
        del kwargs
        return True

    async def fake_forward(**kwargs: Any) -> JSONResponse:
        path = kwargs["upstream_path"].removeprefix("/internal/v1/api/alertmanager/")
        if path == "rules":
            return JSONResponse([{"id": "rule-shared", "name": "shared-readiness"}])
        if path == "channels":
            return JSONResponse([{"id": "chan-shared", "name": "shared-email", "type": "email"}])
        raise AssertionError(f"Unexpected concurrent alertmanager path: {path}")

    async def fake_get_services(tenant_id: str | None = None) -> list[str]:
        assert tenant_id in {state.org_id, "default"}
        return ["api", "checkout", "worker"]

    async def fake_get_labels(start: int | None, end: int | None, tenant_id: str | None = None) -> dict[str, Any]:
        assert start == 1
        assert end == 2
        assert tenant_id in {state.org_id, "default"}
        return {"status": "success", "data": ["service", "level", "tenant"]}

    monkeypatch.setattr(dependencies, "enforce_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(dependencies, "enforce_ip_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(auth_routes, "rate_limit_func", lambda *args, **kwargs: None)
    monkeypatch.setattr(auth_routes, "get_db_session", lambda: FakeCtx())
    monkeypatch.setattr(auth_routes.notification_service, "send_user_welcome_email", _send_user_welcome_email)
    monkeypatch.setattr(user_routes.notification_service, "send_user_welcome_email", _send_user_welcome_email)
    monkeypatch.setattr(user_routes.notification_service, "send_temporary_password_email", _send_temporary_password_email)
    monkeypatch.setattr(grafana_proxy_router, "enforce_public_endpoint_security", lambda *args, **kwargs: None)
    monkeypatch.setattr(alertmanager_router.notifier_proxy_service, "forward", fake_forward)
    monkeypatch.setattr(tempo_router.tempo_service, "get_services", fake_get_services)
    monkeypatch.setattr(loki_router.loki_service, "get_labels", fake_get_labels)
    monkeypatch.setattr(config, "SKIP_STARTUP_DB_INIT", True)

    app.dependency_overrides[get_db] = lambda: "db"

    transport = httpx.ASGITransport(app=app)

    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
            async def register_user(index: int) -> dict[str, str]:
                username = f"stress-{index:02d}"
                password = f"Password-{index:03d}!"
                response = await async_client.post(
                    "/api/auth/register",
                    json={
                        "username": username,
                        "email": f"{username}@example.com",
                        "password": password,
                        "full_name": f"Stress User {index:02d}",
                    },
                )
                assert response.status_code == 200
                return {"id": response.json()["id"], "username": username, "password": password}

            registrations = await asyncio.gather(*(register_user(index) for index in range(50)))

            async def run_regression(user_record: dict[str, str], index: int) -> dict[str, str]:
                login_response = await async_client.post(
                    "/api/auth/login",
                    json={"username": user_record["username"], "password": user_record["password"]},
                )
                assert login_response.status_code == 200
                token = login_response.json()["access_token"]
                headers = {"Authorization": f"Bearer {token}"}

                me_response = await async_client.get("/api/auth/me", headers=headers)
                assert me_response.status_code == 200
                assert me_response.json()["username"] == user_record["username"]

                update_response = await async_client.put(
                    "/api/auth/me",
                    headers=headers,
                    json={
                        "full_name": f"Updated Stress User {index:02d}",
                        "email": f"updated-stress-{index:02d}@example.com",
                    },
                )
                assert update_response.status_code == 200

                create_key_response = await async_client.post(
                    "/api/auth/api-keys",
                    headers=headers,
                    json={"name": f"stress-key-{index:02d}", "key": f"stress-scope-{index:02d}"},
                )
                assert create_key_response.status_code == 200
                key_id = create_key_response.json()["id"]

                visible_keys_response = await async_client.get("/api/auth/api-keys", headers=headers)
                assert visible_keys_response.status_code == 200
                assert [item["id"] for item in visible_keys_response.json()] == [key_id]

                hide_key_response = await async_client.post(
                    f"/api/auth/api-keys/{key_id}/hide",
                    headers=headers,
                    json={"hidden": True},
                )
                assert hide_key_response.status_code == 200

                default_keys_after_hide = await async_client.get("/api/auth/api-keys", headers=headers)
                assert default_keys_after_hide.status_code == 200
                assert default_keys_after_hide.json() == []

                hidden_keys_response = await async_client.get("/api/auth/api-keys", headers=headers, params={"show_hidden": True})
                assert hidden_keys_response.status_code == 200
                assert hidden_keys_response.json()[0]["id"] == key_id
                assert hidden_keys_response.json()[0]["is_hidden"] is True

                rules_response = await async_client.get("/api/alertmanager/rules", headers=headers)
                assert rules_response.status_code == 200
                assert rules_response.json()[0]["name"] == "shared-readiness"

                channels_response = await async_client.get("/api/alertmanager/channels", headers=headers)
                assert channels_response.status_code == 200
                assert channels_response.json()[0]["name"] == "shared-email"

                services_response = await async_client.get("/api/tempo/services", headers=headers)
                assert services_response.status_code == 200
                assert "checkout" in services_response.json()

                labels_response = await async_client.get(
                    "/api/loki/labels",
                    headers=headers,
                    params={"start": 1, "end": 2},
                )
                assert labels_response.status_code == 200
                assert "service" in labels_response.json()["data"]

                return {"user_id": user_record["id"], "key_id": key_id}

            results = await asyncio.gather(
                *(run_regression(user_record, index) for index, user_record in enumerate(registrations))
            )

        assert len({item["id"] for item in registrations}) == 50
        assert len({item["user_id"] for item in results}) == 50
        assert len({item["key_id"] for item in results}) == 50
        assert len(state.api_keys) == 50
        assert state.next_user_id == 52
        assert state.next_api_key_id == 51
    finally:
        app.dependency_overrides.clear()