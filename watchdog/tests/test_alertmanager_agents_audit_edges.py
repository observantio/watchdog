"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import inspect
import io
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from config import config
from models.access.auth_models import Permission, Role, TokenData
from models.observability.agent_models import AgentHeartbeat
from routers.access.auth_router import audit as audit_router
from routers.observability import agents_router
from routers.observability import alertmanager_router


def _request(
    *,
    method: str = "GET",
    path: str = "/",
    headers: list[tuple[bytes, bytes]] | None = None,
    json_body: bytes | None = None,
) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "headers": headers or [],
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
        "query_string": b"",
    }
    request = Request(scope)
    if json_body is not None:
        request._body = json_body
    return request


async def _rtp(func, *args, **kwargs):
    value = func(*args, **kwargs)
    if inspect.isawaitable(value):
        return await value
    return value


def _user(**kwargs) -> TokenData:
    payload = {
        "user_id": "u1",
        "username": "user",
        "tenant_id": "tenant",
        "org_id": "org",
        "role": Role.ADMIN,
        "permissions": [permission.value for permission in Permission],
        "group_ids": ["g1"],
        "is_superuser": True,
    }
    payload.update(kwargs)
    return TokenData(**payload)


@pytest.fixture(autouse=True)
def _patch_threadpool(monkeypatch):
    monkeypatch.setattr(audit_router, "rtp", _rtp)
    monkeypatch.setattr(agents_router, "rtp", _rtp)


@pytest.mark.asyncio
async def test_alertmanager_public_rules_and_proxy_branches(monkeypatch):
    forwarded = []
    monkeypatch.setattr(alertmanager_router, "enforce_public_endpoint_security", lambda *_args, **_kwargs: None)

    async def fake_forward(**kwargs):
        forwarded.append(kwargs)
        return {"ok": True, "path": kwargs["upstream_path"]}

    monkeypatch.setattr(alertmanager_router.notifier_proxy_service, "forward", fake_forward)
    request = _request(path="/api/alertmanager/public/rules")
    result = await alertmanager_router.public_rules_proxy(request)
    assert result["path"].endswith("/public/rules")

    monkeypatch.setattr(alertmanager_router, "required_permissions", lambda *_args: None)
    with pytest.raises(HTTPException) as exc:
        await alertmanager_router.alertmanager_proxy("blocked", _request(path="/api/alertmanager/blocked"), _user())
    assert exc.value.status_code == 403

    monkeypatch.setattr(alertmanager_router, "required_permissions", lambda *_args: ["read:alerts"])
    checked = []
    monkeypatch.setattr(alertmanager_router, "check_permissions", lambda current_user, required: checked.append((current_user.user_id, required)))
    monkeypatch.setattr(alertmanager_router, "apply_scoped_rate_limit", lambda *_args: checked.append("rate"))
    monkeypatch.setattr(alertmanager_router, "is_mutating", lambda method: method.upper() != "GET")

    result = await alertmanager_router.alertmanager_proxy(
        "alerts",
        _request(method="GET", path="/api/alertmanager/alerts"),
        _user(),
    )
    assert result["path"].endswith("/alerts")
    assert checked

    monkeypatch.setattr(alertmanager_router, "validate_and_normalize_silence_payload", lambda payload, _user: {"id": payload.get("id", "sil-1")})
    monkeypatch.setattr(alertmanager_router, "extract_silence_id", lambda path, payload: (payload or {}).get("id"))

    async def fake_find_silence(*_args, **_kwargs):
        return {"id": "sil-1"}

    monkeypatch.setattr(alertmanager_router, "find_silence_for_mutation", fake_find_silence)
    ownership_checks = []
    monkeypatch.setattr(alertmanager_router, "assert_silence_owner", lambda current_user, silence: ownership_checks.append((current_user.user_id, silence["id"])))

    put_request = _request(
        method="PUT",
        path="/api/alertmanager/silences/sil-1",
        headers=[(b"content-type", b"application/json")],
        json_body=b'{"id":"sil-1"}',
    )
    result = await alertmanager_router.alertmanager_proxy("silences/sil-1", put_request, _user())
    assert result["path"].endswith("/silences/sil-1")
    assert ownership_checks == [("u1", "sil-1")]

    monkeypatch.setattr(alertmanager_router, "extract_silence_id", lambda *_args: None)
    with pytest.raises(HTTPException) as exc:
        await alertmanager_router.alertmanager_proxy("silences/sil-1", put_request, _user())
    assert exc.value.status_code == 400

    bad_json_request = _request(method="POST", path="/api/alertmanager/silences", json_body=b"not-json")
    with pytest.raises(HTTPException) as exc:
        await alertmanager_router.alertmanager_proxy("silences", bad_json_request, _user())
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_agents_router_list_active_and_heartbeat(monkeypatch):
    current_user = _user(permissions=[Permission.READ_AGENTS.value])

    class Key:
        def __init__(self, key: str, name: str, is_enabled: bool = True):
            self.key = key
            self.name = name
            self.is_enabled = is_enabled

    monkeypatch.setattr(agents_router.auth_service, "list_api_keys", lambda *_args: [Key("tenant-a", "A"), Key("tenant-b", "B", False)])
    monkeypatch.setattr(
        agents_router.agent_service,
        "list_agents",
        lambda: [
            SimpleNamespace(model_dump=lambda: {"id": "a"}, tenant_id="tenant-a", host_name="host-a"),
            SimpleNamespace(model_dump=lambda: {"id": "b"}, tenant_id="tenant-a", host_name=None),
        ],
    )

    async def fake_key_activity(key_value, _client):
        if key_value == "tenant-b":
            raise RuntimeError("boom")
        return {"metrics_active": True, "metrics_count": 4}

    monkeypatch.setattr(agents_router.agent_service, "key_activity", fake_key_activity)
    monkeypatch.setattr(agents_router.agent_service, "list_agents", lambda: [
        SimpleNamespace(model_dump=lambda: {"id": "agent-a"}, tenant_id="tenant-a", host_name="host-a"),
        SimpleNamespace(model_dump=lambda: {"id": "agent-b"}, tenant_id="tenant-a", host_name=None),
    ])

    listed = await agents_router.list_agents(current_user)
    assert listed == [{"id": "agent-a"}, {"id": "agent-b"}]

    active = await agents_router.list_active_agents(current_user)
    assert active[0]["active"] is True
    assert active[0]["host_names"] == ["host-a"]
    assert active[1]["success"] is False

    called = []
    monkeypatch.setattr(agents_router, "enforce_public_endpoint_security", lambda *_args, **_kwargs: called.append("public"))
    monkeypatch.setattr(agents_router, "enforce_header_token", lambda *_args, **_kwargs: called.append("header"))
    monkeypatch.setattr(agents_router.agent_service, "update_from_heartbeat", lambda payload: called.append(payload.name))
    monkeypatch.setattr(config, "AGENT_INGEST_IP_ALLOWLIST", None)
    monkeypatch.setattr(config, "AGENT_HEARTBEAT_TOKEN", "secret")
    result = await agents_router.heartbeat(
        _request(method="POST", path="/api/agents/heartbeat"),
        AgentHeartbeat(name="agent-a", tenant_id="tenant-a"),
    )
    assert result == {"status": "ok"}
    assert called == ["public", "header", "agent-a"]


@pytest.mark.asyncio
async def test_agents_router_close_mimir_client(monkeypatch):
    closed = []

    class Closable:
        async def aclose(self):
            closed.append(True)

    monkeypatch.setattr(agents_router, "mimir_client", Closable())
    await agents_router.close_mimir_client()
    assert closed == [True]


@pytest.mark.asyncio
async def test_audit_router_listing_and_export(monkeypatch):
    now = datetime.now(timezone.utc)
    current_user = _user()

    class FakeOrderedQuery:
        def __init__(self, rows):
            self.rows = rows

        def offset(self, _offset):
            return self

        def limit(self, _limit):
            return self

        def all(self):
            return self.rows

        def tuples(self):
            return self

    class FakeFilterQuery:
        def __init__(self, rows):
            self.rows = rows

        def order_by(self, *_args, **_kwargs):
            return FakeOrderedQuery(self.rows)

    class FakeExistsQuery:
        def __init__(self, existing):
            self.existing = existing

        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return self.existing

    class FakeDB:
        def __init__(self, rows, existing=None):
            self.rows = rows
            self.existing = existing
            self.added = []

        def query(self, *_args, **_kwargs):
            if len(_args) == 1:
                return FakeExistsQuery(self.existing)
            return FakeFilterQuery(self.rows)

        def add(self, obj):
            self.added.append(obj)

    class FakeCtx:
        def __init__(self, db):
            self.db = db

        def __enter__(self):
            return self.db

        def __exit__(self, exc_type, exc, tb):
            return False

    row = (
        SimpleNamespace(
            id="1",
            tenant_id="tenant",
            user_id="u1",
            action="read",
            resource_type="report",
            resource_id="resource-1",
            details={"secret": "hidden"},
            ip_address="127.0.0.1",
            user_agent="pytest",
            created_at=now,
        ),
        "user",
        "u@example.com",
    )

    monkeypatch.setattr(audit_router, "apply_audit_filters_func", lambda q_obj, *_args: q_obj)
    monkeypatch.setattr(audit_router, "build_audit_log_query", lambda db, *_args: FakeFilterQuery([row]))
    monkeypatch.setattr(audit_router, "sanitize_resource_id", lambda resource_id: f"sanitized:{resource_id}")
    monkeypatch.setattr(audit_router, "sanitize_audit_details", lambda details: {"sanitized": details})
    monkeypatch.setattr(audit_router, "get_request_audit_context", lambda: ("127.0.0.1", "pytest"))
    monkeypatch.setattr(audit_router, "get_db_session", lambda: FakeCtx(FakeDB([row], existing=None)))

    items = await audit_router.list_audit_logs(limit=10, offset=0, current_user=current_user)
    assert items[0]["resource_id"] == "sanitized:resource-1"
    assert items[0]["details"] == {"sanitized": {"secret": "hidden"}}

    export_db = FakeDB([row], existing=None)
    monkeypatch.setattr(audit_router, "get_db_session", lambda: FakeCtx(export_db))
    response = await audit_router.export_audit_logs_csv(current_user=current_user)
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.encode("utf-8") if isinstance(chunk, str) else chunk)
    body = b"".join(chunks)
    text = body.decode("utf-8")
    assert "sanitized:resource-1" in text
    assert "attachment; filename=audit-logs.csv" == response.headers["Content-Disposition"]
    assert export_db.added