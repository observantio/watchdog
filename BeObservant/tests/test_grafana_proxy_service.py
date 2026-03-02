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
from models.access.auth_models import Permission
from services.grafana import proxy_auth_ops

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost/testdb')
os.environ.setdefault('CORS_ALLOW_CREDENTIALS', 'False')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost')

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


import types

gf_mod = types.ModuleType("services.grafana.grafana_service")
class _LocalGrafanaAPIError(Exception):
    def __init__(self, status: int, body=None):
        self.status = status
        self.body = body
gf_mod.GrafanaAPIError = _LocalGrafanaAPIError 
gf_mod.GrafanaService = lambda *a, **k: None  
sys.modules["services.grafana_service"] = gf_mod
sys.modules["services.grafana.grafana_service"] = gf_mod

pa_mod = types.ModuleType("services.grafana.proxy_auth_ops")

pa_mod = types.ModuleType("services.grafana.proxy_auth_ops")
def _is_admin_user(self, token_data):
    return False
def _is_resource_accessible(self, resource, token_data):
    return True
def _extract_dashboard_uid(self, path):
    return None
def _extract_datasource_uid(self, path):
    return None
def _extract_datasource_id(self, path):
    return None
def _extract_proxy_token(self, request, token=None):
    return token
async def _authorize_proxy_request(self, request, db, auth_service, token, orig):
    return {}

def _required_permissions_for_path(path, method):
    return ["read:dashboards"]

pa_mod.is_admin_user = _is_admin_user  
pa_mod.is_resource_accessible = _is_resource_accessible  
pa_mod.extract_dashboard_uid = _extract_dashboard_uid  
pa_mod.extract_datasource_uid = _extract_datasource_uid  
pa_mod.extract_datasource_id = _extract_datasource_id  
pa_mod.extract_proxy_token = _extract_proxy_token  
pa_mod.authorize_proxy_request = _authorize_proxy_request  
pa_mod._required_permissions_for_path = _required_permissions_for_path  
sys.modules["services.grafana.proxy_auth_ops"] = pa_mod

do_mod = types.ModuleType("services.grafana.dashboard_ops")
for name in (
    "check_dashboard_access",
    "get_accessible_dashboard_uids",
    "build_dashboard_search_context",
    "search_dashboards",
    "get_dashboard",
    "create_dashboard",
    "update_dashboard",
    "delete_dashboard",
    "toggle_dashboard_hidden",
    "get_dashboard_metadata",
):
    setattr(do_mod, name, lambda *a, **k: None)
sys.modules["services.grafana.dashboard_ops"] = do_mod

ds_mod = types.ModuleType("services.grafana.datasource_ops")
for name in (
    "check_datasource_access",
    "check_datasource_access_by_id",
    "get_accessible_datasource_uids",
    "build_datasource_list_context",
    "enforce_datasource_query_access",
    "get_datasources",
    "get_datasource",
    "get_datasource_by_name",
    "query_datasource",
    "create_datasource",
    "update_datasource",
    "delete_datasource",
    "toggle_datasource_hidden",
    "get_datasource_metadata",
):
    setattr(ds_mod, name, lambda *a, **k: None)
sys.modules["services.grafana.datasource_ops"] = ds_mod

from services.grafana_proxy_service import GrafanaProxyService
from db_models import Base, Group
from fastapi import HTTPException
GrafanaAPIError = gf_mod.GrafanaAPIError


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


def test_required_permissions_for_rotate_path():
    perms = proxy_auth_ops._required_permissions_for_path("/grafana/api/user/auth-tokens/rotate", "POST")
    # should at least return a sequence
    assert isinstance(perms, (list, set, tuple))
    perms2 = proxy_auth_ops._required_permissions_for_path("/grafana/api/user/auth-tokens/rotate", "GET")
    assert isinstance(perms2, (list, set, tuple))
