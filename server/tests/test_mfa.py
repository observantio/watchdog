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

    # create a user and enroll TOTP
    user = svc.create_user(UserCreate(username='mfa-user', email='mfa-user@example.com', password='pwstrong', full_name='MFA User'), tenant_id)
    payload = svc.enroll_totp(user.id)
    assert 'secret' in payload and payload['secret']

    # verify with a correct code
    secret = payload['secret']
    code = pyotp.TOTP(secret).now()
    recovery_codes = svc.verify_enable_totp(user.id, code)
    assert isinstance(recovery_codes, list) and len(recovery_codes) > 0

    # ensure user now has MFA enabled
    updated = svc.get_user_by_id(user.id)
    assert updated.mfa_enabled is True


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_skip_local_mfa_for_external(monkeypatch):
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        tenant_id = tenant.id

    # create a normal local user and simulate MFA requirement
    user = svc.create_user(
        UserCreate(username='ext-mfa', email='ext-mfa@example.com', password='pw', full_name='External MFA'),
        tenant_id,
    )

    # mark the account as belonging to an external provider and require setup
    with get_db_session() as db:
        db_user = db.query(User).filter_by(id=user.id).first()
        db_user.auth_provider = 'oidc'
        db_user.must_setup_mfa = True
        db_user.mfa_enabled = False
        db.commit()

    # default config skips local MFA for external users
    result = svc._check_local_mfa(svc, db_user, None)
    assert result is True

    # if the flag is disabled we should see the normal challenge behavior
    monkeypatch.setattr(config, 'SKIP_LOCAL_MFA_FOR_EXTERNAL', False)
    result2 = svc._check_local_mfa(svc, db_user, None)
    assert isinstance(result2, dict) and result2.get('mfa_setup_required')
