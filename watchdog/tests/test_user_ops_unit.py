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

from db_models import Base, Group, Permission, Tenant, User
from models.access.auth_models import Role
from models.access.user_models import UserCreate, UserUpdate
from services.auth import user_ops


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _service(external=False):
    ensured = []
    audits = []

    def _to_user_schema(user):
        return user

    def _collect_permissions(actor):
        direct = {permission.name for permission in getattr(actor, "permissions", [])}
        group_perms = {
            permission.name
            for group in getattr(actor, "groups", [])
            for permission in getattr(group, "permissions", [])
        }
        return sorted(direct | group_perms)

    return SimpleNamespace(
        _lazy_init=lambda: None,
        _to_user_schema=_to_user_schema,
        hash_password=lambda value: f"hashed:{value}",
        is_external_auth_enabled=lambda: external,
        provision_external_user=lambda **kwargs: "ext-subject",
        _ensure_default_api_key=lambda db, user: ensured.append(user.id),
        _log_audit=lambda *args, **kwargs: audits.append((args, kwargs)),
        _collect_permissions=_collect_permissions,
        ensured=ensured,
        audits=audits,
    )


def _seed(db):
    tenant = Tenant(id="t1", name="tenant-1", display_name="Tenant 1", is_active=True)
    admin = User(id="u-admin", tenant_id="t1", username="admin", email="admin@example.com", hashed_password="x", org_id="org", role="admin", is_active=True)
    user = User(id="u-user", tenant_id="t1", username="user", email="user@example.com", hashed_password="x", org_id="org", role="user", is_active=True)
    viewer = User(id="u-viewer", tenant_id="t1", username="viewer", email="viewer@example.com", hashed_password="x", org_id="org", role="viewer", is_active=True)
    external = User(id="u-ext", tenant_id="t1", username="external", email="external@example.com", hashed_password="x", org_id="org", role="user", is_active=True, auth_provider="oidc")
    group = Group(id="g1", tenant_id="t1", name="Ops", is_active=True)
    perm = Permission(id="p1", name="read:users", display_name="Read Users", resource_type="users", action="read")
    admin_perm = Permission(id="p2", name="manage:users", display_name="Manage Users", resource_type="users", action="manage")
    db.add_all([tenant, admin, user, viewer, external, group, perm, admin_perm])
    db.commit()
    return admin, user, viewer, external, group, perm, admin_perm


def test_user_ops_helpers_and_getters(monkeypatch):
    db = _session()
    admin, user, viewer, external, group, perm, admin_perm = _seed(db)
    service = _service()

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(user_ops, "get_db_session", fake_session)

    assert user_ops._role_rank(Role.ADMIN) > user_ops._role_rank(Role.VIEWER)
    assert user_ops._role_default_permissions("missing") == set()
    assert user_ops.get_user_by_id(service, "", tenant_id="t1", db=db) is None
    assert user_ops.get_user_by_id(service, admin.id, tenant_id="t1", db=db).id == admin.id
    assert user_ops.get_user_by_username(service, " ADMIN ").id == admin.id
    assert user_ops.get_user_by_username(service, "missing") is None
    assert user_ops.list_users(service, "t1", limit=1, offset=0)[0].id in {admin.id, user.id, viewer.id, external.id}
    with pytest.raises(ValueError, match="integers"):
        user_ops.list_users(service, "t1", limit="bad")


def test_create_user_policy_and_external_branches(monkeypatch):
    db = _session()
    admin, user, viewer, external_user, group, perm, admin_perm = _seed(db)

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(user_ops, "get_db_session", fake_session)
    monkeypatch.setattr(user_ops.config, "DEFAULT_ORG_ID", "default-org")
    monkeypatch.setattr(user_ops.config, "AUTH_PROVIDER", "oidc")
    monkeypatch.setattr(user_ops.config, "KEYCLOAK_USER_PROVISIONING_ENABLED", True)

    service = _service()
    external_service = _service(external=True)

    created = user_ops.create_user(service, UserCreate(username="newuser", email="new@example.com", password="password1", full_name="New User", org_id="default-org"), "t1", creator_id=admin.id, actor_role="admin")
    assert created.username == "newuser"
    assert service.ensured

    with pytest.raises(HTTPException, match="Creator account"):
        user_ops.create_user(service, UserCreate(username="badcreator", email="badcreator@example.com", password="password1", full_name="Bad Creator", org_id="default-org"), "t1", creator_id="missing")

    with pytest.raises(HTTPException, match="higher than your own"):
        user_ops.create_user(service, UserCreate(username="rolehigh", email="rolehigh@example.com", password="password1", full_name="Role High", role=Role.ADMIN, org_id="default-org"), "t1", creator_id=user.id, actor_role="user")

    with pytest.raises(HTTPException, match="initial group memberships"):
        user_ops.create_user(service, UserCreate(username="grouped", email="grouped@example.com", password="password1", full_name="Grouped", group_ids=[group.id], org_id="default-org"), "t1", creator_id=user.id, actor_role="user")

    with pytest.raises(HTTPException, match="tenant scope"):
        user_ops.create_user(service, UserCreate(username="scoped", email="scoped@example.com", password="password1", full_name="Scoped", org_id="other-org"), "t1", creator_id=user.id, actor_role="user")

    with pytest.raises(ValueError, match="Username already exists"):
        user_ops.create_user(service, UserCreate(username="ADMIN", email="dupname@example.com", password="password1", full_name="Dup", org_id="default-org"), "t1", creator_id=admin.id, actor_role="admin")
    with pytest.raises(ValueError, match="Email already exists"):
        user_ops.create_user(service, UserCreate(username="dupemail", email="ADMIN@example.com", password="password1", full_name="Dup", org_id="default-org"), "t1", creator_id=admin.id, actor_role="admin")
    with pytest.raises(ValueError, match="Password is required"):
        user_ops.create_user(service, UserCreate.model_construct(username="nopw", email="nopw@example.com", password="", full_name="No Pw", org_id="default-org", role=Role.USER, group_ids=[], is_active=True, must_setup_mfa=False), "t1", creator_id=admin.id, actor_role="admin")

    created_external = user_ops.create_user(external_service, UserCreate.model_construct(username="externalnew", email="externalnew@example.com", password="", full_name="External New", org_id="default-org", role=Role.USER, group_ids=[], is_active=True, must_setup_mfa=False), "t1", creator_id=admin.id, actor_role="admin")
    assert created_external.auth_provider == "oidc"
    assert db.query(User).filter_by(username="externalnew").first().external_subject == "ext-subject"

    failing_external = _service(external=True)
    failing_external.provision_external_user = lambda **kwargs: None
    with pytest.raises(ValueError, match="provisioning failed"):
        user_ops.create_user(failing_external, UserCreate.model_construct(username="externalfail", email="externalfail@example.com", password="", full_name="External Fail", org_id="default-org", role=Role.USER, group_ids=[], is_active=True, must_setup_mfa=False), "t1", creator_id=admin.id, actor_role="admin")


def test_update_user_and_delete_user_paths(monkeypatch):
    db = _session()
    admin, user, viewer, external_user, group, perm, admin_perm = _seed(db)
    group.members.append(user)
    db.commit()

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(user_ops, "get_db_session", fake_session)
    prune_calls = []
    propagate_calls = []
    monkeypatch.setattr(user_ops, "_prune_removed_member_grafana_group_shares", lambda *args, **kwargs: prune_calls.append((args, kwargs)))
    monkeypatch.setattr(user_ops, "_propagate_removed_member_group_shares", lambda **kwargs: propagate_calls.append(kwargs))
    service = _service()

    assert user_ops.update_user(service, "missing", UserUpdate(full_name="x"), "t1", updater_id=admin.id) is None

    with pytest.raises(HTTPException, match="disable your own"):
        user_ops.update_user(service, user.id, UserUpdate(is_active=False), "t1", updater_id=user.id)
    with pytest.raises(HTTPException, match="cannot change their own role"):
        user_ops.update_user(service, user.id, UserUpdate(role=Role.ADMIN), "t1", updater_id=user.id)

    with pytest.raises(HTTPException, match="Only administrators can modify admin accounts"):
        user_ops.update_user(service, admin.id, UserUpdate(full_name="x"), "t1", updater_id=user.id)

    with pytest.raises(HTTPException, match="Email is managed"):
        user_ops.update_user(service, external_user.id, UserUpdate(email="new@example.com"), "t1", updater_id=admin.id)
    with pytest.raises(HTTPException, match="Username is required"):
        user_ops.update_user(service, user.id, UserUpdate.model_construct(username=" "), "t1", updater_id=admin.id)
    with pytest.raises(HTTPException, match="Username already exists"):
        user_ops.update_user(service, user.id, UserUpdate(username=admin.username), "t1", updater_id=admin.id)

    updated = user_ops.update_user(service, user.id, UserUpdate(username="renamed", org_id="new-org", group_ids=[]), "t1", updater_id=admin.id)
    assert updated.username == "renamed"
    assert updated.org_id == "new-org"
    assert prune_calls
    assert propagate_calls
    assert service.ensured

    with pytest.raises(ValueError, match="cannot delete their own"):
        user_ops.delete_user(service, user.id, "t1", deleter_id=user.id)
    assert user_ops.delete_user(service, "missing", "t1", deleter_id=admin.id) is False
    with pytest.raises(HTTPException, match="cannot be deleted"):
        user_ops.delete_user(service, admin.id, "t1", deleter_id=admin.id + "-other")
    assert user_ops.delete_user(service, user.id, "t1", deleter_id="missing") is False
    with pytest.raises(HTTPException, match="Only administrators can delete users"):
        user_ops.delete_user(service, external_user.id, "t1", deleter_id=viewer.id)

    target = User(id="u-target", tenant_id="t1", username="target", email="target@example.com", hashed_password="x", org_id="org", role="user", is_active=True)
    db.add(target)
    db.commit()
    assert user_ops.delete_user(service, target.id, "t1", deleter_id=admin.id) is True


def test_update_user_permissions_paths(monkeypatch):
    db = _session()
    admin, user, viewer, external_user, group, perm, admin_perm = _seed(db)
    user.permissions.append(perm)
    admin.permissions.extend([perm, admin_perm])
    db.commit()

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(user_ops, "get_db_session", fake_session)
    service = _service()

    with pytest.raises(HTTPException, match="Actor context is required"):
        user_ops.update_user_permissions(service, user.id, [], "t1", actor_user_id=None)
    assert user_ops.update_user_permissions(service, "missing", [], "t1", actor_user_id=admin.id) is False
    with pytest.raises(HTTPException, match="Actor not found"):
        user_ops.update_user_permissions(service, user.id, [], "t1", actor_user_id="missing")
    with pytest.raises(HTTPException, match="cannot change their own permissions"):
        user_ops.update_user_permissions(service, admin.id, [], "t1", actor_user_id=admin.id)

    with pytest.raises(HTTPException, match="Only administrators can modify admin permissions"):
        user_ops.update_user_permissions(service, admin.id, [perm.name], "t1", actor_user_id=user.id, actor_role="user", actor_permissions=[perm.name])

    admin.role = "user"
    db.commit()
    with pytest.raises(HTTPException, match="higher role"):
        user_ops.update_user_permissions(service, user.id, [perm.name], "t1", actor_user_id=viewer.id, actor_role="viewer", actor_permissions=[perm.name])
    admin.role = "admin"
    db.commit()

    with pytest.raises(HTTPException, match="outside your own scope"):
        user_ops.update_user_permissions(service, user.id, [admin_perm.name], "t1", actor_user_id=admin.id, actor_role="admin", actor_permissions=[perm.name])

    with pytest.raises(ValueError, match="Unknown permissions"):
        user_ops.update_user_permissions(service, user.id, [perm.name, "unknown:perm"], "t1", actor_user_id=admin.id, actor_role="admin", actor_permissions=[perm.name, admin_perm.name], actor_is_superuser=True)

    assert user_ops.update_user_permissions(service, user.id, [perm.name, admin_perm.name], "t1", actor_user_id=admin.id, actor_role="admin", actor_permissions=[perm.name, admin_perm.name]) is True
    assert {permission.name for permission in db.query(User).filter_by(id=user.id).first().permissions} == {perm.name, admin_perm.name}


def test_set_grafana_user_id(monkeypatch):
    db = _session()
    admin, user, viewer, external_user, group, perm, admin_perm = _seed(db)

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(user_ops, "get_db_session", fake_session)
    assert user_ops.set_grafana_user_id("missing", 5, "t1") is False
    assert user_ops.set_grafana_user_id(user.id, 5, "t1") is True
    assert db.query(User).filter_by(id=user.id).first().grafana_user_id == 5
