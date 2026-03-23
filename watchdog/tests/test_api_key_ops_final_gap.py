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
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests._env import ensure_test_env

ensure_test_env()

from db_models import ApiKeyShare, Base, HiddenApiKey, Tenant, User, UserApiKey
from models.access.api_key_models import ApiKeyCreate, ApiKeyUpdate
from services.auth import api_key_ops


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _service():
    return SimpleNamespace(
        _lazy_init=lambda: None,
        _generate_otlp_token=lambda: "raw",
        _hash_otlp_token=lambda token: f"hash:{token}",
        _log_audit=lambda *args, **kwargs: None,
        logger=SimpleNamespace(info=lambda *args, **kwargs: None),
    )


def _seed_user(db, uid, tenant_id="t1", org_id="org"):
    if not db.query(Tenant).filter_by(id=tenant_id).first():
        db.add(Tenant(id=tenant_id, name=f"tenant-{tenant_id}", display_name=tenant_id, is_active=True))
    user = User(
        id=uid,
        tenant_id=tenant_id,
        username=uid,
        email=f"{uid}@example.com",
        hashed_password="x",
        org_id=org_id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def test_list_api_keys_skip_shared_none_seen_and_hidden(monkeypatch):
    db = _session()
    owner = _seed_user(db, "u-owner")
    viewer = _seed_user(db, "u-viewer", org_id="scope-shared")

    owned = UserApiKey(id="k1", tenant_id="t1", user_id=viewer.id, name="Owned", key="scope-own", is_default=False, is_enabled=False)
    shared_real = UserApiKey(id="k2", tenant_id="t1", user_id=owner.id, name="Shared", key="scope-shared", is_default=False, is_enabled=True)
    db.add_all([owned, shared_real])
    db.flush()
    # duplicate share (same as owned id) and null api_key record path
    db.add(ApiKeyShare(tenant_id="t1", api_key_id=owned.id, owner_user_id=owner.id, shared_user_id=viewer.id, can_use=True))
    db.add(ApiKeyShare(tenant_id="t1", api_key_id=shared_real.id, owner_user_id=owner.id, shared_user_id=viewer.id, can_use=True))
    db.add(HiddenApiKey(tenant_id="t1", user_id=viewer.id, api_key_id=shared_real.id))
    db.commit()

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(api_key_ops, "get_db_session", fake_session)
    out = api_key_ops.list_api_keys(_service(), viewer.id, show_hidden=False)
    # shared hidden skipped, duplicate share for own key skipped
    assert [row.id for row in out] == ["k1"]


def test_create_and_update_api_key_owner_paths(monkeypatch):
    db = _session()
    owner = _seed_user(db, "u1", org_id="scope-a")
    db.add(UserApiKey(id="k-a", tenant_id="t1", user_id=owner.id, name="A", key="scope-a", is_default=False, is_enabled=True))
    db.add(UserApiKey(id="k-b", tenant_id="t1", user_id=owner.id, name="B", key="scope-b", is_default=False, is_enabled=False))
    db.commit()

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(api_key_ops, "get_db_session", fake_session)
    service = _service()

    with pytest.raises(ValueError, match="already exists in this tenant"):
        api_key_ops.create_api_key(service, owner.id, "t1", ApiKeyCreate(name="X", key="scope-a"))

    renamed = api_key_ops.update_api_key(service, owner.id, "k-a", ApiKeyUpdate(name="Renamed"))
    assert renamed.name == "Renamed"

    enabled = api_key_ops.update_api_key(service, owner.id, "k-b", ApiKeyUpdate(is_enabled=True))
    assert enabled.is_enabled is True
    assert db.query(User).filter_by(id=owner.id).first().org_id == "scope-b"


def test_update_shared_missing_link_and_rotate_default_forbidden(monkeypatch):
    db = _session()
    owner = _seed_user(db, "u1")
    viewer = _seed_user(db, "u2")
    key = UserApiKey(id="k1", tenant_id="t1", user_id=owner.id, name="K", key="scope", is_default=False, is_enabled=True)
    default_key = UserApiKey(id="kdef", tenant_id="t1", user_id=owner.id, name="Def", key="scope-def", is_default=True, is_enabled=False)
    db.add_all([key, default_key])
    db.commit()

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(api_key_ops, "get_db_session", fake_session)
    service = _service()

    with pytest.raises(ValueError, match="API key not found"):
        api_key_ops.update_api_key(service, viewer.id, key.id, ApiKeyUpdate(is_enabled=True))

    with pytest.raises(HTTPException, match="Default key OTLP token cannot be regenerated"):
        api_key_ops.regenerate_api_key_otlp_token(service, owner.id, default_key.id)


def test_replace_api_key_shares_missing_key_and_empty_combined(monkeypatch):
    db = _session()
    owner = _seed_user(db, "u1")
    key = UserApiKey(id="k1", tenant_id="t1", user_id=owner.id, name="K", key="scope", is_default=False, is_enabled=True)
    db.add(key)
    db.commit()

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(api_key_ops, "get_db_session", fake_session)
    service = _service()

    with pytest.raises(ValueError, match="API key not found"):
        api_key_ops.replace_api_key_shares(service, owner_user_id=owner.id, tenant_id="t1", key_id="missing", user_ids=[], group_ids=[])

    # empty normalized users/groups path -> clear shares and return []
    out = api_key_ops.replace_api_key_shares(service, owner_user_id=owner.id, tenant_id="t1", key_id=key.id, user_ids=[" "], group_ids=[" "])
    assert out == []


def test_create_api_key_respects_max_api_keys_limit(monkeypatch):
    db = _session()
    owner = _seed_user(db, "u1")
    db.add(UserApiKey(id="k1", tenant_id="t1", user_id=owner.id, name="K1", key="scope-1", is_default=False, is_enabled=True))
    db.commit()

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(api_key_ops, "get_db_session", fake_session)
    monkeypatch.setattr(api_key_ops.config, "MAX_API_KEYS_PER_USER", 1, raising=False)

    with pytest.raises(ValueError, match="Maximum API key limit reached"):
        api_key_ops.create_api_key(_service(), owner.id, "t1", ApiKeyCreate(name="K2", key="scope-2"))
