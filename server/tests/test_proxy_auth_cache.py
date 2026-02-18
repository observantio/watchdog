import os
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import time
from types import SimpleNamespace

from services.grafana.proxy_auth_ops import authorize_proxy_request
from services.grafana_proxy_service import GrafanaProxyService
from models.access.auth_models import TokenData


class FakeAuthService:
    def __init__(self):
        self.decode_calls = 0
        self.get_user_calls = 0
        self.get_perms_calls = 0

    def decode_token(self, token):
        self.decode_calls += 1
        # return a dict that will be converted to TokenData by the code
        return {
            "user_id": "user-1",
            "username": "u1",
            "tenant_id": "t1",
            "permissions": ["read:dashboards"],
            "group_ids": [1],
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
    svc = GrafanaProxyService()
    auth = FakeAuthService()
    req = DummyRequest()
    db = DummyDB()

    # first call should invoke decode_token
    headers1 = asyncio.run(authorize_proxy_request(svc, req, db, auth, token="tok-123", orig="/grafana/"))
    assert isinstance(headers1, dict)
    assert auth.decode_calls == 1
    assert auth.get_user_calls == 1
    assert auth.get_perms_calls == 1

    # second call with same token should be served from cache (no extra decode_token call)
    headers2 = asyncio.run(authorize_proxy_request(svc, req, db, auth, token="tok-123", orig="/grafana/"))
    assert headers1 == headers2
    assert auth.decode_calls == 1
    assert auth.get_user_calls == 1
    assert auth.get_perms_calls == 1

    # wait for cache expiry and ensure decode_token is invoked again
    time.sleep(11)
    headers3 = asyncio.run(authorize_proxy_request(svc, req, db, auth, token="tok-123", orig="/grafana/"))
    assert auth.decode_calls == 2
    assert headers3 == headers1
