"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Permission as PermissionEnum, Role, TokenData
import database as database_module
from services.database_auth import schema_converters as schema_mod
from services.database_auth import shared as shared_mod
from services.database_auth import token as token_mod


def test_database_lifecycle_and_session_paths(monkeypatch):
    database_module.dispose_database()
    warning_calls = []
    monkeypatch.setattr(database_module.logger, "warning", lambda *args, **kwargs: warning_calls.append(args))
    with monkeypatch.context() as ctx:
        ctx.setattr(database_module.os, "getenv", lambda name: "bad" if name == "DB_POOL_SIZE" else None)
        assert database_module._env_int("DB_POOL_SIZE", 10) == 10
    assert warning_calls

    created = []

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, stmt):
            created.append(("execute", str(stmt)))

    class FakeEngine:
        def __init__(self):
            self.disposed = False

        def connect(self):
            return FakeConn()

        def dispose(self):
            self.disposed = True

    fake_engine = FakeEngine()
    create_engine_calls = []
    session_events: list[str] = []
    fake_session = SimpleNamespace(
        commit=lambda: session_events.append("commit"),
        rollback=lambda: session_events.append("rollback"),
        close=lambda: session_events.append("close"),
    )
    monkeypatch.setattr(
        database_module,
        "create_engine",
        lambda *args, **kwargs: create_engine_calls.append((args, kwargs)) or fake_engine,
    )
    monkeypatch.setattr(database_module, "sessionmaker", lambda **kwargs: (lambda: fake_session))
    monkeypatch.setattr(database_module.Base.metadata, "create_all", lambda bind: created.append(("create_all", bind)))

    database_module.init_database("sqlite:///tmp.db", echo=True, pool_size=5)
    database_module.init_database("sqlite:///tmp.db")
    assert create_engine_calls[0][1] == {"pool_pre_ping": True, "echo": True, "future": True}
    if database_module._engine is None:
        database_module._engine = fake_engine
    if database_module._session_local is None:
        database_module._session_local = lambda: fake_session

    with database_module.get_db_session() as session:
        assert session is fake_session
    assert session_events[-2:] == ["commit", "close"]

    with pytest.raises(RuntimeError, match="boom"):
        with database_module.get_db_session():
            raise RuntimeError("boom")
    assert session_events[-2:] == ["rollback", "close"]

    failed_commit_events = []
    failing_commit_session = SimpleNamespace(
        commit=lambda: (_ for _ in ()).throw(RuntimeError("commit failed")),
        rollback=lambda: failed_commit_events.append("rollback"),
        close=lambda: failed_commit_events.append("close"),
    )
    database_module._session_local = lambda: failing_commit_session
    with pytest.raises(RuntimeError, match="commit failed"):
        with database_module.get_db_session() as session:
            assert session is failing_commit_session
    assert failed_commit_events == ["rollback", "close"]

    database_module._session_local = lambda: fake_session

    yielded = next(database_module.get_db())
    assert yielded is fake_session
    database_module.init_db()
    assert ("create_all", fake_engine) in created
    assert database_module.connection_test() is True

    class BrokenEngine:
        def connect(self):
            raise database_module.SQLAlchemyError("down")

        def dispose(self):
            created.append(("disposed", None))

    database_module._engine = BrokenEngine()
    assert database_module.connection_test() is False
    database_module.dispose_database()
    assert database_module._engine is None
    assert database_module._session_local is None
    with pytest.raises(RuntimeError):
        database_module._require_session_factory()


def test_database_remaining_helper_branches(monkeypatch):
    database_module.dispose_database()
    monkeypatch.setattr(database_module.os, "getenv", lambda name: None)
    assert database_module._env_int("MISSING", 9) == 9
    assert database_module.connection_test() is False
    with pytest.raises(RuntimeError, match="Database not initialized"):
        database_module.init_db()

    create_engine_calls = []
    fake_engine = SimpleNamespace(dispose=lambda: None)
    monkeypatch.setattr(
        database_module,
        "create_engine",
        lambda *args, **kwargs: create_engine_calls.append((args, kwargs)) or fake_engine,
    )
    monkeypatch.setattr(database_module, "sessionmaker", lambda **kwargs: (lambda: SimpleNamespace()))
    database_module.init_database("postgresql://db/app", echo=False, pool_size=7)
    engine_kwargs = create_engine_calls[0][1]
    assert engine_kwargs["pool_size"] == 7
    assert engine_kwargs["max_overflow"] == 20
    assert engine_kwargs["pool_timeout"] == 30
    assert engine_kwargs["pool_recycle"] == 1800
    database_module.dispose_database()

    create_engine_calls.clear()
    monkeypatch.setattr(database_module.os, "getenv", lambda name: "13" if name == "DB_POOL_SIZE" else None)
    database_module.init_database("postgresql://db/app", echo=False, pool_size=None)
    assert create_engine_calls[0][1]["pool_size"] == 13
    database_module.dispose_database()

    session_events = []
    managed_session = SimpleNamespace(
        commit=lambda: session_events.append("commit"),
        rollback=lambda: session_events.append("rollback"),
        close=lambda: session_events.append("close"),
    )
    database_module._session_local = lambda: managed_session
    with database_module._session_scope() as session:
        assert session is managed_session
    assert session_events == ["commit", "close"]

    session_events.clear()
    with pytest.raises(RuntimeError, match="boom"):
        with database_module._session_scope():
            raise RuntimeError("boom")
    assert session_events == ["rollback", "close"]

    context = database_module._SessionContext()
    assert context.__exit__(None, None, None) is None
    database_module._session_local = None


def test_init_database_returns_when_initialized_inside_lock(monkeypatch):
    database_module.dispose_database()

    class EngineStub:
        def dispose(self):
            return None

    class LockStub:
        def __enter__(self):
            database_module._engine = EngineStub()
            database_module._session_local = lambda: SimpleNamespace()
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    create_engine_calls = []
    monkeypatch.setattr(database_module, "_init_lock", LockStub())
    monkeypatch.setattr(database_module, "create_engine", lambda *args, **kwargs: create_engine_calls.append((args, kwargs)))

    database_module.init_database("sqlite:///tmp.db")
    assert create_engine_calls == []
    database_module.dispose_database()


def test_schema_converters_and_shared_helper_paths():
    now = datetime.now(timezone.utc)
    service = SimpleNamespace(
        _to_api_key_schema=lambda key: {
            "id": "k1",
            "name": key.name,
            "key": "abc",
            "otlp_token": None,
            "owner_user_id": "u1",
            "owner_username": "alice",
            "is_default": True,
            "is_enabled": True,
            "created_at": now,
            "updated_at": now,
        },
        get_user_permissions=lambda user: [PermissionEnum.READ_USERS.value, PermissionEnum.READ_GROUPS.value],
        get_user_direct_permissions=lambda user: [PermissionEnum.READ_USERS.value],
    )
    user = SimpleNamespace(
        id="u1",
        tenant_id="tenant-a",
        username="alice",
        email="alice@example.com",
        full_name="Alice",
        org_id="org-a",
        role=Role.ADMIN,
        groups=[SimpleNamespace(id="g1")],
        is_active=True,
        created_at=now,
        updated_at=now,
        last_login=now,
        api_keys=[SimpleNamespace(name="default")],
        needs_password_change=True,
        password_changed_at=now,
        session_invalid_before=now,
        mfa_enabled=True,
        must_setup_mfa=False,
        auth_provider="local",
        grafana_user_id=42,
    )
    user_schema = schema_mod.to_user_schema(service, user)
    assert user_schema.grafana_user_id == 42
    assert user_schema.api_keys[0].name == "default"

    response = schema_mod.build_user_response(service, user_schema, fallback_permissions=[PermissionEnum.READ_ALERTS.value])
    assert response.permissions == [PermissionEnum.READ_USERS, PermissionEnum.READ_GROUPS]
    assert response.direct_permissions == [PermissionEnum.READ_USERS.value]

    api_key = schema_mod.to_api_key_schema(
        SimpleNamespace(
            id="k1",
            name="default",
            key="abc",
            otlp_token="tok",
            user_id="u1",
            user=SimpleNamespace(username="alice"),
            is_default=True,
            is_enabled=True,
            created_at=now,
            updated_at=now,
        )
    )
    assert api_key.owner_username == "alice"

    group_schema = schema_mod.to_group_schema(
        SimpleNamespace(
            id="g1",
            tenant_id="tenant-a",
            name="ops",
            description="Ops",
            created_at=now,
            updated_at=now,
            permissions=[SimpleNamespace(id="p1", name="read:users", display_name="Read", description="desc", resource_type="users", action="read")],
        )
    )
    assert group_schema.permissions[0].name == "read:users"
    assert schema_mod._coerce_permission(PermissionEnum.READ_USERS) is PermissionEnum.READ_USERS
    assert schema_mod._coerce_permission(PermissionEnum.READ_GROUPS.value) is PermissionEnum.READ_GROUPS

    sync_service = SimpleNamespace(_sync_user_from_oidc_claims=lambda claims: SimpleNamespace(is_active=True, username="oidc"))
    assert shared_mod.sync_active_user_from_claims(sync_service, None) is None
    assert shared_mod.sync_active_user_from_claims(sync_service, {"sub": "1"}).username == "oidc"
    sync_service = SimpleNamespace(_sync_user_from_oidc_claims=lambda claims: SimpleNamespace(is_active=False))
    assert shared_mod.sync_active_user_from_claims(sync_service, {"sub": "1"}) is None


def test_token_helpers_and_decode_paths(monkeypatch):
    user = SimpleNamespace(
        id="u1",
        username="alice",
        tenant_id="tenant-a",
        org_id="org-a",
        role="bad-role",
        is_superuser=True,
        groups=[SimpleNamespace(id="g1")],
    )
    service = SimpleNamespace(
        get_user_permissions=lambda db_user: [PermissionEnum.READ_GROUPS.value],
        is_external_auth_enabled=lambda: True,
        oidc_service=SimpleNamespace(verify_access_token=lambda token: {"iat": 123, "scp": [PermissionEnum.READ_USERS.value, "unknown"]}),
        _extract_permissions_from_oidc_claims=lambda claims: [PermissionEnum.READ_USERS.value, "unknown"],
        list_all_permissions=lambda: [{"name": PermissionEnum.READ_USERS.value}, {"name": PermissionEnum.READ_GROUPS.value}],
    )
    token_data = token_mod.build_token_data_for_user(service, user)
    assert token_data.role is Role.USER
    assert token_data.group_ids == ["g1"]

    local = TokenData(
        user_id="local",
        username="local",
        tenant_id="tenant-a",
        org_id="org-a",
        role=Role.ADMIN,
        permissions=[PermissionEnum.READ_ALERTS.value],
    )
    monkeypatch.setattr(token_mod, "decode_token_op", lambda service, token: local)
    assert token_mod.decode_token(service, "tok") is local

    monkeypatch.setattr(token_mod, "decode_token_op", lambda service, token: None)
    external_service = SimpleNamespace(**service.__dict__)
    external_service.is_external_auth_enabled = lambda: False
    assert token_mod.decode_token(external_service, "tok") is None

    monkeypatch.setattr(token_mod, "sync_active_user_from_claims", lambda service, claims: user)
    decoded = token_mod.decode_token(service, "tok")
    assert decoded is not None
    assert decoded.iat == 123
    assert decoded.permissions == sorted([PermissionEnum.READ_GROUPS.value, PermissionEnum.READ_USERS.value])

    monkeypatch.setattr(token_mod, "sync_active_user_from_claims", lambda service, claims: None)
    assert token_mod.decode_token(service, "tok") is None
    assert token_mod._safe_role(Role.ADMIN.value) is Role.ADMIN
    assert token_mod._safe_role("invalid") is Role.USER
    assert token_mod._known_permission_names(service) == {PermissionEnum.READ_USERS.value, PermissionEnum.READ_GROUPS.value}