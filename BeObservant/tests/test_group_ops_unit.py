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
from models.access.group_models import GroupCreate, GroupUpdate
from services.auth import group_ops


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _service() -> SimpleNamespace:
    return SimpleNamespace(
        _to_group_schema=lambda group: group,
        _log_audit=lambda *args, **kwargs: None,
        _collect_permissions=lambda actor: [],
    )


def _seed(db):
    tenant = Tenant(id="t1", name="tenant-1", display_name="Tenant 1", is_active=True)
    admin = User(id="u-admin", tenant_id="t1", username="admin", email="admin@example.com", hashed_password="x", org_id="org", role="admin", is_active=True)
    member = User(id="u-member", tenant_id="t1", username="member", email="member@example.com", hashed_password="x", org_id="org", role="user", is_active=True)
    other = User(id="u-other", tenant_id="t1", username="other", email="other@example.com", hashed_password="x", org_id="org", role="viewer", is_active=True)
    db.add_all([tenant, admin, member, other])
    db.commit()
    return admin, member, other


def test_group_helper_functions_and_access_rules(monkeypatch):
    db = _session()
    admin, member, other = _seed(db)
    group = Group(id="g1", tenant_id="t1", name="Ops", is_active=True)
    group.members.append(member)
    db.add(group)
    db.commit()

    assert group_ops._role_rank("admin") > group_ops._role_rank("viewer")
    assert group_ops._load_usernames_for_ids(db, tenant_id="t1", user_ids=[member.id, " "]) == [member.username]
    assert group_ops._load_usernames_for_ids(db, tenant_id="t1", user_ids=[]) == []
    assert group_ops._can_access_group(group, actor_user_id=None, actor_role="user", actor_is_superuser=False) is False
    assert group_ops._can_access_group(group, actor_user_id=member.id, actor_role="user", actor_is_superuser=False) is True
    assert group_ops._can_access_group(group, actor_user_id=other.id, actor_role="admin", actor_is_superuser=False) is True

    with pytest.raises(HTTPException, match="higher than your own"):
        group_ops._enforce_permission_delegation(
            requested_permissions={"manage:users"},
            actor_permissions={"read:users"},
            actor_role="user",
            actor_is_superuser=False,
        )

    calls = []
    monkeypatch.setattr(group_ops, "_prune_removed_member_benotified_group_shares", lambda **kwargs: (_ for _ in ()).throw(HTTPException(status_code=502, detail="boom")))
    monkeypatch.setattr(group_ops.logger, "warning", lambda *args, **kwargs: calls.append(args))
    group_ops._propagate_removed_member_group_shares(tenant_id="t1", group_id="g1", removed_user_ids=[member.id])
    assert calls


def test_create_list_get_update_and_delete_group(monkeypatch):
    db = _session()
    admin, member, other = _seed(db)

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(group_ops, "get_db_session", fake_session)
    service = _service()

    with pytest.raises(ValueError, match="required"):
        group_ops.create_group(service, GroupCreate(name=" ", description=None), "t1", creator_id=admin.id)

    created = group_ops.create_group(service, GroupCreate(name="Ops", description="desc"), "t1", creator_id=admin.id)
    assert created.name == "Ops"
    created_group = db.query(Group).filter_by(name="Ops").first()
    assert {user.id for user in created_group.members} == {admin.id}

    with pytest.raises(ValueError, match="already exists"):
        group_ops.create_group(service, GroupCreate(name="ops", description=None), "t1", creator_id=admin.id)

    assert len(group_ops.list_groups(service, "t1", actor_user_id=admin.id, actor_role="admin")) == 1
    assert group_ops.list_groups(service, "t1", actor_user_id=None, actor_role="user") == []
    assert group_ops.get_group(service, created_group.id, "t1", actor_user_id=other.id, actor_role="user") is None
    assert group_ops.get_group(service, created_group.id, "t1", actor_user_id=admin.id, actor_role="admin").id == created_group.id

    assert group_ops.update_group(service, "missing", GroupUpdate(name="x"), "t1", updater_id=admin.id) is None
    with pytest.raises(HTTPException, match="Not allowed"):
        group_ops.update_group(service, created_group.id, GroupUpdate(description="x"), "t1", updater_id=other.id, actor_role="user")
    with pytest.raises(ValueError, match="cannot be empty"):
        group_ops.update_group(service, created_group.id, GroupUpdate(name=" "), "t1", updater_id=admin.id, actor_role="admin")
    updated = group_ops.update_group(service, created_group.id, GroupUpdate(name="Ops2", is_active=False), "t1", updater_id=admin.id, actor_role="admin")
    assert updated.name == "Ops2"
    assert updated.is_active is False

    assert group_ops.delete_group(service, "missing", "t1", deleter_id=admin.id, actor_role="admin") is False
    with pytest.raises(HTTPException, match="Not allowed"):
        group_ops.delete_group(service, created_group.id, "t1", deleter_id=other.id, actor_role="user")
    assert group_ops.delete_group(service, created_group.id, "t1", deleter_id=admin.id, actor_role="admin") is True


def test_group_permission_and_member_updates(monkeypatch):
    db = _session()
    admin, member, other = _seed(db)
    perm = Permission(id="p1", name="read:users", display_name="Read Users", resource_type="users", action="read")
    admin_perm = Permission(id="p2", name="manage:users", display_name="Manage Users", resource_type="users", action="manage")
    group = Group(id="g1", tenant_id="t1", name="Ops", is_active=True)
    group.members.extend([admin, member])
    db.add_all([perm, admin_perm, group])
    db.commit()

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(group_ops, "get_db_session", fake_session)
    monkeypatch.setattr(group_ops, "_propagate_removed_member_group_shares", lambda **kwargs: None)
    service = _service()

    with pytest.raises(HTTPException, match="Actor context is required"):
        group_ops.update_group_permissions(service, group.id, [], "t1", actor_user_id=None)

    with pytest.raises(HTTPException, match="Missing permission"):
        group_ops.update_group_permissions(service, group.id, [perm.name], "t1", actor_user_id=member.id, actor_role="user", actor_permissions=[])

    with pytest.raises(HTTPException, match="higher than your own"):
        group_ops.update_group_permissions(service, group.id, ["unknown:perm"], "t1", actor_user_id=admin.id, actor_role="admin")

    assert group_ops.update_group_permissions(service, group.id, [perm.name], "t1", actor_user_id=admin.id, actor_role="admin", actor_permissions=[perm.name]) is True
    assert {permission.name for permission in db.query(Group).filter_by(id=group.id).first().permissions} == {perm.name}

    with pytest.raises(HTTPException, match="Missing permission"):
        group_ops.update_group_members(service, group.id, [member.id], "t1", actor_user_id=member.id, actor_role="user", actor_permissions=[])

    with pytest.raises(ValueError, match="Users not found"):
        group_ops.update_group_members(service, group.id, ["missing"], "t1", actor_user_id=admin.id, actor_role="admin")

    with pytest.raises(HTTPException, match="admin users"):
        group_ops.update_group_members(service, group.id, [admin.id], "t1", actor_user_id=member.id, actor_role="user", actor_permissions=["update:group_members"])

    assert group_ops.update_group_members(service, group.id, [member.id], "t1", actor_user_id=admin.id, actor_role="admin") is True
    assert {user.id for user in db.query(Group).filter_by(id=group.id).first().members} == {member.id}

    assert group_ops.update_group_members(service, group.id, [], "t1", actor_user_id=admin.id, actor_role="admin") is True
    assert db.query(Group).filter_by(id=group.id).first() is None


def test_benotified_prune_http_branches(monkeypatch):
    monkeypatch.setattr(group_ops.config, "BENOTIFIED_URL", "")
    monkeypatch.setattr(group_ops.config, "get_secret", lambda key: None)
    group_ops._prune_removed_member_benotified_group_shares(tenant_id="t1", group_id="g1", removed_user_ids=["u1"])

    monkeypatch.setattr(group_ops.config, "BENOTIFIED_URL", "https://notify")
    monkeypatch.setattr(group_ops.config, "BENOTIFIED_TIMEOUT_SECONDS", 2)
    monkeypatch.setattr(group_ops.config, "get_secret", lambda key: "svc-token")

    class ResponseStub:
        def __init__(self, status_code):
            self.status_code = status_code

    class ClientStub:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            return ResponseStub(502)

    monkeypatch.setattr(group_ops.httpx, "Client", ClientStub)
    with pytest.raises(HTTPException, match="Failed to propagate"):
        group_ops._prune_removed_member_benotified_group_shares(tenant_id="t1", group_id="g1", removed_user_ids=["u1"])
