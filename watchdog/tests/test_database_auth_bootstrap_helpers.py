"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import NoSuchTableError

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from services.database_auth import bootstrap as boot_mod


class _Query:
    def __init__(self, row):
        self.row = row

    def filter(self, *_args, **_kwargs):
        return self

    def filter_by(self, **_kwargs):
        return self

    def with_for_update(self):
        return self

    def all(self):
        if self.row is None:
            return []
        if isinstance(self.row, list):
            return self.row
        return [self.row]

    def first(self):
        if isinstance(self.row, list):
            return self.row[0] if self.row else None
        return self.row


class _DB:
    def __init__(self, query_rows=None, dialect="postgresql"):
        self.query_rows = list(query_rows or [])
        self.executed = []
        self.added = []
        self.flushed = 0
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect)) if dialect else None

    def query(self, *_args, **_kwargs):
        row = self.query_rows.pop(0) if self.query_rows else None
        return _Query(row)

    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))

    def add(self, item):
        self.added.append(item)

    def flush(self):
        self.flushed += 1


def test_bootstrap_primitives_and_column_helpers(monkeypatch):
    assert boot_mod._norm_lower(" Admin ") == "admin"
    assert boot_mod._dialect(_DB()) == "postgresql"
    assert boot_mod._dialect(_DB(dialect="sqlite")) == "sqlite"
    assert boot_mod._dialect(_DB(dialect="")) == ""

    db = _DB(dialect="postgresql")
    boot_mod._pg_advisory_lock(db, 1)
    boot_mod._pg_advisory_unlock(db, 1)
    assert len(db.executed) == 2

    db = _DB(dialect="sqlite")
    boot_mod._pg_advisory_lock(db, 1)
    boot_mod._pg_advisory_unlock(db, 1)
    assert db.executed == []

    monkeypatch.setattr(boot_mod, "inspect", lambda bind: SimpleNamespace(get_columns=lambda table_name: [{"name": "id"}, {"name": "name"}]))
    assert boot_mod._table_columns(_DB(), "users") == {"id", "name"}

    def _raise_no_table(_table_name):
        raise NoSuchTableError("missing")

    monkeypatch.setattr(boot_mod, "inspect", lambda bind: SimpleNamespace(get_columns=_raise_no_table))
    assert boot_mod._table_columns(_DB(), "users") == set()

    monkeypatch.setattr(boot_mod, "_table_columns", lambda db, table_name: set())
    assert boot_mod._ensure_column(_DB(), "users", "new_col", "ALTER") is False
    monkeypatch.setattr(boot_mod, "_table_columns", lambda db, table_name: {"id"})
    db = _DB()
    assert boot_mod._ensure_column(db, "users", "new_col", "ALTER") is True
    assert db.executed


def test_bootstrap_indexes_and_api_key_helpers(monkeypatch):
    db = _DB()
    boot_mod._ensure_indexes(db, ["CREATE INDEX a", "CREATE INDEX b"])
    assert len(db.executed) == 2

    class FailingDB(_DB):
        def execute(self, stmt, params=None):
            raise RuntimeError("boom")

    with pytest.raises(ValueError):
        boot_mod._ensure_indexes(FailingDB(), ["CREATE INDEX bad"])

    db = _DB()
    boot_mod._disable_other_enabled_keys(db, "u1", "k1")
    assert "UPDATE user_api_keys" in db.executed[0][0]

    service = SimpleNamespace(
        _resolve_default_otlp_token=lambda: "default-raw",
        _hash_otlp_token=lambda raw: f"hash:{raw}",
        _generate_otlp_token=lambda: "generated-raw",
    )
    monkeypatch.setattr(boot_mod.config, "DEFAULT_ADMIN_USERNAME", "admin", raising=False)
    monkeypatch.setattr(boot_mod.config, "DEFAULT_OTLP_TOKEN", "configured", raising=False)
    monkeypatch.setattr(boot_mod.config, "DEFAULT_ORG_ID", "org-default", raising=False)
    fake_api_key = lambda **kwargs: SimpleNamespace(id="new-key", **kwargs)
    monkeypatch.setattr(boot_mod, "UserApiKey", fake_api_key)

    existing = SimpleNamespace(id="k1", user_id="u1", is_enabled=False, updated_at=None, name="Default", otlp_token_hash=None, otlp_token=None)
    db = _DB(query_rows=[existing])
    boot_mod.ensure_default_api_key(service, db, SimpleNamespace(id="u1", username="admin", tenant_id="tenant", org_id="org-1"))
    assert existing.is_enabled is True
    assert existing.otlp_token_hash == "hash:default-raw"

    existing = SimpleNamespace(id="k2", user_id="u2", is_enabled=True, updated_at=None, name="Other", otlp_token_hash=None, otlp_token="legacy")
    db = _DB(query_rows=[existing])
    boot_mod.ensure_default_api_key(service, db, SimpleNamespace(id="u2", username="user", tenant_id="tenant", org_id="org-2"))
    assert existing.otlp_token_hash == "hash:legacy"

    db = _DB(query_rows=[None])
    user = SimpleNamespace(id="u3", username="user", tenant_id="tenant", org_id="org-3")
    boot_mod.ensure_default_api_key(service, db, user)
    assert db.added and db.added[0].key == "org-3"
    assert db.flushed == 1

    assert boot_mod.ensure_default_api_key(service, _DB(), None) is None


def test_bootstrap_schema_helpers(monkeypatch):
    changes = iter([True, False])
    monkeypatch.setattr(boot_mod, "_ensure_column", lambda db, table, col, ddl: next(changes))
    db = _DB()
    boot_mod._ensure_user_security_columns(db)
    assert db.flushed == 1

    changes = iter([False, True])
    monkeypatch.setattr(boot_mod, "_ensure_column", lambda db, table, col, ddl: next(changes))
    db = _DB()
    boot_mod._ensure_grafana_folder_columns(db)
    assert db.flushed == 1

    db = _DB()
    boot_mod._backfill_password_changed_at(db)
    assert db.flushed == 1 and "UPDATE users" in db.executed[0][0]

    captured = []
    monkeypatch.setattr(boot_mod, "_ensure_indexes", lambda db, statements: captured.extend(statements))
    monkeypatch.setattr(boot_mod, "_table_columns", lambda db, table_name: {"id", "user_id"})
    monkeypatch.setattr(boot_mod, "_dialect", lambda db: "postgresql")
    db = _DB()
    boot_mod._ensure_api_key_constraints(db)
    assert any("otlp_token_hash" in stmt for stmt in captured)
    assert db.flushed == 1

    captured.clear()
    monkeypatch.setattr(boot_mod, "_dialect", lambda db: "sqlite")
    db = _DB(dialect="sqlite")
    boot_mod._ensure_api_key_constraints(db)
    assert any("is_default = 1" in stmt for stmt in captured)

    captured.clear()
    monkeypatch.setattr(boot_mod, "_table_columns", lambda db, table_name: set())
    db = _DB(dialect="sqlite")
    boot_mod._ensure_api_key_constraints(db)
    assert captured == []