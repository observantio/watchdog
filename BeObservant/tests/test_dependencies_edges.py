"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import types

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import Request

from tests._env import ensure_test_env

ensure_test_env()

from middleware import dependencies
from models.access.auth_models import Role, TokenData


def _request(
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    cookies: bytes | None = None,
    client: tuple[str, int] | None = ("127.0.0.1", 1234),
) -> Request:
    raw_headers = list(headers or [])
    if cookies is not None:
        raw_headers.append((b"cookie", cookies))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/api/test",
            "headers": raw_headers,
            "client": client,
            "scheme": "http",
            "query_string": b"",
        }
    )


def _token_data(**overrides) -> TokenData:
    values = {
        "user_id": "u1",
        "username": "user-1",
        "tenant_id": "tenant-a",
        "org_id": "org-a",
        "role": Role.USER,
        "is_superuser": False,
        "permissions": ["read:traces"],
        "group_ids": [],
        "iat": 100,
        "is_mfa_setup": False,
    }
    values.update(overrides)
    return TokenData(**values)


@pytest.mark.asyncio
async def test_dependency_helpers_for_tenant_and_allowlist_edges(monkeypatch):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="header-token")
    assert dependencies._extract_bearer_token(_request(), creds) == "header-token"
    assert dependencies._extract_bearer_token(_request(cookies=b"beobservant_token=cookie-token"), None) == "cookie-token"
    assert dependencies._extract_bearer_token(_request(), None) is None

    req = _request()
    current_user = _token_data(org_id="org-a")
    assert await dependencies.resolve_tenant_id(req, current_user) == "org-a"
    assert await dependencies.resolve_tenant_id(_request(headers=[(b"x-scope-orgid", b" ")]), current_user) == "org-a"
    assert await dependencies.resolve_tenant_id(_request(headers=[(b"x-scope-orgid", b"org-a")]), current_user) == "org-a"
    assert await dependencies.resolve_tenant_id(_request(headers=[(b"x-scope-orgid", b"org-b")]), _token_data(is_superuser=True)) == "org-b"

    async def run_sync(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(dependencies, "run_in_threadpool", run_sync)
    monkeypatch.setattr(dependencies, "_load_allowed_scope_ids_for_user", lambda **kwargs: {"org-a"})
    with pytest.raises(HTTPException) as not_allowed:
        await dependencies.resolve_tenant_id(_request(headers=[(b"x-scope-orgid", b"org-b")]), current_user)
    assert not_allowed.value.status_code == 403

    monkeypatch.setattr(dependencies, "_load_allowed_scope_ids_for_user", lambda **kwargs: (_ for _ in ()).throw(SQLAlchemyError("db")))
    with pytest.raises(HTTPException) as load_error:
        await dependencies.resolve_tenant_id(_request(headers=[(b"x-scope-orgid", b"org-b")]), current_user)
    assert load_error.value.status_code == 500

    monkeypatch.setattr(dependencies, "_load_allowed_scope_ids_for_user", lambda **kwargs: {"org-a", "org-b"})
    monkeypatch.setattr(dependencies, "_scope_exists_in_other_tenants", lambda **kwargs: (_ for _ in ()).throw(SQLAlchemyError("db")))
    with pytest.raises(HTTPException) as scope_error:
        await dependencies.resolve_tenant_id(_request(headers=[(b"x-scope-orgid", b"org-b")]), current_user)
    assert scope_error.value.status_code == 500

    calls = []
    monkeypatch.setattr(dependencies, "enforce_rate_limit", lambda **kwargs: calls.append(kwargs))
    dependencies.apply_scoped_rate_limit(current_user, "tempo")
    assert calls == [{"key": "user:u1:tempo", "limit": dependencies.config.RATE_LIMIT_USER_PER_MINUTE, "window_seconds": 60}]

    naive_user = types.SimpleNamespace(session_invalid_before=datetime.utcfromtimestamp(101))
    with pytest.raises(HTTPException) as revoked:
        dependencies._enforce_session_revocation(naive_user, _token_data(iat=100))
    assert revoked.value.status_code == 401

    assert dependencies._parse_ip_allowlist(None) == []
    parsed = dependencies._parse_ip_allowlist("127.0.0.1, 2001:db8::1")
    assert [str(item) for item in parsed] == ["127.0.0.1/32", "2001:db8::1/128"]
    with pytest.raises(HTTPException) as bad_allowlist:
        dependencies._parse_ip_allowlist("bad-ip")
    assert bad_allowlist.value.status_code == 403

    monkeypatch.setattr(dependencies, "client_ip", lambda request: "127.0.0.1")
    dependencies.enforce_ip_allowlist(_request(), None, scope="public")
    monkeypatch.setattr(dependencies.config, "ALLOWLIST_FAIL_OPEN", True)
    dependencies.enforce_ip_allowlist(_request(), "", scope="public")
    monkeypatch.setattr(dependencies.config, "ALLOWLIST_FAIL_OPEN", False)
    with pytest.raises(HTTPException, match="Access denied"):
        dependencies.enforce_ip_allowlist(_request(), "", scope="public")
    with pytest.raises(HTTPException, match="Access denied"):
        monkeypatch.setattr(dependencies, "client_ip", lambda request: "bad-ip") or dependencies.enforce_ip_allowlist(_request(), "127.0.0.1", scope="public")
    monkeypatch.setattr(dependencies, "client_ip", lambda request: "127.0.0.1")
    dependencies.enforce_ip_allowlist(_request(), "127.0.0.1", scope="public")
    monkeypatch.setattr(dependencies, "client_ip", lambda request: "198.51.100.4")
    with pytest.raises(HTTPException, match="Access denied"):
        dependencies.enforce_ip_allowlist(_request(client=("198.51.100.4", 1)), "127.0.0.1", scope="public")

    ip_rate_calls = []
    monkeypatch.setattr(dependencies, "enforce_ip_rate_limit", lambda *args, **kwargs: ip_rate_calls.append(kwargs))
    monkeypatch.setattr(dependencies, "client_ip", lambda request: "unknown")
    monkeypatch.setattr(dependencies.config, "REQUIRE_CLIENT_IP_FOR_PUBLIC_ENDPOINTS", True)
    with pytest.raises(HTTPException, match="Access denied"):
        dependencies.enforce_public_endpoint_security(_request(client=None), scope="public", limit=1, window_seconds=60)
    monkeypatch.setattr(dependencies, "client_ip", lambda request: "127.0.0.1")
    dependencies.enforce_public_endpoint_security(_request(), scope="public", limit=2, window_seconds=30, fallback_mode="allow")
    assert ip_rate_calls == [{"scope": "public", "limit": 2, "window_seconds": 30, "fallback_mode": "allow"}]
    with pytest.raises(ValueError, match="fallback_mode"):
        dependencies.enforce_public_endpoint_security(_request(), scope="public", limit=2, window_seconds=30, fallback_mode="bad")

    dependencies.enforce_header_token(_request(), header_name="x-test", expected_token=None, unauthorized_detail="bad")
    with pytest.raises(HTTPException) as unauthorized:
        dependencies.enforce_header_token(_request(), header_name="x-test", expected_token="secret", unauthorized_detail="bad")
    assert unauthorized.value.status_code == 401
    dependencies.enforce_header_token(_request(headers=[(b"x-test", b"secret")]), header_name="x-test", expected_token="secret", unauthorized_detail="bad")


def test_load_allowed_org_ids_and_scope_conflict(monkeypatch):
    class QueryStub:
        def __init__(self, value):
            self.value = value

        def filter_by(self, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def join(self, *args, **kwargs):
            return self

        def all(self):
            return self.value

        def first(self):
            return self.value

    class DbStub:
        def __init__(self):
            self.calls = 0

        def query(self, model):
            self.calls += 1
            if self.calls == 1:
                return QueryStub(types.SimpleNamespace(is_active=True, org_id="org-live"))
            if self.calls == 2:
                return QueryStub([("org-own",), (None,)])
            if self.calls == 3:
                return QueryStub([("org-shared",)])
            return QueryStub((1,))

    db = DbStub()

    @contextmanager
    def session():
        yield db

    monkeypatch.setattr(dependencies, "get_db_session", session)
    allowed = dependencies._load_allowed_org_ids_for_user(current_user=_token_data(), default_org_id="org-default")
    assert allowed == {"org-live", "org-own", "org-shared", "org-default"}
    assert dependencies._scope_exists_in_other_tenants(org_id="org-own", tenant_id="tenant-a") is True


def test_dependency_helper_misc_branches(monkeypatch):
    assert dependencies._normalize_group_ids([" a ", "", "a", "b"]) == ["a", "b"]
    assert set(dependencies._normalize_group_ids({" a ", "b"})) == {"a", "b"}
    assert dependencies._normalize_group_ids(object()) == []
    assert dependencies._validate_rate_limit_fallback_mode(" ") is None
    assert dependencies._validate_rate_limit_fallback_mode(" MEMORY ") == "memory"
    assert dependencies._scope_exists_in_other_tenants(scope_id=None, org_id=None, tenant_id="tenant-a") is False
    assert [str(item) for item in dependencies._parse_ip_allowlist("10.0.0.0/24")] == ["10.0.0.0/24"]
    assert [str(item) for item in dependencies._parse_ip_allowlist("127.0.0.1, ,10.0.0.1")] == ["127.0.0.1/32", "10.0.0.1/32"]

    class QueryStub:
        def filter_by(self, **kwargs):
            return self

        def first(self):
            return types.SimpleNamespace(is_active=False)

    @contextmanager
    def session():
        yield types.SimpleNamespace(query=lambda model: QueryStub())

    monkeypatch.setattr(dependencies, "get_db_session", session)
    assert dependencies._load_allowed_scope_ids_for_user(
        current_user=_token_data(),
        default_scope_id="org-default",
    ) == {"org-default"}


def test_current_user_and_permission_dependency_edges(monkeypatch):
    with pytest.raises(HTTPException, match="Authentication required"):
        dependencies.get_current_user(_request(), None)

    auth_stub = types.SimpleNamespace(
        decode_token=lambda token: None,
        get_user_by_id=lambda user_id: None,
        get_user_permissions=lambda user: [],
    )
    monkeypatch.setattr(dependencies, "auth_service", auth_stub)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
    with pytest.raises(HTTPException, match="expired or your token is invalid"):
        dependencies.get_current_user(_request(), creds)

    mfa_token = _token_data(is_mfa_setup=True)
    monkeypatch.setattr(auth_stub, "decode_token", lambda token: mfa_token)
    with pytest.raises(HTTPException, match="MFA setup token"):
        dependencies.get_current_user(_request(), creds)

    inactive_user = types.SimpleNamespace(is_active=False)
    monkeypatch.setattr(auth_stub, "decode_token", lambda token: _token_data())
    monkeypatch.setattr(auth_stub, "get_user_by_id", lambda user_id: inactive_user)
    with pytest.raises(HTTPException, match="User not found or inactive"):
        dependencies.get_current_user(_request(), creds)

    live_user = types.SimpleNamespace(is_active=True, org_id="org-live", group_ids=(" g1 ", "", 2), session_invalid_before=None)
    monkeypatch.setattr(auth_stub, "get_user_by_id", lambda user_id: live_user)
    monkeypatch.setattr(auth_stub, "get_user_permissions", lambda user: ["read:traces", "write:traces"])
    rate_limit_calls = []
    monkeypatch.setattr(dependencies, "enforce_rate_limit", lambda **kwargs: rate_limit_calls.append(kwargs))
    resolved = dependencies.get_current_user(_request(), creds)
    assert resolved.org_id == "org-live"
    assert resolved.permissions == ["read:traces", "write:traces"]
    assert resolved.group_ids == ["g1", "2"]
    assert rate_limit_calls[0]["key"] == "user:u1"

    with pytest.raises(HTTPException, match="You need to log in"):
        dependencies.get_current_user_or_mfa_setup(_request(), None)

    monkeypatch.setattr(auth_stub, "decode_token", lambda token: None)
    with pytest.raises(HTTPException, match="expired or your token is invalid"):
        dependencies.get_current_user_or_mfa_setup(_request(), creds)

    mfa_user = types.SimpleNamespace(is_active=True, mfa_enabled=False, session_invalid_before=None)
    monkeypatch.setattr(auth_stub, "decode_token", lambda token: _token_data(is_mfa_setup=True))
    monkeypatch.setattr(auth_stub, "get_user_by_id", lambda user_id: mfa_user)
    assert dependencies.get_current_user_or_mfa_setup(_request(), creds).is_mfa_setup is True

    mfa_enabled_user = types.SimpleNamespace(is_active=True, mfa_enabled=True, session_invalid_before=None)
    monkeypatch.setattr(auth_stub, "get_user_by_id", lambda user_id: mfa_enabled_user)
    with pytest.raises(HTTPException, match="MFA setup not permitted"):
        dependencies.get_current_user_or_mfa_setup(_request(), creds)

    decode_calls = []
    user_calls = []
    monkeypatch.setattr(auth_stub, "decode_token", lambda token: decode_calls.append(token) or _token_data(is_mfa_setup=False))
    monkeypatch.setattr(auth_stub, "get_user_by_id", lambda user_id: user_calls.append(user_id) or live_user)
    rate_limit_calls.clear()
    resolved_non_mfa = dependencies.get_current_user_or_mfa_setup(_request(), creds)
    assert resolved_non_mfa.permissions == ["read:traces", "write:traces"]
    assert len(decode_calls) == 1
    assert len(user_calls) == 1
    assert len(rate_limit_calls) == 1

    allowed_user = _token_data(permissions=["read:traces"])
    with pytest.raises(HTTPException, match="READ:USERS"):
        dependencies.require_permission("read:users")(allowed_user)
    assert dependencies.require_permission("read:traces")(_token_data(permissions=["read:traces"]))

    scoped_calls = []
    monkeypatch.setattr(dependencies, "apply_scoped_rate_limit", lambda current_user, scope: scoped_calls.append((current_user.user_id, scope)))
    assert dependencies.require_permission_with_scope("read:traces", "tempo")(_token_data(permissions=["read:traces"]))
    assert scoped_calls[-1] == ("u1", "tempo")

    any_checker = dependencies.require_any_permission(["read:users", "read:traces"])
    assert any_checker(_token_data(permissions=["read:traces"]))
    assert any_checker(_token_data(is_superuser=True, permissions=[]))
    with pytest.raises(HTTPException, match="READ:USERS, READ:TRACES"):
        any_checker(_token_data(permissions=[]))

    any_scoped = dependencies.require_any_permission_with_scope(["read:traces"], "agents")
    assert any_scoped(_token_data(permissions=["read:traces"]))
    assert scoped_calls[-1] == ("u1", "agents")

    authenticated = dependencies.require_authenticated_with_scope("loki")
    assert authenticated(_token_data())
    assert scoped_calls[-1] == ("u1", "loki")


def test_scope_aware_current_user_skips_base_rate_limit(monkeypatch):
    auth_stub = types.SimpleNamespace(
        decode_token=lambda token: _token_data(),
        get_user_by_id=lambda user_id: types.SimpleNamespace(
            is_active=True,
            org_id="org-live",
            group_ids=[],
            session_invalid_before=None,
        ),
        get_user_permissions=lambda user: ["read:traces"],
    )
    monkeypatch.setattr(dependencies, "auth_service", auth_stub)
    rate_limit_calls = []
    monkeypatch.setattr(dependencies, "enforce_rate_limit", lambda **kwargs: rate_limit_calls.append(kwargs))

    resolved = dependencies._scope_aware_current_user(
        _request(),
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
    )

    assert resolved.org_id == "org-live"
    assert resolved.permissions == ["read:traces"]
    assert rate_limit_calls == []


def test_scope_aware_current_user_dependency_does_not_require_body(monkeypatch):
    app = FastAPI()

    monkeypatch.setattr(dependencies, "_scope_aware_current_user", lambda: _token_data())
    monkeypatch.setattr(dependencies, "apply_scoped_rate_limit", lambda current_user, scope: None)

    @app.get("/scoped")
    def scoped(_current_user: TokenData = Depends(dependencies.require_authenticated_with_scope("auth"))):
        return {"ok": True}

    operation = app.openapi()["paths"]["/scoped"]["get"]
    assert "requestBody" not in operation


def test_scoped_permission_dependencies_cover_forbidden_and_superuser_paths(monkeypatch):
    scoped_calls = []
    monkeypatch.setattr(dependencies, "apply_scoped_rate_limit", lambda current_user, scope: scoped_calls.append((current_user.user_id, scope)))

    perm_dependency = dependencies.require_permission_with_scope("read:users", "tempo")
    perm_checker = perm_dependency.__defaults__[0].dependency
    with pytest.raises(HTTPException, match="READ:USERS"):
        perm_checker(_token_data(permissions=[]))
    assert perm_checker(_token_data(permissions=["read:users"])).permissions == ["read:users"]

    any_scoped = dependencies.require_any_permission_with_scope(["read:users"], "tempo")
    any_checker = any_scoped.__defaults__[0].dependency
    assert any_checker(_token_data(is_superuser=True, permissions=[])).is_superuser is True
    assert any_checker(_token_data(permissions=["read:users"])).permissions == ["read:users"]
    assert any_scoped(_token_data(is_superuser=True, permissions=[])).is_superuser is True
    assert scoped_calls[-1] == ("u1", "tempo")

    with pytest.raises(HTTPException, match="READ:USERS"):
        any_checker(_token_data(permissions=[]))
