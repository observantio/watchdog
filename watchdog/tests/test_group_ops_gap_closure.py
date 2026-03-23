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
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests._env import ensure_test_env

ensure_test_env()

from db_models import Base, GrafanaDashboard, GrafanaDatasource, GrafanaFolder, Group, Permission, Tenant, User
from services.auth import group_ops


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db):
    db.add(Tenant(id="t1", name="tenant-1", display_name="Tenant 1", is_active=True))
    admin = User(id="u-admin", tenant_id="t1", username="admin", email="a@example.com", hashed_password="x", org_id="org", role="admin", is_active=True)
    member = User(id="u-member", tenant_id="t1", username="member", email="m@example.com", hashed_password="x", org_id="org", role="user", is_active=True)
    db.add_all([admin, member])
    db.commit()
    return admin, member


def test_prune_removed_member_grafana_group_shares_reverts_to_private():
    db = _session()
    admin, _member = _seed(db)
    group = Group(id="g1", tenant_id="t1", name="Ops", is_active=True)
    db.add(group)
    db.flush()

    dash = GrafanaDashboard(
        tenant_id="t1",
        created_by=admin.id,
        grafana_uid="d1",
        grafana_id=11,
        title="CPU",
        visibility="group",
    )
    ds = GrafanaDatasource(
        tenant_id="t1",
        created_by=admin.id,
        grafana_uid="ds1",
        grafana_id=22,
        name="Prom",
        type="prometheus",
        visibility="group",
    )
    folder = GrafanaFolder(
        tenant_id="t1",
        created_by=admin.id,
        grafana_uid="f1",
        grafana_id=33,
        title="Folder",
        visibility="group",
    )
    dash.shared_groups.append(group)
    ds.shared_groups.append(group)
    folder.shared_groups.append(group)
    db.add_all([dash, ds, folder])
    db.commit()

    group_ops._prune_removed_member_grafana_group_shares(
        db,
        tenant_id="t1",
        group_id="g1",
        removed_user_ids=[admin.id],
    )
    db.commit()

    assert db.query(GrafanaDashboard).filter_by(grafana_uid="d1").first().visibility == "private"
    assert db.query(GrafanaDatasource).filter_by(grafana_uid="ds1").first().visibility == "private"
    assert db.query(GrafanaFolder).filter_by(grafana_uid="f1").first().visibility == "private"


def test_update_group_permissions_denies_non_admin_for_group_with_admin_member(monkeypatch):
    db = _session()
    admin, member = _seed(db)
    read_perm = Permission(id="p1", name="read:users", display_name="Read", description="d", resource_type="users", action="read")
    group = Group(id="g1", tenant_id="t1", name="Ops", is_active=True)
    group.members.extend([admin, member])
    db.add_all([read_perm, group])
    db.commit()

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(group_ops, "get_db_session", fake_session)
    service = SimpleNamespace(_log_audit=lambda *args, **kwargs: None)

    with pytest.raises(HTTPException, match="Only administrators can modify permissions for groups containing admins"):
        group_ops.update_group_permissions(
            service,
            group_id=group.id,
            permission_names=[read_perm.name],
            tenant_id="t1",
            actor_user_id=member.id,
            actor_role="user",
            actor_permissions=["update:group_permissions", read_perm.name],
            actor_is_superuser=False,
        )
