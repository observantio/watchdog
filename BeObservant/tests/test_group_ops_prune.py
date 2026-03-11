"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/observantio_test")
os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "False")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

from db_models import Base, GrafanaDashboard, GrafanaDatasource, GrafanaFolder, Group, Tenant, User
from services.auth.group_ops import _prune_removed_member_grafana_group_shares


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_prune_removed_member_grafana_group_shares_sets_private_and_clears_group():
    db = _session()
    tenant = Tenant(id="t1", name="tenant-1", display_name="Tenant 1")
    owner = User(
        id="u1",
        tenant_id="t1",
        username="owner",
        email="owner@example.com",
        hashed_password="x",
        org_id="org-a",
        is_active=True,
    )
    group = Group(id="g1", tenant_id="t1", name="Team A")
    db.add_all([tenant, owner, group])
    db.commit()

    dash = GrafanaDashboard(
        tenant_id="t1",
        created_by="u1",
        grafana_uid="dash-1",
        title="Dash",
        visibility="group",
    )
    ds = GrafanaDatasource(
        tenant_id="t1",
        created_by="u1",
        grafana_uid="ds-1",
        name="DS",
        type="prometheus",
        visibility="group",
    )
    folder = GrafanaFolder(
        tenant_id="t1",
        created_by="u1",
        grafana_uid="folder-1",
        title="Folder",
        visibility="group",
    )
    dash.shared_groups.append(group)
    ds.shared_groups.append(group)
    folder.shared_groups.append(group)
    db.add_all([dash, ds, folder])
    db.commit()

    _prune_removed_member_grafana_group_shares(
        db,
        tenant_id="t1",
        group_id="g1",
        removed_user_ids=["u1"],
    )
    db.commit()

    dash = db.query(GrafanaDashboard).filter_by(grafana_uid="dash-1", tenant_id="t1").first()
    ds = db.query(GrafanaDatasource).filter_by(grafana_uid="ds-1", tenant_id="t1").first()
    folder = db.query(GrafanaFolder).filter_by(grafana_uid="folder-1", tenant_id="t1").first()

    assert dash is not None and dash.visibility == "private" and len(dash.shared_groups or []) == 0
    assert ds is not None and ds.visibility == "private" and len(ds.shared_groups or []) == 0
    assert folder is not None and folder.visibility == "private" and len(folder.shared_groups or []) == 0
