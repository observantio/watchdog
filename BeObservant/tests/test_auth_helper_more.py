"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from types import SimpleNamespace
import sys

import pytest
from fastapi import HTTPException, Request, Response

from tests._env import ensure_test_env

ensure_test_env()

from db_models import AuditLog, User
from models.access.auth_models import Permission, Role, TokenData
from services.auth import helper as auth_helper


def _request(scope_overrides=None):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "scheme": "http",
        "headers": [],
        "client": ("127.0.0.1", 1234),
    }
    if scope_overrides:
        scope.update(scope_overrides)
    return Request(scope)


class FakeQuery:
    def __init__(self):
        self.filters = []
        self.outerjoins = []

    def outerjoin(self, *args, **kwargs):
        self.outerjoins.append((args, kwargs))
        return self

    def filter(self, criterion):
        self.filters.append(criterion)
        return self


class FakeDB:
    def __init__(self):
        self.query_obj = FakeQuery()

    def query(self, *args, **kwargs):
        return self.query_obj


def test_invalidate_grafana_proxy_auth_cache_paths(monkeypatch):
    called = []
    fake_module = SimpleNamespace(clear_proxy_auth_cache=lambda: called.append(True))
    monkeypatch.setitem(sys.modules, "services.grafana.proxy_auth_ops", fake_module)
    auth_helper.invalidate_grafana_proxy_auth_cache()
    assert called == [True]

    monkeypatch.setitem(sys.modules, "services.grafana.proxy_auth_ops", SimpleNamespace())
    warnings = []
    monkeypatch.setattr(auth_helper.logger, "warning", lambda *args, **kwargs: warnings.append(args))
    auth_helper.invalidate_grafana_proxy_auth_cache()
    assert warnings


def test_admin_permission_gate_and_cookie_clear(monkeypatch):
    user = TokenData(user_id="u1", username="name", tenant_id="t1", org_id="o1", role=Role.USER, permissions=[])
    with pytest.raises(HTTPException, match="Admin role required"):
        auth_helper.require_admin_with_audit_permission(user)

    admin = TokenData(user_id="u2", username="admin", tenant_id="t1", org_id="o1", role=Role.ADMIN, permissions=[Permission.READ_AUDIT_LOGS.value])
    assert auth_helper.require_admin_with_audit_permission(admin) == admin

    response = Response()
    monkeypatch.setattr(auth_helper, "cookie_secure", lambda request: True)
    monkeypatch.setattr(auth_helper.config, "FORCE_SECURE_COOKIES", False)
    auth_helper.clear_auth_cookie(_request(), response)
    header = response.headers.get("set-cookie", "")
    assert "Max-Age=0" in header
    assert "secure" in header.lower()


def test_audit_helpers_and_filters(monkeypatch):
    assert auth_helper.audit_key_is_sensitive("jwt_token") is True
    assert auth_helper.audit_key_is_sensitive("status_code") is False
    assert auth_helper.redact_query_string("code=123&ok=yes") == "code=%5BREDACTED%5D&ok=yes"
    assert auth_helper.sanitize_resource_id("https://host/path?token=abc&x=1") == "https://host/path?token=%5BREDACTED%5D&x=1"
    assert auth_helper.sanitize_audit_details(None) == {}

    db = FakeDB()
    actor = User
    superuser = TokenData(user_id="u1", username="su", tenant_id="t1", org_id="o1", role=Role.ADMIN, permissions=[], is_superuser=True)
    auth_helper.build_audit_log_query(db, superuser, "tenant-x", actor)
    assert db.query_obj.outerjoins
    assert db.query_obj.filters

    query = FakeQuery()
    filtered = auth_helper.apply_audit_filters_func(query, "start", "end", "user-1", "login", "users", q="needle")
    assert filtered is query
    assert len(query.filters) == 6


def test_role_permission_admin_and_rate_limit_delegate(monkeypatch):
    assert Permission.READ_ALERTS.value in auth_helper.role_permission_strings(Role.ADMIN)
    assert auth_helper.perms_check(TokenData(user_id="u1", username="x", tenant_id="t1", org_id="o1", role=Role.USER, permissions=["a", "b"])) == {"a", "b"}
    assert auth_helper.is_admin_check(TokenData(user_id="u2", username="x", tenant_id="t1", org_id="o1", role=Role.ADMIN, permissions=[])) is True

    calls = []
    monkeypatch.setattr(auth_helper, "enforce_public_endpoint_security", lambda request, **kwargs: calls.append(kwargs))
    monkeypatch.setattr(auth_helper.config, "AUTH_PUBLIC_IP_ALLOWLIST", ["127.0.0.1"])
    auth_helper.rate_limit_func(_request(), "scope-a", 5, 60)
    assert calls == [{"scope": "scope-a", "limit": 5, "window_seconds": 60, "allowlist": ["127.0.0.1"]}]
