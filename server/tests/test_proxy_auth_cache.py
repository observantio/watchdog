import os
# ensure test environment variables are set before importing modules that
# instantiate Config() at import time (prevents CORS wildcard validation errors)
from tests._env import ensure_test_env
ensure_test_env()

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services.grafana_proxy_service import GrafanaProxyService
from models.access.auth_models import TokenData


class FakeAuthService:
    def __init__(self):
        self.decode_calls = 0
        self.get_user_calls = 0
        self.get_perms_calls = 0

    def decode_token(self, token):
        self.decode_calls += 1
        # return a dict compatible with TokenData so the code can construct it
        return {
            "user_id": "user-1",
            "username": "u1",
            "tenant_id": "t1",
            "org_id": "org1",
            "role": "user",
            "permissions": ["read:dashboards"],
            "group_ids": ["1"],
            "is_superuser": False,
        }

    def get_user_by_id(self, user_id):
        self.get_user_calls += 1
        return SimpleNamespace(is_active=True, group_ids=[1], org_id="org1")

    def get_user_permissions(self, user):
        self.get_perms_calls += 1
        return ["read:dashboards"]


class DummyDB:
    pass


class DummyRequest:
    def __init__(self):
        self.headers = {}
        self.cookies = {}
        self.method = "GET"


import asyncio

def test_authorize_proxy_request_is_cached():
    # ensure module-level cache is empty for deterministic test runs
    import importlib, sys
    proxy_mod_name = "services.grafana.proxy_auth_ops"
    if proxy_mod_name in sys.modules:
        # reload to ensure we use the real implementation (some tests monkeypatch this module)
        importlib.reload(sys.modules[proxy_mod_name])
    proxy_mod = importlib.import_module(proxy_mod_name)
    proxy_mod._PROXY_AUTH_CACHE.clear()

    svc = GrafanaProxyService()
    auth = FakeAuthService()
    req = DummyRequest()
    db = DummyDB()

    # import the live function after ensuring the module is the real one
    authorize_proxy_request = proxy_mod.authorize_proxy_request

    # first call should invoke decode_token
    headers1 = asyncio.run(authorize_proxy_request(svc, req, db, auth, token="tok-123", orig="/grafana/"))
    assert isinstance(headers1, dict)
    assert auth.decode_calls == 1
    assert auth.get_user_calls == 1
    assert auth.get_perms_calls == 1

    # second call with same token/path/method should be served from cache for authz checks
    headers2 = asyncio.run(authorize_proxy_request(svc, req, db, auth, token="tok-123", orig="/grafana/"))
    assert headers1 == headers2
    assert auth.decode_calls == 2
    assert auth.get_user_calls == 1
    assert auth.get_perms_calls == 1

    # wait for cache expiry and ensure decode_token is invoked again
    time.sleep(11)
    headers3 = asyncio.run(authorize_proxy_request(svc, req, db, auth, token="tok-123", orig="/grafana/"))
    assert auth.decode_calls == 3
    assert auth.get_user_calls == 2
    assert auth.get_perms_calls == 2
    assert headers3 == headers1


def test_cache_is_scoped_by_method_and_path():
    import importlib
    import sys

    proxy_mod_name = "services.grafana.proxy_auth_ops"
    if proxy_mod_name in sys.modules:
        importlib.reload(sys.modules[proxy_mod_name])
    proxy_mod = importlib.import_module(proxy_mod_name)
    proxy_mod._PROXY_AUTH_CACHE.clear()

    svc = GrafanaProxyService()
    auth = FakeAuthService()
    req = DummyRequest()
    db = DummyDB()
    authorize_proxy_request = proxy_mod.authorize_proxy_request

    headers = asyncio.run(authorize_proxy_request(svc, req, db, auth, token="tok-123", orig="/grafana/"))
    assert isinstance(headers, dict)

    req.method = "POST"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            authorize_proxy_request(
                svc,
                req,
                db,
                auth,
                token="tok-123",
                orig="/grafana/api/dashboards/db",
            )
        )
    assert exc.value.status_code == 403
