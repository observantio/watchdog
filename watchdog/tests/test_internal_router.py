"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from fastapi.testclient import TestClient
from fastapi import HTTPException, status
import pytest

from tests._env import ensure_test_env
from services.internal_service import InternalService
ensure_test_env()

from config import config
config.SKIP_STARTUP_DB_INIT = True

from main import app
from config import config
from routers import internal_router


class DummyAuthService:
    def validate_otlp_token(self, token, *, suppress_errors=True):
        return "org123" if token == "good" else None

class DummyInternalService:
    def __init__(self):
        self._auth_service = DummyAuthService()

    def verify_service_token(self, x_internal_token: str = None):
        return None

    def validate_token_or_404(self, token: str):
        org = self._auth_service.validate_otlp_token(token, suppress_errors=False)
        if not org:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        return {"org_id": org}



@pytest.fixture(autouse=True)
def patch_auth_service(monkeypatch):
    monkeypatch.setattr(internal_router, "internal_service", DummyInternalService())


def test_missing_header(monkeypatch):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    client = TestClient(app)
    resp = client.get("/api/internal/otlp/validate?token=good")
    assert resp.status_code == 422


def test_service_token_not_configured(monkeypatch):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", None)
    client = TestClient(app)
    resp = client.post(
        "/api/internal/otlp/validate",
        headers={"X-Internal-Token": "whatever"},
        json={"token": "good"},
    )
    assert resp.status_code == 500


def test_bad_header(monkeypatch):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    client = TestClient(app)
    resp = client.get(
        "/api/internal/otlp/validate?token=good",
        headers={"X-Internal-Token": "wrong"},
    )
    assert resp.status_code == 403


def test_invalid_token(monkeypatch):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    client = TestClient(app)
    resp = client.get(
        "/api/internal/otlp/validate?token=bad",
        headers={"X-Internal-Token": "secret"},
    )
    assert resp.status_code == 410


def test_query_path_disabled(monkeypatch):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    client = TestClient(app)
    resp = client.get(
        "/api/internal/otlp/validate?token=good",
        headers={"X-Internal-Token": "secret"},
    )
    assert resp.status_code == 410


def test_success_post_body(monkeypatch):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    client = TestClient(app)
    resp = client.post(
        "/api/internal/otlp/validate",
        headers={"X-Internal-Token": "secret"},
        json={"token": "good"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"org_id": "org123"}


def test_success_post_header_token(monkeypatch):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    client = TestClient(app)
    resp = client.post(
        "/api/internal/otlp/validate",
        headers={"X-Internal-Token": "secret", "X-OTLP-Token": "good"},
        json={},
    )
    assert resp.status_code == 200
    assert resp.json() == {"org_id": "org123"}


def test_post_invalid_token(monkeypatch):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    client = TestClient(app)
    resp = client.post(
        "/api/internal/otlp/validate",
        headers={"X-Internal-Token": "secret"},
        json={"token": "bad"},
    )
    assert resp.status_code == 404


def test_post_db_error_maps_to_503(monkeypatch):
    class FailingAuthService:
        def validate_otlp_token(self, token, *, suppress_errors=True):
            raise RuntimeError("db down")

    monkeypatch.setattr(internal_router, "internal_service", InternalService(auth_service=FailingAuthService()))
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    client = TestClient(app)
    resp = client.post(
        "/api/internal/otlp/validate",
        headers={"X-Internal-Token": "secret"},
        json={"token": "good"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Auth database unavailable"
