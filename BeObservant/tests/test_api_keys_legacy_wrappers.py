"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from fastapi import HTTPException

from tests._env import ensure_test_env

ensure_test_env()

from config import config as global_config
from db_models import Tenant, User
from tests import test_api_keys as legacy_api_keys


class FakeQuery:
    def __init__(self, items):
        self._items = list(items)

    def filter_by(self, **kwargs):
        self._items = [item for item in self._items if all(getattr(item, key, None) == value for key, value in kwargs.items())]
        return self

    def first(self):
        return self._items[0] if self._items else None


class FakeSession:
    def __init__(self):
        self.tenants = [Tenant(id="t-default", name="default", display_name="Default", is_active=True)]
        self.users = []

    def query(self, model):
        mapping = {
            "Tenant": self.tenants,
            "User": self.users,
        }
        return FakeQuery(mapping[model.__name__])

    def add(self, obj):
        if isinstance(obj, Tenant) and obj not in self.tenants:
            self.tenants.append(obj)

    def flush(self):
        return None

    def commit(self):
        return None


class FakeApiKeyService:
    def __init__(self, db):
        self.db = db
        self._user_counter = 0
        self._key_counter = 0
        self._users = {}
        self._keys = {}
        self._shares = {}
        self._valid_tokens = {}

    def _lazy_init(self):
        return None

    def create_user(self, user_create, tenant_id):
        self._user_counter += 1
        user = User(
            id=f"u-{self._user_counter}",
            tenant_id=tenant_id,
            username=user_create.username,
            email=user_create.email,
            hashed_password="x",
            full_name=getattr(user_create, "full_name", None),
            org_id="default",
            is_active=True,
        )
        self.db.users.append(user)
        self._users[user.id] = user
        self._key_counter += 1
        token = f"token-{self._key_counter}"
        default_key = SimpleNamespace(
            id=f"k-{self._key_counter}",
            owner_id=user.id,
            tenant_id=tenant_id,
            name="__implicit_default__",
            key=f"default-{user.id}",
            is_default=True,
            is_enabled=True,
            current_token=token,
        )
        self._keys[default_key.id] = default_key
        self._valid_tokens[token] = default_key.key
        user.org_id = default_key.key
        return user

    def create_api_key(self, owner_id, tenant_id, api_key_create):
        owner_keys = [key for key in self._keys.values() if key.owner_id == owner_id]
        for key in owner_keys:
            if key.name.lower() == api_key_create.name.lower():
                raise ValueError("name already exists")
        for key in self._keys.values():
            if key.key == api_key_create.key and key.tenant_id != tenant_id:
                raise ValueError("already assigned to another tenant")
        self._key_counter += 1
        token = f"token-{self._key_counter}"
        record = SimpleNamespace(
            id=f"k-{self._key_counter}",
            owner_id=owner_id,
            tenant_id=tenant_id,
            name=api_key_create.name,
            key=api_key_create.key,
            is_default=("default" in api_key_create.name.lower()),
            is_enabled=True,
            current_token=token,
        )
        self._keys[record.id] = record
        self._valid_tokens[token] = record.key
        self._users[owner_id].org_id = record.key
        return SimpleNamespace(id=record.id, key=record.key, name=record.name, otlp_token=token, is_default=record.is_default)

    def replace_api_key_shares(self, owner_id, tenant_id, key_id, user_ids, group_ids=None):
        record = self._keys[key_id]
        if record.is_default:
            raise ValueError("Default key cannot be shared")
        self._shares[key_id] = list(user_ids)
        return True

    def list_api_keys(self, user_id):
        result = []
        for record in self._keys.values():
            if record.owner_id == user_id:
                result.append(SimpleNamespace(
                    id=record.id,
                    key=record.key,
                    name=record.name,
                    is_shared=False,
                    is_default=record.is_default,
                    is_enabled=record.is_enabled,
                    otlp_token=None,
                ))
            elif user_id in self._shares.get(record.id, []):
                owner = self._users[record.owner_id]
                result.append(SimpleNamespace(
                    id=record.id,
                    key=record.key,
                    name=record.name,
                    is_shared=True,
                    is_default=False,
                    is_enabled=(self._users[user_id].org_id == record.key),
                    otlp_token=None,
                    owner_user_id=owner.id,
                    owner_username=owner.username,
                ))
        return result

    def delete_api_key(self, actor_id, key_id):
        record = self._keys[key_id]
        if actor_id != record.owner_id:
            raise HTTPException(status_code=403, detail="forbidden")
        del self._keys[key_id]
        self._shares.pop(key_id, None)
        return True

    def regenerate_api_key_otlp_token(self, owner_id, key_id):
        record = self._keys[key_id]
        if record.is_default:
            raise HTTPException(status_code=403, detail="cannot be regenerated")
        old = record.current_token
        self._valid_tokens.pop(old, None)
        self._key_counter += 1
        token = f"token-{self._key_counter}"
        record.current_token = token
        self._valid_tokens[token] = record.key
        return SimpleNamespace(id=record.id, otlp_token=token)

    def validate_otlp_token(self, token):
        return self._valid_tokens.get(token)

    def update_api_key(self, actor_id, key_id, api_key_update):
        record = self._keys[key_id]
        actor = self._users[actor_id]
        if actor_id != record.owner_id:
            if getattr(api_key_update, "is_enabled", None) is True:
                actor.org_id = record.key
                for owned in self._keys.values():
                    if owned.owner_id == actor_id:
                        owned.is_enabled = False
                return SimpleNamespace(id=record.id, is_enabled=True)
            raise ValueError("shared")
        if getattr(api_key_update, "is_default", None):
            if self._shares.get(record.id):
                raise ValueError("Shared keys cannot be set as default")
            record.is_default = True
        if getattr(api_key_update, "is_enabled", None) is True:
            for owned in self._keys.values():
                if owned.owner_id == actor_id:
                    owned.is_enabled = owned.id == key_id
            actor.org_id = record.key
        if getattr(api_key_update, "is_enabled", None) is False:
            record.is_enabled = False
            defaults = [owned for owned in self._keys.values() if owned.owner_id == actor_id and owned.is_default]
            if defaults:
                defaults[0].is_enabled = True
                actor.org_id = defaults[0].key
        return SimpleNamespace(id=record.id, is_enabled=record.is_enabled)


def _patch_legacy_api_keys(monkeypatch, db, svc):
    @contextmanager
    def fake_session_ctx():
        yield db

    monkeypatch.setattr(legacy_api_keys, "get_db_session", fake_session_ctx)
    monkeypatch.setattr(legacy_api_keys, "DatabaseAuthService", lambda: svc)
    monkeypatch.setattr(legacy_api_keys, "UserCreate", lambda **kwargs: SimpleNamespace(**kwargs), raising=False)
    monkeypatch.setattr(legacy_api_keys, "database", SimpleNamespace(connection_test=lambda: False), raising=False)
    monkeypatch.setattr(global_config, "DEFAULT_ADMIN_TENANT", "default", raising=False)


def _run(monkeypatch, func):
    db = FakeSession()
    svc = FakeApiKeyService(db)
    _patch_legacy_api_keys(monkeypatch, db, svc)
    return func()


def test_executes_legacy_api_key_shared_visibility_body(monkeypatch):
    _run(monkeypatch, legacy_api_keys.test_list_api_keys_hides_otlp_token_for_shared_user)


def test_executes_legacy_api_key_owner_reveal_body(monkeypatch):
    _run(monkeypatch, legacy_api_keys.test_otlp_token_is_one_time_reveal_for_owner)


def test_executes_legacy_api_key_delete_forbidden_body(monkeypatch):
    _run(monkeypatch, legacy_api_keys.test_delete_api_key_by_non_owner_returns_403)


def test_executes_legacy_api_key_delete_owner_body(monkeypatch):
    _run(monkeypatch, legacy_api_keys.test_delete_api_key_by_owner_succeeds)


def test_executes_legacy_api_key_enable_switch_body(monkeypatch):
    _run(monkeypatch, legacy_api_keys.test_enabling_owned_key_updates_user_org_and_keeps_single_active_view)


def test_executes_legacy_api_key_default_share_forbidden_body(monkeypatch):
    _run(monkeypatch, legacy_api_keys.test_default_api_key_cannot_be_shared)


def test_executes_legacy_api_key_default_regen_forbidden_body(monkeypatch):
    _run(monkeypatch, legacy_api_keys.test_default_api_key_otlp_token_cannot_be_regenerated)


def test_executes_legacy_api_key_shared_default_forbidden_body(monkeypatch):
    _run(monkeypatch, legacy_api_keys.test_shared_key_cannot_be_set_as_default)


def test_executes_legacy_api_key_cross_tenant_collision_body(monkeypatch):
    _run(monkeypatch, legacy_api_keys.test_api_key_value_cannot_collide_across_tenants)


def test_executes_legacy_api_key_name_uniqueness_body(monkeypatch):
    _run(monkeypatch, legacy_api_keys.test_api_key_name_must_be_unique_case_insensitive_per_owner)


def test_executes_legacy_api_key_regen_reveal_body(monkeypatch):
    _run(monkeypatch, legacy_api_keys.test_regenerate_otlp_token_returns_one_time_reveal)


def test_executes_legacy_api_key_ingest_token_body(monkeypatch):
    _run(monkeypatch, legacy_api_keys.test_inactive_key_otlp_tokens_remain_valid_for_ingest)


def test_executes_legacy_api_key_enabled_constraint_body(monkeypatch):
    _run(monkeypatch, legacy_api_keys.test_switching_between_owned_enabled_keys_preserves_unique_enabled_constraint)


def test_executes_legacy_api_key_disable_fallback_body(monkeypatch):
    _run(monkeypatch, legacy_api_keys.test_disabling_owned_non_default_key_falls_back_to_default_key)
