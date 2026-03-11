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

from services.auth.helper import (
    audit_key_is_sensitive,
    redact_query_string,
    sanitize_resource_id,
    sanitize_audit_details,
    require_admin_with_audit_permission,
)
from models.access.auth_models import Role
from types import SimpleNamespace


def test_audit_key_sensitive():
    assert audit_key_is_sensitive("token")
    assert audit_key_is_sensitive("Token")
    assert not audit_key_is_sensitive("status_code")
    assert not audit_key_is_sensitive("STATUS_Code")


def test_redact_query_string_empty():
    assert redact_query_string("") == ""
    assert redact_query_string(None) == ""


def test_redact_query_string_sanitizes():
    qs = "status_code=200&token=secret&code=123"
    out = redact_query_string(qs)
    assert "status_code=200" in out
    assert "token=%5BREDACTED%5D" in out
    assert "code=%5BREDACTED%5D" in out


def test_sanitize_resource_id():
    assert sanitize_resource_id("abc") == "abc"
    assert sanitize_resource_id("http://example.com?a=1&token=foo") == \
        "http://example.com?a=1&token=%5BREDACTED%5D"


def test_sanitize_audit_details():
    details = {"status_code":200, "token":"x", "query":"a=1&secret=2"}
    out = sanitize_audit_details(details)
    assert out["status_code"] == 200
    assert out["token"] == "[REDACTED]"
    assert "secret=%5BREDACTED%5D" in out["query"]


def make_user(role: str | Role = Role.USER.value, superuser=False):
    if isinstance(role, Role):
        role = role.value
    return SimpleNamespace(role=str(role), is_superuser=superuser)



def test_require_admin_permission():
    user = make_user()
    with pytest.raises(HTTPException):
        require_admin_with_audit_permission(user)
    admin = make_user(role=Role.ADMIN)
    assert require_admin_with_audit_permission(admin) is admin
    superu = make_user(superuser=True)
    assert require_admin_with_audit_permission(superu) is superu
