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
from services.database_auth_service import DatabaseAuthService
from models.access.group_models import GroupCreate
from models.access.user_models import UserCreate
from db_models import AuditLog, GrafanaDashboard, GrafanaDatasource, GrafanaFolder, Group, Tenant


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_update_group_permissions_logs_actor_user_id():
    svc = DatabaseAuthService()
    svc._lazy_init()
    with get_db_session() as db:
        tenant = db.query(Tenant).first()
        tenant_id = tenant.id

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


@pytest.mark.skipif(not database.connection_test(), reason="DB not available")
def test_update_group_members_prunes_removed_member_grafana_group_shares():
    svc = DatabaseAuthService()
    svc._lazy_init()

    with get_db_session() as db:
        tenant = db.query(Tenant).first()
        tenant_id = tenant.id

    admin = svc.create_user(
        UserCreate(username="gadmin", email="gadmin@example.com", password="pw", full_name="Admin"),
        tenant_id,
    )
    owner = svc.create_user(
        UserCreate(username="gowner", email="gowner@example.com", password="pw", full_name="Owner"),
        tenant_id,
    )
    member = svc.create_user(
        UserCreate(username="gmember", email="gmember@example.com", password="pw", full_name="Member"),
        tenant_id,
    )

    group = svc.create_group(GroupCreate(name="share-prune-group", description="test"), tenant_id, admin.id)
    svc.update_group_members(
        group.id,
        [owner.id, member.id],
        tenant_id,
        actor_user_id=admin.id,
        actor_role="admin",
    )

    with get_db_session() as db:
        g = db.query(Group).filter_by(id=group.id, tenant_id=tenant_id).first()
        dash = GrafanaDashboard(
            tenant_id=tenant_id,
            created_by=owner.id,
            grafana_uid="dash-prune-u1",
            title="dash-prune",
            visibility="group",
        )
        ds = GrafanaDatasource(
            tenant_id=tenant_id,
            created_by=owner.id,
            grafana_uid="ds-prune-u1",
            name="ds-prune",
            type="prometheus",
            visibility="group",
        )
        folder = GrafanaFolder(
            tenant_id=tenant_id,
            created_by=owner.id,
            grafana_uid="folder-prune-u1",
            title="folder-prune",
            visibility="group",
        )
        dash.shared_groups.append(g)
        ds.shared_groups.append(g)
        folder.shared_groups.append(g)
        db.add_all([dash, ds, folder])
        db.commit()

    svc.update_group_members(
        group.id,
        [member.id],
        tenant_id,
        actor_user_id=admin.id,
        actor_role="admin",
    )

    with get_db_session() as db:
        dash = db.query(GrafanaDashboard).filter_by(tenant_id=tenant_id, grafana_uid="dash-prune-u1").first()
        ds = db.query(GrafanaDatasource).filter_by(tenant_id=tenant_id, grafana_uid="ds-prune-u1").first()
        folder = db.query(GrafanaFolder).filter_by(tenant_id=tenant_id, grafana_uid="folder-prune-u1").first()
        assert dash is not None and dash.visibility == "private" and len(dash.shared_groups or []) == 0
        assert ds is not None and ds.visibility == "private" and len(ds.shared_groups or []) == 0
        assert folder is not None and folder.visibility == "private" and len(folder.shared_groups or []) == 0
