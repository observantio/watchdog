"""Tests for internal token validation route and config integration."""

from fastapi.testclient import TestClient
import pytest

from main import app
from config import config
from routers import internal_router


class DummyAuthService:
    def validate_otlp_token(self, token):
        return "org123" if token == "good" else None


@pytest.fixture(autouse=True)
def patch_auth_service(monkeypatch):
    monkeypatch.setattr(internal_router, "_auth_service", DummyAuthService())


def test_missing_header(monkeypatch):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    client = TestClient(app)
    resp = client.get("/api/internal/otlp/validate?token=good")
    assert resp.status_code == 422


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
    assert resp.status_code == 404


def test_success(monkeypatch):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    client = TestClient(app)
    resp = client.get(
        "/api/internal/otlp/validate?token=good",
        headers={"X-Internal-Token": "secret"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"org_id": "org123"}
