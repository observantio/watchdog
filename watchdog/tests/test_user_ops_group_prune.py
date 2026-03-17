"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
"""

from contextlib import contextmanager
import os
import types

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/observantio_test")
os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "False")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

from db_models import Base, GrafanaDashboard, Group, Tenant, User
from models.access.user_models import UserUpdate
from services.auth import user_ops


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_update_user_group_ids_prunes_grafana_group_shares(monkeypatch):
    db = _session()
    tenant = Tenant(id="t1", name="tenant-1", display_name="Tenant 1")
    user = User(
        id="u1",
        tenant_id="t1",
        username="owner",
        email="owner@example.com",
        hashed_password="x",
        org_id="org-a",
        is_active=True,
    )
    g1 = Group(id="g1", tenant_id="t1", name="Team A")
    g2 = Group(id="g2", tenant_id="t1", name="Team B")
    g1.members.append(user)
    g2.members.append(user)
    db.add_all([tenant, user, g1, g2])
    db.commit()

    dashboard = GrafanaDashboard(
        tenant_id="t1",
        created_by="u1",
        grafana_uid="dash-1",
        title="Dash",
        visibility="group",
    )
    dashboard.shared_groups.append(g1)
    db.add(dashboard)
    db.commit()

    @contextmanager
    def _fake_session():
        try:
            yield db
        finally:
            pass

    monkeypatch.setattr(user_ops, "get_db_session", _fake_session)

    svc = types.SimpleNamespace(
        _lazy_init=lambda: None,
        _to_user_schema=lambda orm_user: orm_user,
        _ensure_default_api_key=lambda *args, **kwargs: None,
        _log_audit=lambda *args, **kwargs: None,
    )

    user_ops.update_user(
        svc,
        "u1",
        UserUpdate(group_ids=["g2"]),
        "t1",
        updater_id=None,
    )

    row = db.query(GrafanaDashboard).filter_by(tenant_id="t1", grafana_uid="dash-1").first()
    assert row is not None
    assert row.visibility == "private"
    assert len(row.shared_groups or []) == 0
