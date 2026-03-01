"""Unit tests for :mod:`services.internal_service`.

These tests exercise the logic that was previously embedded in the
router module, ensuring the layer remains thin and that errors are
translated correctly.
"""

import pytest
from sqlalchemy.exc import SQLAlchemyError

from config import config
from services.internal_service import InternalService


class DummyAuth:
    def validate_otlp_token(self, token, *, suppress_errors=True):
        return "org" if token == "good" else None


class ErrorAuth:
    def validate_otlp_token(self, token, *, suppress_errors=True):
        raise SQLAlchemyError("boom")


def test_verify_service_token_missing(monkeypatch):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", None)
    svc = InternalService()
    with pytest.raises(RuntimeError) as exc:
        svc.verify_service_token("any")
    assert "not configured" in str(exc.value)


def test_verify_service_token_forbidden(monkeypatch):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    svc = InternalService()
    with pytest.raises(PermissionError):
        svc.verify_service_token("wrong")


def test_verify_service_token_ok(monkeypatch):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    svc = InternalService()
    # should not raise
    svc.verify_service_token("secret")


def test_validate_otlp_token_not_found():
    svc = InternalService(auth_service=DummyAuth())
    with pytest.raises(LookupError):
        svc.validate_otlp_token("bad")


def test_validate_otlp_token_success():
    svc = InternalService(auth_service=DummyAuth())
    assert svc.validate_otlp_token("good") == {"org_id": "org"}


def test_validate_otlp_token_db_error():
    svc = InternalService(auth_service=ErrorAuth())
    with pytest.raises(RuntimeError) as exc:
        svc.validate_otlp_token("good")
    assert "Auth database unavailable" in str(exc.value)
