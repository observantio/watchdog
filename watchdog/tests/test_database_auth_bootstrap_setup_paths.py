"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import SQLAlchemyError

from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Role
from services.database_auth import bootstrap as mod


class _Query:
    def __init__(self, row):
        self._row = row

    def filter_by(self, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def with_for_update(self):
        return self

    def all(self):
        if self._row is None:
            return []
        if isinstance(self._row, list):
            return self._row
        return [self._row]

    def first(self):
        if isinstance(self._row, list):
            return self._row[0] if self._row else None
        return self._row


class _DB:
    def __init__(self, query_rows):
        self.query_rows = list(query_rows)
        self.commits = 0
        self.flushes = 0
        self.added = []

    def query(self, *_args, **_kwargs):
        row = self.query_rows.pop(0) if self.query_rows else None
        return _Query(row)

    def add(self, item):
        self.added.append(item)

    def flush(self):
        self.flushes += 1

    def commit(self):
        self.commits += 1


def test_ensure_default_setup_bootstrap_disabled_warns_when_tenant_missing(monkeypatch):
    db = _DB([None])
    warnings = []
    events = []
    service = SimpleNamespace(
        logger=SimpleNamespace(warning=lambda *args, **kwargs: warnings.append(args), error=lambda *args, **kwargs: None)
    )

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(mod, "get_db_session", fake_session)
    monkeypatch.setattr(mod, "_pg_advisory_lock", lambda *_args, **_kwargs: events.append("lock"))
    monkeypatch.setattr(mod, "_pg_advisory_unlock", lambda *_args, **_kwargs: events.append("unlock"))
    monkeypatch.setattr(mod, "_ensure_user_security_columns", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "_ensure_grafana_folder_columns", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "_ensure_api_key_constraints", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "_backfill_password_changed_at", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "ensure_permissions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod.config, "DEFAULT_ADMIN_BOOTSTRAP_ENABLED", False, raising=False)
    monkeypatch.setattr(mod.config, "DEFAULT_ADMIN_TENANT", "default", raising=False)

    mod.ensure_default_setup(service)
    assert events == ["lock", "unlock"]
    assert warnings


def test_ensure_default_setup_validates_required_config(monkeypatch):
    db = _DB([None])
    service = SimpleNamespace(
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None)
    )

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(mod, "get_db_session", fake_session)
    monkeypatch.setattr(mod, "_pg_advisory_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "_pg_advisory_unlock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "_ensure_user_security_columns", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "_ensure_grafana_folder_columns", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "_ensure_api_key_constraints", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "_backfill_password_changed_at", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "ensure_permissions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod.config, "DEFAULT_ADMIN_BOOTSTRAP_ENABLED", True, raising=False)

    monkeypatch.setattr(mod.config, "DEFAULT_ADMIN_TENANT", "", raising=False)
    with pytest.raises(ValueError, match="DEFAULT_ADMIN_TENANT"):
        mod.ensure_default_setup(service)

    monkeypatch.setattr(mod.config, "DEFAULT_ADMIN_TENANT", "default", raising=False)
    monkeypatch.setattr(mod.config, "DEFAULT_ADMIN_USERNAME", "", raising=False)
    with pytest.raises(ValueError, match="DEFAULT_ADMIN_USERNAME"):
        mod.ensure_default_setup(service)


def test_ensure_default_setup_existing_admin_runs_idempotent_paths(monkeypatch):
    tenant = SimpleNamespace(id="t1", name="default")
    admin_user = SimpleNamespace(
        id="u1",
        tenant_id="t1",
        username="admin",
        role=Role.ADMIN,
        permissions=[],
    )
    db = _DB([tenant, admin_user])
    calls = []
    service = SimpleNamespace(
        hash_password=lambda text: f"hashed:{text}",
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None, info=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None),
    )

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(mod, "get_db_session", fake_session)
    monkeypatch.setattr(mod, "_pg_advisory_lock", lambda *_args, **_kwargs: calls.append("lock"))
    monkeypatch.setattr(mod, "_pg_advisory_unlock", lambda *_args, **_kwargs: calls.append("unlock"))
    monkeypatch.setattr(mod, "_ensure_user_security_columns", lambda *_args, **_kwargs: calls.append("cols"))
    monkeypatch.setattr(mod, "_ensure_grafana_folder_columns", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "_ensure_api_key_constraints", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "_backfill_password_changed_at", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "ensure_permissions", lambda *_args, **_kwargs: calls.append("permissions"))
    monkeypatch.setattr(mod, "ensure_default_api_key", lambda *_args, **_kwargs: calls.append("default-key"))
    monkeypatch.setattr(mod.config, "DEFAULT_ADMIN_BOOTSTRAP_ENABLED", True, raising=False)
    monkeypatch.setattr(mod.config, "DEFAULT_ADMIN_TENANT", "default", raising=False)
    monkeypatch.setattr(mod.config, "DEFAULT_ADMIN_USERNAME", "admin", raising=False)

    mod.ensure_default_setup(service)
    assert "default-key" in calls
    assert db.commits == 1
    assert calls[-1] == "unlock"


def test_ensure_default_setup_logs_and_reraises_sqlalchemy_errors(monkeypatch):
    errors = []
    service = SimpleNamespace(
        logger=SimpleNamespace(error=lambda *args, **kwargs: errors.append(args), warning=lambda *args, **kwargs: None)
    )

    @contextmanager
    def fake_session():
        raise SQLAlchemyError("db down")
        yield  # pragma: no cover

    monkeypatch.setattr(mod, "get_db_session", fake_session)
    with pytest.raises(SQLAlchemyError):
        mod.ensure_default_setup(service)
    assert errors
