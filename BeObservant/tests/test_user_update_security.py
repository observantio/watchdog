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
import database
from database import get_db_session
from config import config
from services.database_auth_service import DatabaseAuthService
from models.access.user_models import UserCreate, UserUpdate
from models.access.auth_models import Role
from db_models import Tenant, User

@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_non_admin_cannot_escalate_user_role():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    actor = svc.create_user(UserCreate(username='actor1', email='actor1@example.com', password='pw', full_name='Actor'), tenant_id)
    target = svc.create_user(UserCreate(username='target1', email='target1@example.com', password='pw', full_name='Target'), tenant_id)

    with pytest.raises(HTTPException) as exc:
        svc.update_user(target.id, UserUpdate(role=Role.ADMIN), tenant_id, actor.id)
    assert exc.value.status_code == 403


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_non_admin_cannot_create_admin_user():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    actor = svc.create_user(UserCreate(username='creator1', email='creator1@example.com', password='pw', full_name='Creator'), tenant_id)

    with pytest.raises(HTTPException) as exc:
        svc.create_user(
            UserCreate(
                username='admincand1',
                email='admincand1@example.com',
                password='pw',
                full_name='Admin Candidate',
                role=Role.ADMIN,
            ),
            tenant_id,
            creator_id=actor.id,
            actor_role='user',
            actor_permissions=['create:users'],
            actor_is_superuser=False,
        )
    assert exc.value.status_code == 403


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_admin_can_only_toggle_is_active_for_another_admin():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    actor = svc.create_user(UserCreate(username='admin-actor', email='admin-actor@example.com', password='pw', full_name='Actor'), tenant_id)
    target = svc.create_user(UserCreate(username='admin-target', email='admin-target@example.com', password='pw', full_name='Target'), tenant_id)

    with get_db_session() as db:
        db_actor = db.query(User).filter_by(id=actor.id, tenant_id=tenant_id).first()
        db_target = db.query(User).filter_by(id=target.id, tenant_id=tenant_id).first()
        db_actor.role = Role.ADMIN.value
        db_target.role = Role.ADMIN.value
        db.commit()

    with pytest.raises(HTTPException) as exc:
        svc.update_user(target.id, UserUpdate(role=Role.USER), tenant_id, actor.id)
    assert exc.value.status_code == 403
    assert "only be activated or deactivated" in str(exc.value.detail).lower()

    with pytest.raises(HTTPException) as exc:
        svc.update_user(target.id, UserUpdate(full_name='Renamed Target'), tenant_id, actor.id)
    assert exc.value.status_code == 403
    assert "only be activated or deactivated" in str(exc.value.detail).lower()

    updated = svc.update_user(target.id, UserUpdate(is_active=False), tenant_id, actor.id)
    assert updated is not None
    assert updated.is_active is False
