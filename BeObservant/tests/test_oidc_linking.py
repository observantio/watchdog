"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from tests._env import ensure_test_env
ensure_test_env()
import pytest
import database
from database import get_db_session
from config import config
from services.database_auth_service import DatabaseAuthService
from models.access.user_models import UserCreate
from models.access.auth_models import Role


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_oidc_links_existing_local_account(monkeypatch):
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(database.db_models.Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    user = svc.create_user(
        UserCreate(username='linkuser', email='link@example.com', password='pw', full_name='Link User'),
        tenant_id,
    )
    assert user.auth_provider == 'local'

    monkeypatch.setattr(config, 'AUTH_PROVIDER', 'oidc')
    monkeypatch.setattr(config, 'OIDC_AUTO_PROVISION_USERS', True)

    claims = {'email': 'link@example.com', 'sub': 'oidc-subject'}
    linked = svc._sync_user_from_oidc_claims(claims)
    assert linked is not None
    assert linked.id == user.id
    assert linked.auth_provider == 'oidc'
    assert linked.role == Role.VIEWER.value

    # subsequent login should also work and keep provider
    linked2 = svc._sync_user_from_oidc_claims(claims)
    assert linked2 and linked2.id == user.id


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_oidc_refuses_if_auto_provision_disabled(monkeypatch):
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(database.db_models.Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    user = svc.create_user(
        UserCreate(username='noauto', email='noauto@example.com', password='pw', full_name='No Auto'),
        tenant_id,
    )
    assert user.auth_provider == 'local'

    monkeypatch.setattr(config, 'AUTH_PROVIDER', 'oidc')
    monkeypatch.setattr(config, 'OIDC_AUTO_PROVISION_USERS', False)

    claims = {'email': 'noauto@example.com', 'sub': 'oidc-sub2'}
    result = svc._sync_user_from_oidc_claims(claims)
    assert result is None


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_local_user_needs_password_change_with_oidc_enabled(monkeypatch):
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(database.db_models.Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    monkeypatch.setattr(config, 'AUTH_PROVIDER', 'oidc')
    monkeypatch.setattr(config, 'AUTH_PASSWORD_FLOW_ENABLED', True)

    user = svc.create_user(
        UserCreate(username='pwuser', email='pwuser@example.com', password='password123', full_name='Password User'),
        tenant_id,
    )
    assert user.auth_provider == 'local'
    assert user.needs_password_change, "local users should still be prompted to change password"


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_password_login_triggers_expiry_even_if_provider_set(monkeypatch):
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(database.db_models.Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    user = svc.create_user(
        UserCreate(username='expire', email='expire@example.com', password='password123', full_name='Exp'),
        tenant_id,
    )
    assert user.auth_provider == 'local'

    with get_db_session() as db:
        u = db.query(database.db_models.User).filter_by(id=user.id).first()
        u.auth_provider = 'oidc'
        from datetime import timedelta

        u.password_changed_at = u.password_changed_at - timedelta(days=365)
        db.commit()

    monkeypatch.setattr(config, 'PASSWORD_RESET_INTERVAL_DAYS', 30)

    logged = svc.authenticate_user('expire', 'password123')
    assert logged is not None
    assert logged.needs_password_change

@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_oidc_auto_provisions_with_viewer_role(monkeypatch):
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(database.db_models.Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    monkeypatch.setattr(config, 'AUTH_PROVIDER', 'oidc')
    monkeypatch.setattr(config, 'OIDC_AUTO_PROVISION_USERS', True)
    claims = {'email': 'newuser@example.com', 'sub': 'oidc-new'}
    new = svc._sync_user_from_oidc_claims(claims)
    assert new is not None
    assert new.role == Role.VIEWER.value
    assert new.auth_provider == 'oidc'
    assert not getattr(new, "needs_password_change", False)
