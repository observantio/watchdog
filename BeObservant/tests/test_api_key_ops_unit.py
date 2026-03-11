"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests._env import ensure_test_env

ensure_test_env()

from db_models import ApiKeyShare, Base, Group, HiddenApiKey, Tenant, User, UserApiKey
from models.access.api_key_models import ApiKeyCreate, ApiKeyUpdate
from services.auth import api_key_ops


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _service() -> SimpleNamespace:
    token_counter = {"value": 0}

    def _generate_otlp_token():
        token_counter["value"] += 1
        return f"otlp-token-{token_counter['value']}"

    return SimpleNamespace(
        _lazy_init=lambda: None,
        _generate_otlp_token=_generate_otlp_token,
        _hash_otlp_token=lambda token: f"hash:{token}",
        _log_audit=lambda *args, **kwargs: None,
        logger=SimpleNamespace(info=lambda *args, **kwargs: None),
    )


def _seed_user(db, *, tenant_id="t1", user_id="u1", username="user1", email="u1@example.com", org_id="org-default"):
    tenant = db.query(Tenant).filter_by(id=tenant_id).first()
    if tenant is None:
        db.add(Tenant(id=tenant_id, name=f"tenant-{tenant_id}", display_name=tenant_id, is_active=True))
    user = User(
        id=user_id,
        tenant_id=tenant_id,
        username=username,
        email=email,
        hashed_password="x",
        org_id=org_id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def test_api_key_helper_functions_cover_edge_cases():
    assert api_key_ops._normalize_scope_key(None) is None
    assert api_key_ops._normalize_scope_key(" abc:def ") == "abc:def"
    with pytest.raises(ValueError, match="cannot be blank"):
        api_key_ops._normalize_scope_key("   ")
    with pytest.raises(ValueError, match="must be 3-200 chars"):
        api_key_ops._normalize_scope_key("a$")

    now = datetime.now(timezone.utc)
    assert api_key_ops._share_created_at(SimpleNamespace(created_at=now)) == now
    assert isinstance(api_key_ops._share_created_at(SimpleNamespace(created_at=None)), datetime)
    assert api_key_ops._normalize_api_key_name(" name ") == "name"
    with pytest.raises(ValueError, match="name is required"):
        api_key_ops._normalize_api_key_name(" ")


def test_api_key_db_helpers_and_schema_mapping():
    db = _session()
    owner = _seed_user(db)
    other = _seed_user(db, user_id="u2", username="user2", email="u2@example.com")
    key = UserApiKey(
        id="k1",
        tenant_id="t1",
        user_id=owner.id,
        name="Key One",
        key="scope-1",
        otlp_token="secret",
        is_default=False,
        is_enabled=True,
    )
    db.add(key)
    db.flush()
    share = ApiKeyShare(tenant_id="t1", api_key_id=key.id, owner_user_id=owner.id, shared_user_id=other.id, can_use=True)
    db.add(share)
    db.commit()
    key.user = owner
    share.shared_user = other
    key.shares = [share]

    assert api_key_ops._require_user(db, owner.id).id == owner.id
    with pytest.raises(ValueError, match="User not found"):
        api_key_ops._require_user(db, "missing")
    assert api_key_ops._require_user_in_tenant(db, owner.id, "t1").id == owner.id
    with pytest.raises(ValueError, match="User not found"):
        api_key_ops._require_user_in_tenant(db, owner.id, "other")
    assert api_key_ops._require_api_key_in_tenant(db, key.id, "t1").id == key.id
    with pytest.raises(ValueError, match="API key not found"):
        api_key_ops._require_api_key_in_tenant(db, key.id, "other")

    api_key_ops._assert_unique_api_key_name(db, tenant_id="t1", owner_user_id=owner.id, name="OtherName")
    with pytest.raises(ValueError, match="name already exists"):
        api_key_ops._assert_unique_api_key_name(db, tenant_id="t1", owner_user_id=owner.id, name="key one")

    shares = api_key_ops._list_api_key_shares_in_session(db, tenant_id="t1", key_id=key.id)
    assert shares[0].user_id == other.id
    assert shares[0].username == other.username

    owner_schema = api_key_ops._api_key_to_schema(key, is_shared=False, can_use=True, viewer_enabled=True, is_hidden=True)
    assert owner_schema.otlp_token == "secret"
    assert owner_schema.is_hidden is True
    assert owner_schema.shared_with[0].user_id == other.id

    shared_schema = api_key_ops._api_key_to_schema(key, is_shared=True, can_use=True, viewer_enabled=False)
    assert shared_schema.otlp_token is None
    assert shared_schema.is_shared is True
    assert shared_schema.owner_username == owner.username


def test_api_key_state_helpers_update_org_and_enabled_flags():
    db = _session()
    owner = _seed_user(db)
    key_a = UserApiKey(id="a", tenant_id="t1", user_id=owner.id, name="A", key="scope-a", is_enabled=True, is_default=False)
    key_b = UserApiKey(id="b", tenant_id="t1", user_id=owner.id, name="B", key="scope-b", is_enabled=False, is_default=False)
    db.add_all([key_a, key_b])
    db.commit()

    now = datetime.now(timezone.utc)
    api_key_ops._disable_other_enabled_keys(db, owner.id, "t1", now, exclude_key_id="a")
    db.commit()
    assert db.query(UserApiKey).filter_by(id="a").first().is_enabled is True
    assert db.query(UserApiKey).filter_by(id="b").first().is_enabled is False

    api_key_ops._set_org_id(owner, "scope-b", now)
    assert owner.org_id == "scope-b"
    unchanged = owner.updated_at
    api_key_ops._set_org_id(owner, "scope-b", now)
    assert owner.updated_at == unchanged


def test_set_api_key_hidden_and_delete_share_paths(monkeypatch):
    db = _session()
    owner = _seed_user(db)
    other = _seed_user(db, user_id="u2", username="user2", email="u2@example.com")
    key = UserApiKey(id="k1", tenant_id="t1", user_id=owner.id, name="Key", key="scope-1", is_enabled=True, is_default=False)
    share = ApiKeyShare(tenant_id="t1", api_key_id=key.id, owner_user_id=owner.id, shared_user_id=other.id, can_use=True)
    db.add_all([key, share])
    db.commit()

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(api_key_ops, "get_db_session", fake_session)
    service = _service()

    with pytest.raises(HTTPException, match="cannot hide your own"):
        api_key_ops.set_api_key_hidden(service, owner.id, key.id, True)

    assert api_key_ops.set_api_key_hidden(service, other.id, key.id, True) is True
    assert db.query(HiddenApiKey).filter_by(user_id=other.id, api_key_id=key.id).first() is not None
    assert api_key_ops.set_api_key_hidden(service, other.id, key.id, False) is True
    assert db.query(HiddenApiKey).filter_by(user_id=other.id, api_key_id=key.id).first() is None

    assert api_key_ops.delete_api_key_share(service, owner.id, "t1", key.id, "missing") is False
    assert api_key_ops.delete_api_key_share(service, owner.id, "t1", key.id, other.id) is True
    with pytest.raises(ValueError, match="API key not found"):
        api_key_ops.delete_api_key_share(service, owner.id, "t1", "missing", other.id)


def test_create_update_delete_and_backfill_api_keys(monkeypatch):
    db = _session()
    owner = _seed_user(db)
    other = _seed_user(db, user_id="u2", username="user2", email="u2@example.com")
    share_owner = _seed_user(db, user_id="u4", username="shareowner", email="u4@example.com", org_id="share-org")
    toggle_owner = _seed_user(db, user_id="u5", username="toggleowner", email="u5@example.com", org_id="toggle-org")
    solo_owner = _seed_user(db, user_id="u6", username="soloowner", email="u6@example.com", org_id="solo-org")
    foreign_tenant = Tenant(id="t2", name="tenant-t2", display_name="T2", is_active=True)
    foreign_user = User(id="u3", tenant_id="t2", username="user3", email="u3@example.com", hashed_password="x", org_id="org-x", is_active=True)
    foreign_key = UserApiKey(id="k-foreign", tenant_id="t2", user_id="u3", name="Foreign", key="dup-scope", is_enabled=True)
    db.add_all([foreign_tenant, foreign_user, foreign_key])
    db.commit()

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(api_key_ops, "get_db_session", fake_session)
    generated_ids = iter(["generated-scope", "share-id-1", "share-id-2", "share-id-3"])
    monkeypatch.setattr(uuid, "uuid4", lambda: next(generated_ids))
    service = _service()

    with pytest.raises(ValueError, match="another tenant"):
        api_key_ops.create_api_key(service, owner.id, "t1", ApiKeyCreate(name="KeyA", key="dup-scope"))

    created = api_key_ops.create_api_key(service, owner.id, "t1", ApiKeyCreate(name="KeyA", key=None))
    assert created.key == "generated-scope"
    assert created.otlp_token == "otlp-token-1"

    with pytest.raises(ValueError, match="name already exists"):
        api_key_ops.create_api_key(service, owner.id, "t1", ApiKeyCreate(name="KeyA", key="other-scope"))

    owner_key = db.query(UserApiKey).filter_by(id=created.id).first()
    shared_key = UserApiKey(id="k-shared", tenant_id="t1", user_id=share_owner.id, name="Shared", key="scope-shared", is_default=False, is_enabled=True)
    toggle_enabled = UserApiKey(id="k-toggle-enabled", tenant_id="t1", user_id=toggle_owner.id, name="Enabled", key="scope-enabled", is_default=False, is_enabled=True)
    toggle_disabled = UserApiKey(id="k-toggle-disabled", tenant_id="t1", user_id=toggle_owner.id, name="Disabled", key="scope-disabled", is_default=False, is_enabled=False)
    solo_key = UserApiKey(id="k-solo", tenant_id="t1", user_id=solo_owner.id, name="Solo", key="scope-solo", is_default=False, is_enabled=True)
    db.add_all([shared_key, toggle_enabled, toggle_disabled, solo_key])
    db.flush()
    db.add(ApiKeyShare(tenant_id="t1", api_key_id=shared_key.id, owner_user_id=share_owner.id, shared_user_id=other.id, can_use=True))
    db.commit()

    with pytest.raises(ValueError, match="only be selected as active"):
        api_key_ops.update_api_key(service, other.id, shared_key.id, ApiKeyUpdate(name="rename"))
    with pytest.raises(ValueError, match="requires is_enabled=true"):
        api_key_ops.update_api_key(service, other.id, shared_key.id, ApiKeyUpdate(is_enabled=False))
    shared_selected = api_key_ops.update_api_key(service, other.id, shared_key.id, ApiKeyUpdate(is_enabled=True))
    assert shared_selected.is_shared is True
    assert db.query(User).filter_by(id=other.id).first().org_id == shared_key.key

    db.add(ApiKeyShare(tenant_id="t1", api_key_id=owner_key.id, owner_user_id=owner.id, shared_user_id=other.id, can_use=True))
    db.commit()
    with pytest.raises(ValueError, match="Remove shares first"):
        api_key_ops.update_api_key(service, owner.id, owner_key.id, ApiKeyUpdate(is_default=True))
    db.query(ApiKeyShare).filter_by(api_key_id=owner_key.id).delete()
    db.commit()

    promoted = api_key_ops.update_api_key(service, owner.id, owner_key.id, ApiKeyUpdate(is_default=True))
    assert promoted.is_default is True
    assert db.query(User).filter_by(id=owner.id).first().org_id == owner_key.key

    with pytest.raises(ValueError, match="Default key cannot be disabled"):
        api_key_ops.update_api_key(service, owner.id, owner_key.id, ApiKeyUpdate(is_enabled=False))

    with pytest.raises(ValueError, match="At least one API key must be enabled"):
        api_key_ops.update_api_key(service, solo_owner.id, solo_key.id, ApiKeyUpdate(is_enabled=False))

    with pytest.raises(HTTPException, match="Not authorized to rotate"):
        api_key_ops.regenerate_api_key_otlp_token(service, other.id, owner_key.id)

    rotated = api_key_ops.regenerate_api_key_otlp_token(service, toggle_owner.id, toggle_disabled.id)
    assert rotated.otlp_token == "otlp-token-2"

    assert api_key_ops.delete_api_key(service, "missing", toggle_disabled.id) is False
    assert api_key_ops.delete_api_key(service, owner.id, "missing") is False
    with pytest.raises(HTTPException, match="Not authorized"):
        api_key_ops.delete_api_key(service, other.id, toggle_disabled.id)
    with pytest.raises(ValueError, match="cannot be deleted"):
        api_key_ops.delete_api_key(service, owner.id, owner_key.id)
    assert api_key_ops.delete_api_key(service, toggle_owner.id, toggle_disabled.id) is True

    no_hash = UserApiKey(id="k-backfill", tenant_id="t1", user_id=owner.id, name="Backfill", key="scope-backfill", otlp_token="plain", otlp_token_hash=None, is_enabled=False)
    db.add(no_hash)
    db.commit()
    api_key_ops.backfill_otlp_tokens(service)
    refreshed = db.query(UserApiKey).filter_by(id="k-backfill").first()
    assert refreshed.otlp_token is None
    assert refreshed.otlp_token_hash == "hash:plain"
