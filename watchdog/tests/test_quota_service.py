"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests._env import ensure_test_env

ensure_test_env()

from db_models import Base, Tenant, User, UserApiKey
from models.access.auth_models import Role, TokenData
from services import quota_service as quota_module


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db):
    db.add(Tenant(id="t1", name="tenant-t1", display_name="T1", is_active=True))
    db.add(
        User(
            id="u1",
            tenant_id="t1",
            username="u1",
            email="u1@example.com",
            hashed_password="x",
            org_id="org-1",
            is_active=True,
        )
    )
    db.add(
        UserApiKey(
            id="k1",
            tenant_id="t1",
            user_id="u1",
            name="K1",
            key="scope-1",
            is_default=False,
            is_enabled=True,
        )
    )
    db.commit()


def _token():
    return TokenData(
        user_id="u1",
        username="u1",
        tenant_id="t1",
        org_id="org-1",
        role=Role.USER,
        permissions=[],
    )


@pytest.mark.asyncio
async def test_quota_service_uses_native_when_complete(monkeypatch):
    db = _session()
    _seed(db)

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(quota_module, "get_db_session", fake_session)
    monkeypatch.setattr(quota_module.config, "MAX_API_KEYS_PER_USER", 10, raising=False)
    monkeypatch.setattr(quota_module.config, "QUOTA_NATIVE_ENABLED", True, raising=False)
    monkeypatch.setattr(quota_module.config, "QUOTA_PROMETHEUS_ENABLED", True, raising=False)
    monkeypatch.setattr(quota_module.config, "LOKI_QUOTA_NATIVE_PATH", "/native/loki", raising=False)
    monkeypatch.setattr(quota_module.config, "TEMPO_QUOTA_NATIVE_PATH", "/native/tempo", raising=False)
    monkeypatch.setattr(quota_module.config, "LOKI_QUOTA_NATIVE_LIMIT_FIELD", "limit", raising=False)
    monkeypatch.setattr(quota_module.config, "LOKI_QUOTA_NATIVE_USED_FIELD", "used", raising=False)
    monkeypatch.setattr(quota_module.config, "TEMPO_QUOTA_NATIVE_LIMIT_FIELD", "limit", raising=False)
    monkeypatch.setattr(quota_module.config, "TEMPO_QUOTA_NATIVE_USED_FIELD", "used", raising=False)
    monkeypatch.setattr(quota_module.config, "LOKI_URL", "http://loki:3100", raising=False)
    monkeypatch.setattr(quota_module.config, "TEMPO_URL", "http://tempo:3200", raising=False)

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            if "native/loki" in url:
                return _Response({"limit": 120.0, "used": 45.0})
            if "native/tempo" in url:
                return _Response({"limit": 90.0, "used": 30.0})
            return _Response({})

    monkeypatch.setattr(quota_module.httpx, "AsyncClient", _Client)

    out = await quota_module.quota_service.get_quotas(_token())
    assert out.api_keys.current == 1
    assert out.api_keys.max == 10
    assert out.loki.source == "native"
    assert out.loki.status == "ok"
    assert out.tempo.source == "native"
    assert out.tempo.status == "ok"


@pytest.mark.asyncio
async def test_quota_service_falls_back_to_prometheus(monkeypatch):
    db = _session()
    _seed(db)

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(quota_module, "get_db_session", fake_session)
    monkeypatch.setattr(quota_module.config, "QUOTA_NATIVE_ENABLED", True, raising=False)
    monkeypatch.setattr(quota_module.config, "QUOTA_PROMETHEUS_ENABLED", True, raising=False)
    monkeypatch.setattr(quota_module.config, "LOKI_QUOTA_NATIVE_PATH", "/native/loki", raising=False)
    monkeypatch.setattr(quota_module.config, "TEMPO_QUOTA_NATIVE_PATH", "/native/tempo", raising=False)
    monkeypatch.setattr(quota_module.config, "LOKI_QUOTA_PROM_LIMIT_QUERY", "loki_limit{tenant=\"{tenant_id}\"}", raising=False)
    monkeypatch.setattr(quota_module.config, "LOKI_QUOTA_PROM_USED_QUERY", "loki_used{tenant=\"{tenant_id}\"}", raising=False)
    monkeypatch.setattr(quota_module.config, "TEMPO_QUOTA_PROM_LIMIT_QUERY", "tempo_limit{tenant=\"{tenant_id}\"}", raising=False)
    monkeypatch.setattr(quota_module.config, "TEMPO_QUOTA_PROM_USED_QUERY", "tempo_used{tenant=\"{tenant_id}\"}", raising=False)
    monkeypatch.setattr(quota_module.config, "QUOTA_PROMETHEUS_BASE_URL", "http://mimir:9009", raising=False)

    class _Response:
        def __init__(self, payload=None, fail=False):
            self._payload = payload or {}
            self._fail = fail

        def raise_for_status(self):
            if self._fail:
                raise httpx.HTTPStatusError("bad", request=httpx.Request("GET", "http://x"), response=httpx.Response(500))

        def json(self):
            return self._payload

    def _prom_payload(value):
        return {"status": "success", "data": {"resultType": "vector", "result": [{"value": [123, str(value)]}]}}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            if "/native/" in url:
                return _Response(fail=True)
            query = (kwargs.get("params") or {}).get("query", "")
            if "loki_limit" in query:
                return _Response(_prom_payload(200))
            if "loki_used" in query:
                return _Response(_prom_payload(80))
            if "tempo_limit" in query:
                return _Response(_prom_payload(300))
            if "tempo_used" in query:
                return _Response(_prom_payload(120))
            return _Response({"status": "success", "data": {"result": []}})

    monkeypatch.setattr(quota_module.httpx, "AsyncClient", _Client)

    out = await quota_module.quota_service.get_quotas(_token())
    assert out.loki.source == "prometheus"
    assert out.loki.status == "ok"
    assert out.loki.limit == 200
    assert out.loki.used == 80
    assert out.tempo.source == "prometheus"
    assert out.tempo.status == "ok"


@pytest.mark.asyncio
async def test_quota_service_reports_unavailable_when_sources_fail(monkeypatch):
    db = _session()
    _seed(db)

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(quota_module, "get_db_session", fake_session)
    monkeypatch.setattr(quota_module.config, "QUOTA_NATIVE_ENABLED", False, raising=False)
    monkeypatch.setattr(quota_module.config, "QUOTA_PROMETHEUS_ENABLED", False, raising=False)
    monkeypatch.setattr(quota_module.config, "LOKI_QUOTA_NATIVE_PATH", "", raising=False)
    monkeypatch.setattr(quota_module.config, "TEMPO_QUOTA_NATIVE_PATH", "", raising=False)
    monkeypatch.setattr(quota_module.config, "LOKI_QUOTA_PROM_LIMIT_QUERY", "", raising=False)
    monkeypatch.setattr(quota_module.config, "LOKI_QUOTA_PROM_USED_QUERY", "", raising=False)
    monkeypatch.setattr(quota_module.config, "TEMPO_QUOTA_PROM_LIMIT_QUERY", "", raising=False)
    monkeypatch.setattr(quota_module.config, "TEMPO_QUOTA_PROM_USED_QUERY", "", raising=False)

    out = await quota_module.quota_service.get_quotas(_token())
    assert out.loki.status == "unavailable"
    assert out.tempo.status == "unavailable"
    assert out.loki.source == "none"
    assert out.tempo.source == "none"


@pytest.mark.asyncio
async def test_quota_service_degraded_message_reflects_partial_data(monkeypatch):
    db = _session()
    _seed(db)

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(quota_module, "get_db_session", fake_session)
    monkeypatch.setattr(quota_module.config, "QUOTA_NATIVE_ENABLED", True, raising=False)
    monkeypatch.setattr(quota_module.config, "QUOTA_PROMETHEUS_ENABLED", False, raising=False)
    monkeypatch.setattr(quota_module.config, "LOKI_QUOTA_NATIVE_PATH", "/native/loki", raising=False)
    monkeypatch.setattr(quota_module.config, "TEMPO_QUOTA_NATIVE_PATH", "/native/tempo", raising=False)
    monkeypatch.setattr(quota_module.config, "LOKI_QUOTA_NATIVE_LIMIT_FIELD", "limit", raising=False)
    monkeypatch.setattr(quota_module.config, "LOKI_QUOTA_NATIVE_USED_FIELD", "used", raising=False)
    monkeypatch.setattr(quota_module.config, "TEMPO_QUOTA_NATIVE_LIMIT_FIELD", "limit", raising=False)
    monkeypatch.setattr(quota_module.config, "TEMPO_QUOTA_NATIVE_USED_FIELD", "used", raising=False)
    monkeypatch.setattr(quota_module.config, "LOKI_URL", "http://loki:3100", raising=False)
    monkeypatch.setattr(quota_module.config, "TEMPO_URL", "http://tempo:3200", raising=False)

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            if "native/loki" in url:
                return _Response({"limit": 120.0, "used": 45.0})
            if "native/tempo" in url:
                return _Response({"used": 1771.0})
            return _Response({})

    monkeypatch.setattr(quota_module.httpx, "AsyncClient", _Client)

    out = await quota_module.quota_service.get_quotas(_token())
    assert out.tempo.status == "degraded"
    assert out.tempo.used == 1771.0
    assert out.tempo.limit is None
    assert out.tempo.message
    assert "usage is available" in out.tempo.message.lower()
    assert "unavailable" not in out.tempo.message.lower()


@pytest.mark.asyncio
async def test_quota_service_merges_native_partial_values_across_candidates(monkeypatch):
    db = _session()
    _seed(db)

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(quota_module, "get_db_session", fake_session)
    monkeypatch.setattr(quota_module.config, "QUOTA_NATIVE_ENABLED", True, raising=False)
    monkeypatch.setattr(quota_module.config, "QUOTA_PROMETHEUS_ENABLED", False, raising=False)
    monkeypatch.setattr(quota_module.config, "LOKI_QUOTA_NATIVE_PATH", "/native/loki", raising=False)
    monkeypatch.setattr(quota_module.config, "TEMPO_QUOTA_NATIVE_PATH", "/status/overrides", raising=False)
    monkeypatch.setattr(quota_module.config, "LOKI_QUOTA_NATIVE_LIMIT_FIELD", "limit", raising=False)
    monkeypatch.setattr(quota_module.config, "LOKI_QUOTA_NATIVE_USED_FIELD", "used", raising=False)
    monkeypatch.setattr(quota_module.config, "TEMPO_QUOTA_NATIVE_LIMIT_FIELD", "max_traces_per_user", raising=False)
    monkeypatch.setattr(quota_module.config, "TEMPO_QUOTA_NATIVE_USED_FIELD", "used", raising=False)
    monkeypatch.setattr(quota_module.config, "LOKI_URL", "http://loki:3100", raising=False)
    monkeypatch.setattr(quota_module.config, "TEMPO_URL", "http://tempo:3200", raising=False)

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            if "native/loki" in url:
                return _Response({"limit": 120.0, "used": 45.0})
            if "/status/overrides" in url:
                return _Response({"used": 1771.0})
            if "/status/config" in url:
                return _Response({"max_traces_per_user": 50000.0})
            return _Response({})

    monkeypatch.setattr(quota_module.httpx, "AsyncClient", _Client)

    out = await quota_module.quota_service.get_quotas(_token())
    assert out.tempo.source == "native"
    assert out.tempo.status == "ok"
    assert out.tempo.used == 1771.0
    assert out.tempo.limit == 50000.0
