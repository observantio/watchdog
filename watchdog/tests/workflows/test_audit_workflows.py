"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from routers.access.auth_router import audit as audit_routes

from .helpers import WorkflowState, patch_auth_service


class FakeAuditQuery:
    def __init__(self, rows: list[tuple[object, str, str]]):
        self.rows = rows

    def filter_by_fields(
        self,
        *,
        start: datetime | None,
        end: datetime | None,
        user_id: str | None,
        action: str | None,
        resource_type: str | None,
        q: str | None,
    ) -> "FakeAuditQuery":
        filtered = []
        for log, username, email in self.rows:
            if start and log.created_at < start:
                continue
            if end and log.created_at > end:
                continue
            if user_id and log.user_id != user_id:
                continue
            if action and log.action != action:
                continue
            if resource_type and log.resource_type != resource_type:
                continue
            if q and q not in json.dumps(log.details):
                continue
            filtered.append((log, username, email))
        return FakeAuditQuery(filtered)

    def order_by(self, *_args, **_kwargs):
        self.rows = sorted(self.rows, key=lambda row: row[0].created_at, reverse=True)
        return self

    def offset(self, value: int):
        self.rows = self.rows[value:]
        return self

    def limit(self, value: int):
        self.rows = self.rows[:value]
        return self

    def tuples(self):
        return self

    def all(self):
        return self.rows


def test_audit_list_and_export_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)

    now = datetime.now(timezone.utc)
    audit_rows = [
        (
            SimpleNamespace(
                id="audit-1",
                tenant_id=state.tenant_id,
                user_id="u-admin",
                action="auth.login",
                resource_type="users",
                resource_id="/api/auth/login?password=secret",
                details={"query": "password=secret&status=ok", "token": "jwt-1", "note": "alice"},
                ip_address="127.0.0.1",
                user_agent="pytest",
                created_at=now,
            ),
            "admin",
            "admin@example.com",
        ),
        (
            SimpleNamespace(
                id="audit-2",
                tenant_id=state.tenant_id,
                user_id="u-admin",
                action="grafana.dashboard.update",
                resource_type="dashboards",
                resource_id="dash-1",
                details={"query": "title=latency", "note": "latency"},
                ip_address="127.0.0.1",
                user_agent="pytest",
                created_at=now - timedelta(minutes=5),
            ),
            "admin",
            "admin@example.com",
        ),
    ]

    class FakeExistenceQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return None

    class FakeDB:
        def __init__(self):
            self.added = []

        def add(self, item):
            self.added.append(item)

        def query(self, *_args, **_kwargs):
            return FakeExistenceQuery()

    class FakeCtx:
        def __enter__(self):
            return FakeDB()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_build_audit_log_query(db, current_user, tenant_id, actor):
        del db, current_user, tenant_id, actor
        return FakeAuditQuery(audit_rows)

    def fake_apply_audit_filters(query, start, end, user_id, action, resource_type, q=None):
        return query.filter_by_fields(start=start, end=end, user_id=user_id, action=action, resource_type=resource_type, q=q)

    monkeypatch.setattr(audit_routes, "get_db_session", lambda: FakeCtx())
    monkeypatch.setattr(audit_routes, "build_audit_log_query", fake_build_audit_log_query)
    monkeypatch.setattr(audit_routes, "apply_audit_filters_func", fake_apply_audit_filters)
    monkeypatch.setattr(audit_routes, "get_request_audit_context", lambda: ("127.0.0.1", "pytest"))

    headers = state.auth_header("token-u-admin")
    list_response = client.get(
        "/api/auth/audit-logs",
        headers=headers,
        params={"action": "auth.login", "resource_type": "users", "q": "alice", "limit": 10, "offset": 0},
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["resource_id"] == "/api/auth/login?password=%5BREDACTED%5D"
    assert list_response.json()[0]["details"]["token"] == "[REDACTED]"

    export_response = client.get(
        "/api/auth/audit-logs/export",
        headers=headers,
        params={"start": (now - timedelta(days=1)).isoformat(), "end": now.isoformat(), "resource_type": "dashboards"},
    )
    assert export_response.status_code == 200
    csv_body = export_response.text
    assert "grafana.dashboard.update" in csv_body
    assert "[REDACTED]" not in csv_body