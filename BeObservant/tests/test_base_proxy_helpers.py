"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Role, TokenData
from services.proxy.base_proxy import BaseProxyService


class _Proxy(BaseProxyService):
    pass


def _user(role=Role.ADMIN, is_superuser=False):
    return TokenData(
        user_id="u1",
        username="alice",
        tenant_id="tenant-a",
        org_id="org-a",
        role=role,
        permissions=["read:users"],
        group_ids=["g1"],
        is_superuser=is_superuser,
        is_mfa_setup=False,
    )


def test_build_base_jwt_claims_and_extract_error_detail(monkeypatch):
    service = _Proxy(base_url="https://example", timeout=1.0, tls_enabled=False)
    claims = service._build_base_jwt_claims(
        current_user=_user(),
        tenant_id="tenant-a",
        issuer="issuer",
        audience="audience",
        ttl_seconds=60,
    )
    assert claims["iss"] == "issuer"
    assert claims["aud"] == "audience"
    assert claims["org_id"] == "org-a"
    assert claims["role"] == Role.ADMIN.value
    assert claims["group_ids"] == ["g1"]

    fallback_claims = service._build_base_jwt_claims(
        current_user=type("User", (), {"user_id": "u2", "username": "bob", "permissions": [], "group_ids": []})(),
        tenant_id="tenant-b",
        issuer="issuer",
        audience="audience",
        ttl_seconds=60,
    )
    assert fallback_claims["org_id"] == "tenant-b"
    assert fallback_claims["role"] == "user"

    response = httpx.Response(400, json={"detail": "bad"})
    assert service._extract_error_detail(response) == "bad"
    response = httpx.Response(400, json={"message": "boom"})
    assert service._extract_error_detail(response) == "boom"
    response = httpx.Response(400, json=["a", "b"])
    assert service._extract_error_detail(response) == '["a", "b"]'
    response = httpx.Response(400, text="plain-text")
    assert service._extract_error_detail(response) == "plain-text"


def test_write_audit_uses_session_context(monkeypatch):
    service = _Proxy(base_url="https://example", timeout=1.0, tls_enabled=False)
    added = []

    class FakeSession:
        def add(self, obj):
            added.append(obj)

    class Ctx:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("services.proxy.base_proxy.get_db_session", lambda: Ctx())
    service.write_audit(
        current_user=_user(is_superuser=True),
        action="proxy.complete",
        resource_id="/x",
        details={"ok": True},
    )

    assert added
    assert added[0].tenant_id == "tenant-a"
    assert added[0].user_id == "u1"
    assert added[0].resource_type == "proxy"


def test_write_audit_allows_anonymous_context_and_json_detail_fallback(monkeypatch):
    service = _Proxy(base_url="https://example", timeout=1.0, tls_enabled=False)
    added = []

    class FakeSession:
        def add(self, obj):
            added.append(obj)

    class Ctx:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("services.proxy.base_proxy.get_db_session", lambda: Ctx())
    service.write_audit(
        current_user=None,
        action="proxy.complete",
        resource_id="/anonymous",
        details={"ok": True},
    )

    assert added[0].tenant_id is None
    assert added[0].user_id is None
    response = httpx.Response(400, json={"other": "value"})
    assert service._extract_error_detail(response) == '{"other": "value"}'


def test_base_proxy_uses_ca_cert_path_when_tls_enabled(monkeypatch):
    captured = {}

    class DummyClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("services.proxy.base_proxy.httpx.AsyncClient", DummyClient)
    _Proxy(base_url="https://example", timeout=1.0, tls_enabled=True, ca_cert_path="/tmp/ca.pem")
    assert captured["verify"] == "/tmp/ca.pem"