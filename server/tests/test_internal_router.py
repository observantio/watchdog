"""Tests for internal token validation route and config integration."""

from fastapi.testclient import TestClient
import pytest

from tests._env import ensure_test_env

ensure_test_env()

from main import app
from config import config
from routers import internal_router


class DummyAuthService:
    def validate_otlp_token(self, token, *, suppress_errors=True):
        return "org123" if token == "good" else None


@pytest.fixture(autouse=True)
def patch_auth_service(monkeypatch):
    # the router now delegates to an InternalService instance, so make sure
    # its auth service is replaced with our dummy implementation.
    monkeypatch.setattr(internal_router, "_auth_service", DummyAuthService())
    internal_router._internal_service._auth_service = internal_router._auth_service


def test_missing_header(monkeypatch):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    client = TestClient(app)
    resp = client.get("/api/internal/otlp/validate?token=good")
    assert resp.status_code == 422


def test_service_token_not_configured(monkeypatch):
    # if the gateway internal token is not set we surface a 500 error
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

    monkeypatch.setattr(internal_router, "_auth_service", FailingAuthService())
    # update internal_service reference as well
    internal_router._internal_service._auth_service = internal_router._auth_service
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    client = TestClient(app)
    resp = client.post(
        "/api/internal/otlp/validate",
        headers={"X-Internal-Token": "secret"},
        json={"token": "good"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Auth database unavailable"
