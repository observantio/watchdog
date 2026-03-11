from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests._env import ensure_test_env

ensure_test_env()

from db_models import AuditLog, Base, GrafanaFolder, Tenant, User
from models.access.auth_models import Role, TokenData
from services.auth import helper as auth_helper
from services.common import cookies as cookie_helpers
from services.database_auth import audit as db_audit
from services.grafana import folder_ops
from services.grafana.grafana_service import GrafanaAPIError
from services.loki.http_client import LokiHttpClient


def _request(*, scheme="http", headers=None, client=("127.0.0.1", 1)):
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/",
        "scheme": scheme,
        "headers": headers or [],
        "client": client,
        "query_string": b"",
    })


def _db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class _QueryRecorder:
    def __init__(self):
        self.filters = []

    def outerjoin(self, *args, **kwargs):
        return self

    def filter(self, criterion):
        self.filters.append(criterion)
        return self


class _AuditDB:
    def __init__(self):
        self.query_obj = _QueryRecorder()
        self.added = []

    def query(self, *args, **kwargs):
        return self.query_obj

    def add(self, obj):
        self.added.append(obj)


class _FolderGrafanaStub:
    def __init__(self):
        self.create_error = None
        self.update_error = None
        self.delete_error = None
        self.folder = SimpleNamespace(id=11, uid="f1", title="Folder 1")

    async def get_folder(self, uid):
        return self.folder

    async def create_folder(self, title):
        if self.create_error is not None:
            raise self.create_error
        return self.folder

    async def update_folder(self, uid, title):
        if self.update_error is not None:
            raise self.update_error
        return self.folder

    async def delete_folder(self, uid):
        if self.delete_error is not None:
            raise self.delete_error
        return True


class _FolderProxyStub:
    def __init__(self, grafana_service):
        self.grafana_service = grafana_service
        self.errors = []

    def _validate_group_visibility(self, db, *, shared_group_ids, **kwargs):
        return []

    def _raise_http_from_grafana_error(self, exc):
        self.errors.append(exc)


class _ResponseStub:
    def __init__(self, status_code):
        self.status_code = status_code

    def raise_for_status(self):
        request = httpx.Request("GET", "https://loki.test")
        response = httpx.Response(self.status_code, request=request)
        raise httpx.HTTPStatusError("boom", request=request, response=response)

    def json(self):
        return {}


class _ClientStub:
    def __init__(self, response):
        self.response = response

    async def get(self, url, params=None, headers=None):
        return self.response


def test_auth_helper_database_audit_cookie_and_loki_small_gaps(monkeypatch):
    assert auth_helper.sanitize_resource_id("https://host/path?") == "https://host/path?"
    assert _request().url.path == "/"

    audit_db = _AuditDB()
    current_user = TokenData(user_id="u1", username="user", tenant_id="tenant-a", org_id="org-1", role=Role.USER, permissions=[])
    auth_helper.build_audit_log_query(audit_db, current_user, None, User)
    assert audit_db.query_obj.filters

    monkeypatch.setattr(db_audit, "get_request_audit_context", lambda: ("10.0.0.1", "agent/1.0"))
    db_audit.log_audit(audit_db, "tenant-a", "u1", "login", "auth", "user:u1", {"ok": True})
    entry = audit_db.added[-1]
    assert isinstance(entry, AuditLog)
    assert entry.ip_address == "10.0.0.1"
    assert entry.user_agent == "agent/1.0"

    secure_request = SimpleNamespace(url=SimpleNamespace(scheme="https"), headers={}, client=None)
    assert cookie_helpers.is_secure_cookie_request(secure_request, trust_proxy_headers=False) is True
    assert _ResponseStub(200).json() == {}

    client = LokiHttpClient()
    warnings = []
    monkeypatch.setattr("services.loki.http_client.logger.warning", lambda *args, **kwargs: warnings.append(args))
    result = asyncio.run(
        client.safe_get_json(
            _ClientStub(_ResponseStub(500)),
            "https://loki.test",
            params={"q": "x"},
            headers={},
            quiet=False,
        )
    )
    assert result is None
    assert warnings


def test_folder_ops_remaining_success_and_nonraising_error_paths():
    db = _db_session()
    db.add_all([
        Tenant(id="t1", name="tenant-1", display_name="Tenant 1", is_active=True),
        User(id="u1", tenant_id="t1", username="owner", email="owner@example.com", hashed_password="x", org_id="org-1", is_active=True),
        GrafanaFolder(
            id="db-folder",
            tenant_id="t1",
            created_by="u1",
            grafana_uid="f1",
            grafana_id=11,
            title="Folder 1",
            visibility="private",
            hidden_by=[],
        ),
    ])
    db.commit()

    grafana = _FolderGrafanaStub()
    service = _FolderProxyStub(grafana)

    folder = asyncio.run(folder_ops.get_folder(service, db, "f1", "u1", "t1", []))
    assert folder is not None
    assert folder.uid == "f1"
    assert service._validate_group_visibility(db, shared_group_ids=[]) == []

    grafana.create_error = GrafanaAPIError(400, {"message": "bad"})
    assert asyncio.run(folder_ops.create_folder(service, db, "New", "u1", "t1", [])) is None

    grafana.create_error = None
    grafana.update_error = GrafanaAPIError(500, {"message": "bad"})
    assert asyncio.run(folder_ops.update_folder(service, db, "f1", "u1", "t1", [])) is None

    grafana.update_error = None
    grafana.delete_error = httpx.ConnectError("down")
    assert asyncio.run(folder_ops.delete_folder(service, db, "f1", "u1", "t1", [])) is False

    grafana.delete_error = None
    grafana.folder = SimpleNamespace(id=12, uid="f-created", title="Created")
    created = asyncio.run(folder_ops.create_folder(service, db, "Created", "u1", "t1", []))
    assert created is not None
    grafana.folder = SimpleNamespace(id=11, uid="f1", title="Folder 1")
    updated = asyncio.run(folder_ops.update_folder(service, db, "f1", "u1", "t1", []))
    assert updated is not None
    assert asyncio.run(folder_ops.delete_folder(service, db, "f1", "u1", "t1", [])) is True
    assert len(service.errors) == 3