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
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from tests._env import ensure_test_env

ensure_test_env()

from db_models import Base, Tenant, User, UserApiKey
from models.access.api_key_models import ApiKeyCreate
from services.auth import api_key_ops


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _service():
    return SimpleNamespace(
        _lazy_init=lambda: None,
        _generate_otlp_token=lambda: "raw-token",
        _hash_otlp_token=lambda token: f"hash:{token}",
        _log_audit=lambda *args, **kwargs: None,
        logger=SimpleNamespace(info=lambda *args, **kwargs: None),
    )


def _seed_user(db, user_id="u1", tenant_id="t1", org_id="org-a"):
    if not db.query(Tenant).filter_by(id=tenant_id).first():
        db.add(Tenant(id=tenant_id, name=f"tenant-{tenant_id}", display_name=tenant_id, is_active=True))
    user = User(
        id=user_id,
        tenant_id=tenant_id,
        username=user_id,
        email=f"{user_id}@example.com",
        hashed_password="x",
        org_id=org_id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def test_create_api_key_integrity_error_and_list_shares_paths(monkeypatch):
    user = SimpleNamespace(id="u1", org_id="org-a", updated_at=None)

    class _Query:
        def __init__(self, row):
            self.row = row

        def filter_by(self, **_kwargs):
            return self

        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return self.row

        def update(self, *_args, **_kwargs):
            return 0

        def count(self):
            return 0

    class _DB:
        def __init__(self):
            self._flush_count = 0

        def query(self, model):
            if model is User:
                return _Query(user)
            if model is UserApiKey:
                return _Query(None)
            return _Query(None)

        def add(self, _item):
            return None

        def flush(self):
            self._flush_count += 1
            if self._flush_count >= 1:
                raise IntegrityError("insert", {}, RuntimeError("dup"))

        def rollback(self):
            return None

        def commit(self):
            return None

        def refresh(self, _item):
            return None

    db = _DB()

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(api_key_ops, "get_db_session", fake_session)
    service = _service()

    with pytest.raises(ValueError, match="already exists"):
        api_key_ops.create_api_key(
            service,
            "u1",
            "t1",
            ApiKeyCreate(name="KeyA", key="scope-dup"),
        )

    # Real DB for share listing branches
    db2 = _session()
    _seed_user(db2, "u1")

    @contextmanager
    def fake_session_2():
        yield db2

    monkeypatch.setattr(api_key_ops, "get_db_session", fake_session_2)

    # list_api_key_shares not found + found
    with pytest.raises(ValueError, match="API key not found"):
        api_key_ops.list_api_key_shares(service, "u1", "t1", "missing")

    key = UserApiKey(id="k1", tenant_id="t1", user_id="u1", name="A", key="scope-a", is_default=False, is_enabled=True)
    db2.add(key)
    db2.commit()
    assert api_key_ops.list_api_key_shares(service, "u1", "t1", "k1") == []


def test_delete_api_key_reenables_default_and_updates_org(monkeypatch):
    db = _session()
    owner = _seed_user(db, "u1", org_id="scope-deleted")
    key_to_delete = UserApiKey(
        id="k-del",
        tenant_id="t1",
        user_id=owner.id,
        name="DeleteMe",
        key="scope-deleted",
        is_default=False,
        is_enabled=True,
    )
    default_key = UserApiKey(
        id="k-default",
        tenant_id="t1",
        user_id=owner.id,
        name="Default",
        key="scope-default",
        is_default=True,
        is_enabled=False,
    )
    db.add_all([key_to_delete, default_key])
    db.commit()

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(api_key_ops, "get_db_session", fake_session)
    service = _service()
    assert api_key_ops.delete_api_key(service, owner.id, key_to_delete.id) is True
    refreshed_default = db.query(UserApiKey).filter_by(id="k-default").first()
    refreshed_owner = db.query(User).filter_by(id=owner.id).first()
    assert refreshed_default.is_enabled is True
    assert refreshed_owner.org_id == "scope-default"


def test_backfill_otlp_tokens_rollback_on_failure(monkeypatch):
    db = _session()
    owner = _seed_user(db, "u1")
    db.add(
        UserApiKey(
            id="k1",
            tenant_id="t1",
            user_id=owner.id,
            name="Key",
            key="scope1",
            otlp_token="legacy",
            otlp_token_hash=None,
            is_default=False,
            is_enabled=True,
        )
    )
    db.commit()

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(api_key_ops, "get_db_session", fake_session)
    service = _service()
    service._hash_otlp_token = lambda _token: (_ for _ in ()).throw(RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        api_key_ops.backfill_otlp_tokens(service)
