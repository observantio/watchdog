"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from tests._env import ensure_test_env
ensure_test_env()

import pytest
import pyotp

from database import get_db_session
from config import config
from services.database_auth_service import DatabaseAuthService
from models.access.user_models import UserCreate
from db_models import Tenant


import database

@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_enroll_and_verify_mfa_flow():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    user = svc.create_user(UserCreate(username='mfa-user', email='mfa-user@example.com', password='pwstrong', full_name='MFA User'), tenant_id)
    payload = svc.enroll_totp(user.id)
    assert 'secret' in payload and payload['secret']
    secret = payload['secret']
    code = pyotp.TOTP(secret).now()
    recovery_codes = svc.verify_enable_totp(user.id, code)
    assert isinstance(recovery_codes, list) and len(recovery_codes) > 0
    updated = svc.get_user_by_id(user.id)
    assert updated.mfa_enabled is True


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_skip_local_mfa_for_external(monkeypatch):
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    user = svc.create_user(
        UserCreate(username='ext-mfa', email='ext-mfa@example.com', password='pw', full_name='External MFA'),
        tenant_id,
    )

    with get_db_session() as db:
        db_user = db.query(User).filter_by(id=user.id).first()
        db_user.auth_provider = 'oidc'
        db_user.must_setup_mfa = True
        db_user.mfa_enabled = False
        db.commit()

    result = svc._check_local_mfa(svc, db_user, None)
    assert result is True

    monkeypatch.setattr(config, 'SKIP_LOCAL_MFA_FOR_EXTERNAL', False)
    result2 = svc._check_local_mfa(svc, db_user, None)
    assert isinstance(result2, dict) and result2.get('mfa_setup_required')
