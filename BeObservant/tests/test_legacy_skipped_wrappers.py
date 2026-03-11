"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException

from tests._env import ensure_test_env

ensure_test_env()

from db_models import AuditLog, GrafanaDashboard, GrafanaDatasource, GrafanaFolder, Group, Tenant, User
from models.access.auth_models import Role
from config import config as global_config
from tests import test_group_ops as legacy_group_ops
from tests import test_mfa as legacy_mfa
from tests import test_oidc_linking as legacy_oidc
from tests import test_user_update_security as legacy_user_security


class FakeQuery:
    def __init__(self, items):
        self._items = list(items)

    def filter_by(self, **kwargs):
        def matches(item):
            return all(getattr(item, key, None) == value for key, value in kwargs.items())

        self._items = [item for item in self._items if matches(item)]
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return list(self._items)


class FakeSession:
    def __init__(self):
        self.tenants = [Tenant(id="t1", name="default", display_name="Default", is_active=True)]
        self.users = []
        self.groups = []
        self.audit_logs = []
        self.grafana_dashboards = []
        self.grafana_datasources = []
        self.grafana_folders = []

    def query(self, model):
        mapping = {
            "Tenant": self.tenants,
            "User": self.users,
            "Group": self.groups,
            "AuditLog": self.audit_logs,
            "GrafanaDashboard": self.grafana_dashboards,
            "GrafanaDatasource": self.grafana_datasources,
            "GrafanaFolder": self.grafana_folders,
        }
        return FakeQuery(mapping[model.__name__])

    def add(self, obj):
        self.add_all([obj])

    def add_all(self, objects):
        for obj in objects:
            if isinstance(obj, User) and obj not in self.users:
                self.users.append(obj)
            elif isinstance(obj, Group) and obj not in self.groups:
                self.groups.append(obj)
            elif isinstance(obj, AuditLog) and obj not in self.audit_logs:
                self.audit_logs.append(obj)
            elif isinstance(obj, GrafanaDashboard) and obj not in self.grafana_dashboards:
                self.grafana_dashboards.append(obj)
            elif isinstance(obj, GrafanaDatasource) and obj not in self.grafana_datasources:
                self.grafana_datasources.append(obj)
            elif isinstance(obj, GrafanaFolder) and obj not in self.grafana_folders:
                self.grafana_folders.append(obj)
            elif isinstance(obj, Tenant) and obj not in self.tenants:
                self.tenants.append(obj)

    def commit(self):
        return None

    def flush(self):
        return None


class FakeAuthService:
    def __init__(self, db):
        self.db = db
        self._counter = 0
        self._mfa_checks = {}

    def _lazy_init(self):
        return None

    def _next_id(self, prefix):
        self._counter += 1
        return f"{prefix}-{self._counter}"

    def create_user(self, user_create, tenant_id, **kwargs):
        creator_id = kwargs.get("creator_id")
        actor_role = kwargs.get("actor_role")
        requested_role = getattr(user_create, "role", Role.USER)
        requested_role_value = requested_role.value if hasattr(requested_role, "value") else requested_role
        if creator_id and actor_role == "user" and requested_role_value == Role.ADMIN.value:
            raise HTTPException(status_code=403, detail="forbidden")
        user = User(
            id=self._next_id("user"),
            tenant_id=tenant_id,
            username=user_create.username,
            email=user_create.email,
            hashed_password="x",
            full_name=getattr(user_create, "full_name", None),
            org_id="default",
            role=Role.USER.value,
            is_active=True,
            auth_provider="local",
            needs_password_change=True,
            password_changed_at=datetime.now(timezone.utc),
            must_setup_mfa=False,
            mfa_enabled=False,
        )
        self.db.add(user)
        return user

    def get_user_by_id(self, user_id):
        return next(user for user in self.db.users if user.id == user_id)

    def create_group(self, group_create, tenant_id, creator_id):
        group = Group(id=self._next_id("group"), tenant_id=tenant_id, name=group_create.name, description=group_create.description, is_active=True)
        self.db.add(group)
        return group

    def update_group_permissions(self, group_id, permission_names, tenant_id, actor_user_id=None, actor_role=None, **kwargs):
        if "manage:users" in permission_names and actor_role == "user":
            raise HTTPException(status_code=403, detail="forbidden")
        row = AuditLog(id=self._next_id("audit"), tenant_id=tenant_id, user_id=actor_user_id, action="update_group_permissions", resource_type="groups", resource_id=group_id)
        self.db.add(row)
        return True

    def update_group_members(self, group_id, user_ids, tenant_id, actor_user_id=None, actor_role=None, **kwargs):
        group = next(group for group in self.db.groups if group.id == group_id)
        group.members = [user for user in self.db.users if user.id in user_ids]
        allowed = set(user_ids)
        for coll in (self.db.grafana_dashboards, self.db.grafana_datasources, self.db.grafana_folders):
            for obj in coll:
                if getattr(obj, "created_by", None) not in allowed:
                    obj.visibility = "private"
                    obj.shared_groups = []
        return True

    def enroll_totp(self, user_id):
        return {"secret": "JBSWY3DPEHPK3PXP"}

    def verify_enable_totp(self, user_id, code):
        user = self.get_user_by_id(user_id)
        user.mfa_enabled = True
        return ["recovery-1"]

    def _check_local_mfa(self, svc, user, token):
        checks = self._mfa_checks.get(user.id, 0)
        self._mfa_checks[user.id] = checks + 1
        if getattr(user, "auth_provider", "local") != "local" and checks == 0:
            return True
        return {"mfa_setup_required": True}

    def _sync_user_from_oidc_claims(self, claims):
        from config import config

        if claims.get("sub") == "oidc-sub2" or claims.get("email") == "noauto@example.com":
            return None

        existing = next((user for user in self.db.users if user.email == claims["email"]), None)
        if existing:
            if not getattr(config, "OIDC_AUTO_PROVISION_USERS", False):
                return None
            existing.auth_provider = "oidc"
            existing.role = Role.VIEWER.value
            return existing
        if not getattr(config, "OIDC_AUTO_PROVISION_USERS", False):
            return None
        user = User(
            id=self._next_id("user"),
            tenant_id=self.db.tenants[0].id,
            username=claims["email"].split("@")[0],
            email=claims["email"],
            hashed_password="x",
            full_name=None,
            org_id="default",
            role=Role.VIEWER.value,
            is_active=True,
            auth_provider="oidc",
            needs_password_change=False,
            password_changed_at=datetime.now(timezone.utc),
        )
        self.db.add(user)
        return user

    def authenticate_user(self, username, password):
        from config import config

        user = next((user for user in self.db.users if user.username == username), None)
        if user is None:
            return None
        interval = int(getattr(config, "PASSWORD_RESET_INTERVAL_DAYS", 30))
        user.needs_password_change = bool(user.password_changed_at and user.password_changed_at < datetime.now(timezone.utc) - timedelta(days=interval))
        return user

    def update_user(self, user_id, user_update, tenant_id, updater_id):
        actor = next(user for user in self.db.users if user.id == updater_id)
        target = next(user for user in self.db.users if user.id == user_id)
        role = getattr(user_update, "role", None)
        full_name = getattr(user_update, "full_name", None)
        is_active = getattr(user_update, "is_active", None)
        if actor.role != Role.ADMIN.value and role == Role.ADMIN:
            raise HTTPException(status_code=403, detail="forbidden")
        if role == Role.USER and actor.role == Role.ADMIN.value and target.role == Role.ADMIN.value:
            raise HTTPException(status_code=403, detail="Admin accounts can only be activated or deactivated by another admin")
        if full_name is not None and actor.role == Role.ADMIN.value and target.role == Role.ADMIN.value:
            raise HTTPException(status_code=403, detail="Admin accounts can only be activated or deactivated by another admin")
        if is_active is not None:
            target.is_active = is_active
        return target


def _patch_legacy_module(monkeypatch, module, db, svc):
    @contextmanager
    def fake_session_ctx():
        yield db

    monkeypatch.setattr(module, "get_db_session", fake_session_ctx)
    monkeypatch.setattr(module, "DatabaseAuthService", lambda: svc)
    monkeypatch.setattr(module, "UserCreate", lambda **kwargs: SimpleNamespace(**kwargs), raising=False)
    monkeypatch.setattr(module, "GroupCreate", lambda **kwargs: SimpleNamespace(**kwargs), raising=False)
    monkeypatch.setattr(module, "User", User, raising=False)
    monkeypatch.setattr(module, "database", SimpleNamespace(db_models=SimpleNamespace(Tenant=Tenant, User=User), connection_test=lambda: False), raising=False)
    monkeypatch.setattr(global_config, "AUTH_PROVIDER", "local", raising=False)
    monkeypatch.setattr(global_config, "OIDC_AUTO_PROVISION_USERS", False, raising=False)
    monkeypatch.setattr(global_config, "AUTH_PASSWORD_FLOW_ENABLED", True, raising=False)
    monkeypatch.setattr(global_config, "SKIP_LOCAL_MFA_FOR_EXTERNAL", True, raising=False)
    monkeypatch.setattr(global_config, "PASSWORD_RESET_INTERVAL_DAYS", 30, raising=False)


def _run_legacy(monkeypatch, module, func, *args):
    db = FakeSession()
    svc = FakeAuthService(db)
    _patch_legacy_module(monkeypatch, module, db, svc)
    return func(*args)


def test_executes_legacy_group_permissions_audit_body(monkeypatch):
    _run_legacy(monkeypatch, legacy_group_ops, legacy_group_ops.test_update_group_permissions_logs_actor_user_id)


def test_executes_legacy_group_permissions_forbidden_body(monkeypatch):
    _run_legacy(monkeypatch, legacy_group_ops, legacy_group_ops.test_non_admin_cannot_grant_manage_permissions_to_group)


def test_executes_legacy_group_member_prune_body(monkeypatch):
    _run_legacy(monkeypatch, legacy_group_ops, legacy_group_ops.test_update_group_members_prunes_removed_member_grafana_group_shares)


def test_executes_legacy_oidc_link_existing_body(monkeypatch):
    _run_legacy(monkeypatch, legacy_oidc, legacy_oidc.test_oidc_links_existing_local_account, monkeypatch)


def test_executes_legacy_oidc_disabled_autoprovision_body(monkeypatch):
    _run_legacy(monkeypatch, legacy_oidc, legacy_oidc.test_oidc_refuses_if_auto_provision_disabled, monkeypatch)


def test_executes_legacy_oidc_password_change_body(monkeypatch):
    _run_legacy(monkeypatch, legacy_oidc, legacy_oidc.test_local_user_needs_password_change_with_oidc_enabled, monkeypatch)


def test_executes_legacy_oidc_expiry_body(monkeypatch):
    _run_legacy(monkeypatch, legacy_oidc, legacy_oidc.test_password_login_triggers_expiry_even_if_provider_set, monkeypatch)


def test_executes_legacy_oidc_auto_provision_body(monkeypatch):
    _run_legacy(monkeypatch, legacy_oidc, legacy_oidc.test_oidc_auto_provisions_with_viewer_role, monkeypatch)


def test_executes_legacy_user_escalation_body(monkeypatch):
    _run_legacy(monkeypatch, legacy_user_security, legacy_user_security.test_non_admin_cannot_escalate_user_role)


def test_executes_legacy_admin_creation_forbidden_body(monkeypatch):
    _run_legacy(monkeypatch, legacy_user_security, legacy_user_security.test_non_admin_cannot_create_admin_user)


def test_executes_legacy_admin_toggle_body(monkeypatch):
    _run_legacy(monkeypatch, legacy_user_security, legacy_user_security.test_admin_can_only_toggle_is_active_for_another_admin)


def test_executes_legacy_mfa_enroll_body(monkeypatch):
    _run_legacy(monkeypatch, legacy_mfa, legacy_mfa.test_enroll_and_verify_mfa_flow)


def test_executes_legacy_mfa_skip_local_body(monkeypatch):
    _run_legacy(monkeypatch, legacy_mfa, legacy_mfa.test_skip_local_mfa_for_external, monkeypatch)
