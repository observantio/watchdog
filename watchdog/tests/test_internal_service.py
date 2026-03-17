"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import pytest
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException

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
    with pytest.raises(HTTPException) as exc:
        svc.verify_service_token("any")
    assert exc.value.status_code == 500


def test_verify_service_token_forbidden(monkeypatch):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    svc = InternalService()
    with pytest.raises(HTTPException) as exc:
        svc.verify_service_token("wrong")
    assert exc.value.status_code == 403


def test_verify_service_token_ok(monkeypatch):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    svc = InternalService()
    svc.verify_service_token("secret")


def test_validate_otlp_token_not_found():
    svc = InternalService(auth_service=DummyAuth())
    assert svc._auth_service.validate_otlp_token("bad") is None


def test_validate_otlp_token_success():
    svc = InternalService(auth_service=DummyAuth())
    assert svc._auth_service.validate_otlp_token("good") == "org"


def test_validate_otlp_token_db_error():
    svc = InternalService(auth_service=ErrorAuth())
    with pytest.raises(SQLAlchemyError):
        svc._auth_service.validate_otlp_token("good")
