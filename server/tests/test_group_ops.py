from tests._env import ensure_test_env
ensure_test_env()

import pytest
from fastapi import HTTPException

import database
from database import get_db_session
from services.database_auth_service import DatabaseAuthService
from models.access.group_models import GroupCreate
from models.access.user_models import UserCreate
from db_models import Tenant, AuditLog


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_update_group_permissions_logs_actor_user_id():
    svc = DatabaseAuthService()
    svc._lazy_init()

    # find the default tenant created by bootstrap
    with get_db_session() as db:
        tenant = db.query(Tenant).first()
        tenant_id = tenant.id

    # create a user and a group
    creator = svc.create_user(UserCreate(username='gcreator', email='gcreator@example.com', password='pw', full_name='Creator'), tenant_id)
    group = svc.create_group(GroupCreate(name='test-group', description='test'), tenant_id, creator.id)

    ok = svc.update_group_permissions(
        group.id,
        ['read:agents'],
        tenant_id,
        actor_user_id=creator.id,
        actor_role='user',
    )
    assert ok is True

    # verify actor attribution is present in audit log
    with get_db_session() as db:
        row = db.query(AuditLog).filter_by(action='update_group_permissions', resource_id=group.id).order_by(AuditLog.created_at.desc()).first()
        assert row is not None
        assert row.user_id == creator.id


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_non_admin_cannot_grant_manage_permissions_to_group():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).first()
        tenant_id = tenant.id

    creator = svc.create_user(UserCreate(username='gcreator2', email='gcreator2@example.com', password='pw', full_name='Creator'), tenant_id)
    group = svc.create_group(GroupCreate(name='test-group-2', description='test'), tenant_id, creator.id)

    with pytest.raises(HTTPException) as exc:
        svc.update_group_permissions(
            group.id,
            ['manage:users'],
            tenant_id,
            actor_user_id=creator.id,
            actor_role='user',
        )
    assert exc.value.status_code == 403
