"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import os
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/observantio_test')
os.environ.setdefault('CORS_ALLOW_CREDENTIALS', 'False')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost')

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.grafana import proxy_auth_ops
from services.grafana.grafana_service import GrafanaAPIError
from services.grafana_proxy_service import GrafanaProxyService
from db_models import Base, Group, Tenant, User
from fastapi import HTTPException


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_raise_http_from_grafana_error_prefers_message_key():
    svc = GrafanaProxyService()
    gae = GrafanaAPIError(404, {"message": "not found"})
    with pytest.raises(HTTPException) as exc:
        svc._raise_http_from_grafana_error(gae)
    assert exc.value.status_code == 404
    assert exc.value.detail == "not found"


def test_raise_http_from_grafana_error_uses_error_or_detail_keys():
    svc = GrafanaProxyService()
    gae = GrafanaAPIError(400, {"error": "bad"})
    with pytest.raises(HTTPException) as exc:
        svc._raise_http_from_grafana_error(gae)
    assert exc.value.status_code == 400
    assert exc.value.detail == "bad"

    gae2 = GrafanaAPIError(422, {"detail": "invalid"})
    with pytest.raises(HTTPException) as exc2:
        svc._raise_http_from_grafana_error(gae2)
    assert exc2.value.status_code == 422
    assert exc2.value.detail == "invalid"


def test_raise_http_from_grafana_error_with_string_body_and_non_error_status():
    svc = GrafanaProxyService()
    gae = GrafanaAPIError(300, "weird")
    with pytest.raises(HTTPException) as exc:
        svc._raise_http_from_grafana_error(gae)
    assert exc.value.status_code == 500
    assert exc.value.detail == "weird"


def test_validate_group_visibility_no_groups_raises():
    db = make_session()
    svc = GrafanaProxyService()
    with pytest.raises(HTTPException) as exc:
        svc._validate_group_visibility(db, tenant_id="t1", group_ids=["g1"], shared_group_ids=None, is_admin=False)
    assert exc.value.status_code == 400
    assert "No groups provided" in str(exc.value.detail)


def test_validate_group_visibility_missing_ids_raises():
    db = make_session()

    g1 = Group(id="g1", tenant_id="t1", name="one")
    db.add(g1)
    db.commit()

    svc = GrafanaProxyService()
    with pytest.raises(HTTPException) as exc:
        svc._validate_group_visibility(db, tenant_id="t1", group_ids=["g1"], shared_group_ids=["g1", "g2"], is_admin=True)
    assert exc.value.status_code == 400
    assert "One or more group ids are invalid" in exc.value.detail



def test_validate_group_visibility_non_admin_not_member_raises():
    db = make_session()
    g1 = Group(id="g1", tenant_id="t1", name="one")
    g2 = Group(id="g2", tenant_id="t1", name="two")
    db.add_all([g1, g2])
    db.commit()

    svc = GrafanaProxyService()
    with pytest.raises(HTTPException) as exc:
        svc._validate_group_visibility(db, tenant_id="t1", group_ids=["g1"], shared_group_ids=["g1", "g2"], is_admin=False)
    assert exc.value.status_code == 403
    assert "User is not a member of one or more specified groups" in exc.value.detail


def test_validate_group_visibility_success_for_admin_and_member():
    db = make_session()
    g1 = Group(id="g1", tenant_id="t1", name="one")
    g2 = Group(id="g2", tenant_id="t1", name="two")
    db.add_all([g1, g2])
    db.commit()

    svc = GrafanaProxyService()
    groups = svc._validate_group_visibility(db, tenant_id="t1", group_ids=[], shared_group_ids=["g1", "g2"], is_admin=True)
    assert {g.id for g in groups} == {"g1", "g2"}

    groups2 = svc._validate_group_visibility(db, tenant_id="t1", group_ids=["g1", "g2"], shared_group_ids=["g1", "g2"], is_admin=False)
    assert {g.id for g in groups2} == {"g1", "g2"}


def test_validate_group_visibility_uses_live_db_membership_when_user_id_provided():
    db = make_session()
    db.add(Tenant(id="t1", name="tenant-1", display_name="Tenant 1"))
    user = User(
        id="u1",
        tenant_id="t1",
        username="user1",
        email="u1@example.com",
        hashed_password="x",
        org_id="org-a",
        is_active=True,
    )
    g1 = Group(id="g1", tenant_id="t1", name="one")
    g1.members.append(user)
    db.add_all([user, g1])
    db.commit()

    svc = GrafanaProxyService()
    groups = svc._validate_group_visibility(
        db,
        user_id="u1",
        tenant_id="t1",
        group_ids=[],
        shared_group_ids=["g1"],
        is_admin=False,
    )
    assert {g.id for g in groups} == {"g1"}


def test_validate_group_visibility_denies_when_live_membership_removed_even_with_stale_group_ids():
    db = make_session()
    db.add(Tenant(id="t1", name="tenant-1", display_name="Tenant 1"))
    user = User(
        id="u1",
        tenant_id="t1",
        username="user1",
        email="u1@example.com",
        hashed_password="x",
        org_id="org-a",
        is_active=True,
    )
    g1 = Group(id="g1", tenant_id="t1", name="one")
    db.add_all([user, g1])
    db.commit()

    svc = GrafanaProxyService()
    with pytest.raises(HTTPException) as exc:
        svc._validate_group_visibility(
            db,
            user_id="u1",
            tenant_id="t1",
            group_ids=["g1"],
            shared_group_ids=["g1"],
            is_admin=False,
        )
    assert exc.value.status_code == 403
    assert "User is not a member of one or more specified groups" in exc.value.detail


def test_required_permissions_for_rotate_path():
    perms = proxy_auth_ops._required_permissions_for_path("/grafana/api/user/auth-tokens/rotate", "POST")
    # should at least return a sequence
    assert isinstance(perms, (list, set, tuple))
    perms2 = proxy_auth_ops._required_permissions_for_path("/grafana/api/user/auth-tokens/rotate", "GET")
    assert isinstance(perms2, (list, set, tuple))
