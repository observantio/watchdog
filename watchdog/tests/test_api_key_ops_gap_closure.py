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
from sqlalchemy.orm import sessionmaker

from tests._env import ensure_test_env

ensure_test_env()

from db_models import ApiKeyShare, Base, Group, HiddenApiKey, Tenant, User, UserApiKey
from services.auth import api_key_ops


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _service() -> SimpleNamespace:
    return SimpleNamespace(
        _lazy_init=lambda: None,
        _log_audit=lambda *args, **kwargs: None,
    )


def _seed_user(db, *, user_id: str, tenant_id: str = "t1", username: str | None = None, org_id: str = "org-default"):
    tenant = db.query(Tenant).filter_by(id=tenant_id).first()
    if tenant is None:
        db.add(Tenant(id=tenant_id, name=f"tenant-{tenant_id}", display_name=tenant_id, is_active=True))
    user = User(
        id=user_id,
        tenant_id=tenant_id,
        username=username or user_id,
        email=f"{user_id}@example.com",
        hashed_password="x",
        org_id=org_id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def test_list_api_keys_owned_shared_hidden_and_enabled_logic(monkeypatch):
    db = _session()
    owner = _seed_user(db, user_id="u-owner")
    viewer = _seed_user(db, user_id="u-viewer", org_id="org-shared")

    owned_visible = UserApiKey(
        id="k-own-visible",
        tenant_id="t1",
        user_id=viewer.id,
        name="Owned Visible",
        key="org-owned",
        is_enabled=True,
        is_default=False,
    )
    owned_hidden = UserApiKey(
        id="k-own-hidden",
        tenant_id="t1",
        user_id=viewer.id,
        name="Owned Hidden",
        key="org-hidden",
        is_enabled=False,
        is_default=False,
    )
    shared_key = UserApiKey(
        id="k-shared",
        tenant_id="t1",
        user_id=owner.id,
        name="Shared",
        key="org-shared",
        is_enabled=True,
        is_default=False,
    )
    db.add_all([owned_visible, owned_hidden, shared_key])
    db.flush()
    db.add(
        ApiKeyShare(
            tenant_id="t1",
            api_key_id=shared_key.id,
            owner_user_id=owner.id,
            shared_user_id=viewer.id,
            can_use=True,
        )
    )
    db.add(HiddenApiKey(tenant_id="t1", user_id=viewer.id, api_key_id=owned_hidden.id))
    db.commit()

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(api_key_ops, "get_db_session", fake_session)
    service = _service()

    assert api_key_ops.list_api_keys(service, "missing") == []

    visible_only = api_key_ops.list_api_keys(service, viewer.id, show_hidden=False)
    assert [item.id for item in visible_only] == ["k-own-visible", "k-shared"]
    assert visible_only[0].is_shared is False
    assert visible_only[1].is_shared is True
    # viewer has an enabled owned key, so shared keys must not appear enabled in the viewer projection
    assert visible_only[1].is_enabled is False

    with_hidden = api_key_ops.list_api_keys(service, viewer.id, show_hidden=True)
    assert [item.id for item in with_hidden] == ["k-own-visible", "k-own-hidden", "k-shared"]
    hidden_item = next(item for item in with_hidden if item.id == "k-own-hidden")
    assert hidden_item.is_hidden is True


def test_replace_api_key_shares_group_user_validation_and_success_paths(monkeypatch):
    db = _session()
    owner = _seed_user(db, user_id="u-owner")
    user_a = _seed_user(db, user_id="u-a")
    user_b = _seed_user(db, user_id="u-b")
    outsider = _seed_user(db, user_id="u-outsider")

    key = UserApiKey(
        id="k-1",
        tenant_id="t1",
        user_id=owner.id,
        name="NonDefault",
        key="scope-k1",
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
    group_ok = Group(id="g-ok", tenant_id="t1", name="OK", is_active=True)
    group_ok.members.extend([owner, user_a, user_b])
    group_no_owner = Group(id="g-no-owner", tenant_id="t1", name="NoOwner", is_active=True)
    group_no_owner.members.extend([outsider])
    db.add_all([key, default_key, group_ok, group_no_owner])
    db.flush()
    db.add(
        ApiKeyShare(
            tenant_id="t1",
            api_key_id=key.id,
            owner_user_id=owner.id,
            shared_user_id=user_a.id,
            can_use=True,
        )
    )
    db.commit()

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(api_key_ops, "get_db_session", fake_session)
    service = _service()

    with pytest.raises(ValueError, match="Invalid share groups"):
        api_key_ops.replace_api_key_shares(
            service,
            owner_user_id=owner.id,
            tenant_id="t1",
            key_id=key.id,
            user_ids=[],
            group_ids=["g-missing"],
        )

    with pytest.raises(ValueError, match="only share with groups you are in"):
        api_key_ops.replace_api_key_shares(
            service,
            owner_user_id=owner.id,
            tenant_id="t1",
            key_id=key.id,
            user_ids=[],
            group_ids=["g-no-owner"],
        )

    with pytest.raises(ValueError, match="Default key cannot be shared"):
        api_key_ops.replace_api_key_shares(
            service,
            owner_user_id=owner.id,
            tenant_id="t1",
            key_id=default_key.id,
            user_ids=[user_a.id],
            group_ids=[],
        )

    with pytest.raises(ValueError, match="Invalid share users"):
        api_key_ops.replace_api_key_shares(
            service,
            owner_user_id=owner.id,
            tenant_id="t1",
            key_id=key.id,
            user_ids=["u-missing"],
            group_ids=[],
        )

    result = api_key_ops.replace_api_key_shares(
        service,
        owner_user_id=owner.id,
        tenant_id="t1",
        key_id=key.id,
        # include owner + duplicates on purpose; owner must be stripped and duplicates deduped
        user_ids=[owner.id, user_a.id, user_a.id],
        group_ids=["g-ok"],
    )
    shared_user_ids = sorted(item.user_id for item in result)
    assert shared_user_ids == sorted([user_a.id, user_b.id])
