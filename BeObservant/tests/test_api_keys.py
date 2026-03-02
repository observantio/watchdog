"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from tests._env import ensure_test_env
ensure_test_env()

import pytest
from fastapi import HTTPException
import uuid

import database
from database import get_db_session
from config import config
from services.database_auth_service import DatabaseAuthService
from models.access.user_models import UserCreate
from models.access.api_key_models import ApiKeyCreate, ApiKeyUpdate
from db_models import Tenant, User


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_list_api_keys_hides_otlp_token_for_shared_user():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    owner = svc.create_user(UserCreate(username='owner', email='owner@example.com', password='pw', full_name='Owner'), tenant_id)
    other = svc.create_user(UserCreate(username='other', email='other@example.com', password='pw', full_name='Other'), tenant_id)

    created = svc.create_api_key(owner.id, tenant_id, ApiKeyCreate(name='owner-key', key='org-owner'))
    assert created.otlp_token  

    
    svc.replace_api_key_shares(owner.id, tenant_id, created.id, [other.id], group_ids=[])

    keys_for_other = svc.list_api_keys(other.id)
    shared_entry = next((k for k in keys_for_other if k.id == created.id), None)
    assert shared_entry is not None
    assert shared_entry.is_shared is True
    assert shared_entry.otlp_token is None
    assert shared_entry.owner_user_id == owner.id
    assert getattr(shared_entry, 'owner_username', None) == owner.username


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_otlp_token_is_one_time_reveal_for_owner():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    owner = svc.create_user(UserCreate(username='owner-otlp', email='owner-otlp@example.com', password='pw', full_name='Owner'), tenant_id)
    created = svc.create_api_key(owner.id, tenant_id, ApiKeyCreate(name='owner-key-otlp', key='org-owner-otlp'))
    assert created.otlp_token

    listed = svc.list_api_keys(owner.id)
    owner_entry = next((k for k in listed if k.id == created.id), None)
    assert owner_entry is not None
    assert owner_entry.otlp_token is None


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_delete_api_key_by_non_owner_returns_403():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    owner = svc.create_user(UserCreate(username='del-owner', email='del-owner@example.com', password='pw', full_name='Owner'), tenant_id)
    other = svc.create_user(UserCreate(username='del-other', email='del-other@example.com', password='pw', full_name='Other'), tenant_id)

    created = svc.create_api_key(owner.id, tenant_id, ApiKeyCreate(name='del-key', key='org-del'))
    svc.replace_api_key_shares(owner.id, tenant_id, created.id, [other.id], group_ids=[])

    with pytest.raises(HTTPException) as exc:
        svc.delete_api_key(other.id, created.id)
    assert exc.value.status_code == 403


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_delete_api_key_by_owner_succeeds():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    owner = svc.create_user(UserCreate(username='owner2', email='owner2@example.com', password='pw', full_name='Owner'), tenant_id)
    created = svc.create_api_key(owner.id, tenant_id, ApiKeyCreate(name='owner2-key', key='org-owner2'))

    ok = svc.delete_api_key(owner.id, created.id)
    assert ok is True


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_enabling_owned_key_updates_user_org_and_keeps_single_active_view():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    owner = svc.create_user(UserCreate(username='owner3', email='owner3@example.com', password='pw', full_name='Owner'), tenant_id)
    other = svc.create_user(UserCreate(username='other3', email='other3@example.com', password='pw', full_name='Other'), tenant_id)

    shared_key = svc.create_api_key(owner.id, tenant_id, ApiKeyCreate(name='shared-key', key='org-shared-1'))
    mine = svc.create_api_key(other.id, tenant_id, ApiKeyCreate(name='mine', key='org-mine-1'))
    svc.replace_api_key_shares(owner.id, tenant_id, shared_key.id, [other.id], group_ids=[])

    
    svc.update_api_key(other.id, shared_key.id, ApiKeyUpdate(is_enabled=True))
    keys_after_shared = svc.list_api_keys(other.id)
    mine_after_shared = next(k for k in keys_after_shared if k.id == mine.id)
    shared_after_shared = next(k for k in keys_after_shared if k.id == shared_key.id)
    assert mine_after_shared.is_enabled is False
    assert shared_after_shared.is_enabled is True

    
    svc.update_api_key(other.id, mine.id, ApiKeyUpdate(is_enabled=True))
    keys_after_mine = svc.list_api_keys(other.id)
    mine_after_mine = next(k for k in keys_after_mine if k.id == mine.id)
    shared_after_mine = next(k for k in keys_after_mine if k.id == shared_key.id)
    assert mine_after_mine.is_enabled is True
    assert shared_after_mine.is_enabled is False

    with get_db_session() as db:
        db_user = db.query(User).filter_by(id=other.id).first()
        assert db_user is not None
        assert db_user.org_id == 'org-mine-1'


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_default_api_key_cannot_be_shared():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    owner = svc.create_user(UserCreate(username='owner4', email='owner4@example.com', password='pw', full_name='Owner'), tenant_id)
    other = svc.create_user(UserCreate(username='other4', email='other4@example.com', password='pw', full_name='Other'), tenant_id)

    default_key = svc.create_api_key(owner.id, tenant_id, ApiKeyCreate(name='default-key', key='org-default-1'))
    assert default_key.is_default is True

    with pytest.raises(ValueError, match="Default key cannot be shared"):
        svc.replace_api_key_shares(owner.id, tenant_id, default_key.id, [other.id], group_ids=[])


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_default_api_key_otlp_token_cannot_be_regenerated():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    owner = svc.create_user(UserCreate(username='owner-default-regen', email='owner-default-regen@example.com', password='pw', full_name='Owner'), tenant_id)
    default_key = svc.create_api_key(owner.id, tenant_id, ApiKeyCreate(name='default-key-regen', key='org-default-regen-1'))
    assert default_key.is_default is True

    with pytest.raises(HTTPException) as exc:
        svc.regenerate_api_key_otlp_token(owner.id, default_key.id)
    assert exc.value.status_code == 403
    assert "cannot be regenerated" in str(exc.value.detail).lower()


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_shared_key_cannot_be_set_as_default():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    owner = svc.create_user(UserCreate(username='owner5', email='owner5@example.com', password='pw', full_name='Owner'), tenant_id)
    other = svc.create_user(UserCreate(username='other5', email='other5@example.com', password='pw', full_name='Other'), tenant_id)

    svc.create_api_key(owner.id, tenant_id, ApiKeyCreate(name='default-owner-key', key='org-owner-default-1'))
    shared_candidate = svc.create_api_key(owner.id, tenant_id, ApiKeyCreate(name='shared-candidate', key='org-shared-candidate-1'))
    svc.replace_api_key_shares(owner.id, tenant_id, shared_candidate.id, [other.id], group_ids=[])

    with pytest.raises(ValueError, match="Shared keys cannot be set as default"):
        svc.update_api_key(owner.id, shared_candidate.id, ApiKeyUpdate(is_default=True))


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_api_key_value_cannot_collide_across_tenants():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant_a = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_a_id = tenant_a.id
        tenant_b = Tenant(
            name=f"tenant-{uuid.uuid4().hex[:8]}",
            display_name="Tenant B",
            is_active=True,
        )
        db.add(tenant_b)
        db.flush()
        tenant_b_id = tenant_b.id

    owner_a = svc.create_user(UserCreate(username='owner6', email='owner6@example.com', password='pw', full_name='Owner'), tenant_a_id)
    owner_b = svc.create_user(UserCreate(username='owner7', email='owner7@example.com', password='pw', full_name='Owner'), tenant_b_id)

    scope_value = f"scope-{uuid.uuid4().hex[:10]}"
    created_a = svc.create_api_key(owner_a.id, tenant_a_id, ApiKeyCreate(name='a-key', key=scope_value))
    assert created_a.key == scope_value

    with pytest.raises(ValueError, match="another tenant"):
        svc.create_api_key(owner_b.id, tenant_b_id, ApiKeyCreate(name='b-key', key=scope_value))


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_regenerate_otlp_token_returns_one_time_reveal():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    owner = svc.create_user(UserCreate(username='owner8', email='owner8@example.com', password='pw', full_name='Owner'), tenant_id)
    created = svc.create_api_key(owner.id, tenant_id, ApiKeyCreate(name='regen-key', key='org-regen-1'))
    assert created.otlp_token

    rotated = svc.regenerate_api_key_otlp_token(owner.id, created.id)
    assert rotated.otlp_token
    assert rotated.otlp_token != created.otlp_token

    listed = svc.list_api_keys(owner.id)
    listed_entry = next((k for k in listed if k.id == created.id), None)
    assert listed_entry is not None
    assert listed_entry.otlp_token is None


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_inactive_key_otlp_tokens_remain_valid_for_ingest():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    owner = svc.create_user(
        UserCreate(username='owner-ingest', email='owner-ingest@example.com', password='pw', full_name='Owner'),
        tenant_id,
    )
    first = svc.create_api_key(owner.id, tenant_id, ApiKeyCreate(name='first-key', key='org-ingest-1'))
    second = svc.create_api_key(owner.id, tenant_id, ApiKeyCreate(name='second-key', key='org-ingest-2'))

    assert first.otlp_token
    assert second.otlp_token
    assert svc.validate_otlp_token(first.otlp_token) == 'org-ingest-1'
    assert svc.validate_otlp_token(second.otlp_token) == 'org-ingest-2'

    rotated_first = svc.regenerate_api_key_otlp_token(owner.id, first.id)
    assert rotated_first.otlp_token
    assert svc.validate_otlp_token(first.otlp_token) is None
    assert svc.validate_otlp_token(rotated_first.otlp_token) == 'org-ingest-1'


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_switching_between_owned_enabled_keys_preserves_unique_enabled_constraint():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    owner = svc.create_user(UserCreate(username='owner9', email='owner9@example.com', password='pw', full_name='Owner'), tenant_id)
    key_a = svc.create_api_key(owner.id, tenant_id, ApiKeyCreate(name='key-a', key='org-switch-a'))
    key_b = svc.create_api_key(owner.id, tenant_id, ApiKeyCreate(name='key-b', key='org-switch-b'))

    svc.update_api_key(owner.id, key_a.id, ApiKeyUpdate(is_enabled=True))
    after_a = svc.list_api_keys(owner.id)
    key_a_after_a = next(k for k in after_a if k.id == key_a.id)
    key_b_after_a = next(k for k in after_a if k.id == key_b.id)
    assert key_a_after_a.is_enabled is True
    assert key_b_after_a.is_enabled is False

    svc.update_api_key(owner.id, key_b.id, ApiKeyUpdate(is_enabled=True))
    after_b = svc.list_api_keys(owner.id)
    key_a_after_b = next(k for k in after_b if k.id == key_a.id)
    key_b_after_b = next(k for k in after_b if k.id == key_b.id)
    assert key_a_after_b.is_enabled is False
    assert key_b_after_b.is_enabled is True
