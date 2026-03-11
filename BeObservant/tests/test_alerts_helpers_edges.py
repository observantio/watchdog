"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Permission, Role, TokenData
from services.alerts import helpers as helpers_mod


def _user(*, permissions=None, group_ids=None, is_superuser=False) -> TokenData:
    return TokenData(
        user_id="u1",
        username="alice",
        tenant_id="tenant-a",
        org_id="tenant-a",
        role=Role.ADMIN,
        permissions=permissions or [Permission.READ_ALERTS.value],
        group_ids=group_ids or ["g1"],
        is_superuser=is_superuser,
        is_mfa_setup=False,
    )


def _request(*, headers=None) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/alertmanager",
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "query_string": b"",
    }
    return Request(scope)


def test_required_permissions_maps_routes():
    assert helpers_mod.required_permissions("alerts", "GET") == {Permission.READ_ALERTS.value}
    assert helpers_mod.required_permissions("alerts", "POST") == {
        Permission.CREATE_ALERTS.value,
        Permission.WRITE_ALERTS.value,
    }
    assert helpers_mod.required_permissions("alerts", "DELETE") == {Permission.DELETE_ALERTS.value}
    assert helpers_mod.required_permissions("incidents/123", "PATCH") == {Permission.UPDATE_INCIDENTS.value}
    assert helpers_mod.required_permissions("silences/1", "GET") == {Permission.READ_SILENCES.value}
    assert helpers_mod.required_permissions("silences", "POST") == {
        Permission.CREATE_SILENCES.value,
        Permission.WRITE_ALERTS.value,
    }
    assert helpers_mod.required_permissions("silences/1", "PUT") == {
        Permission.UPDATE_SILENCES.value,
        Permission.WRITE_ALERTS.value,
    }
    assert helpers_mod.required_permissions("silences/1", "DELETE") == {Permission.DELETE_SILENCES.value}
    assert helpers_mod.required_permissions("rules/import", "POST") == {
        Permission.CREATE_RULES.value,
        Permission.WRITE_ALERTS.value,
    }
    assert helpers_mod.required_permissions("rules", "GET") == {Permission.READ_RULES.value}
    assert helpers_mod.required_permissions("rules", "POST") == {
        Permission.CREATE_RULES.value,
        Permission.WRITE_ALERTS.value,
        Permission.TEST_RULES.value,
    }
    assert helpers_mod.required_permissions("rules", "PUT") == {
        Permission.UPDATE_RULES.value,
        Permission.WRITE_ALERTS.value,
    }
    assert helpers_mod.required_permissions("rules", "DELETE") == {Permission.DELETE_RULES.value}
    assert helpers_mod.required_permissions("channels", "GET") == {Permission.READ_CHANNELS.value}
    assert helpers_mod.required_permissions("channels", "POST") == {
        Permission.CREATE_CHANNELS.value,
        Permission.WRITE_CHANNELS.value,
        Permission.TEST_CHANNELS.value,
    }
    assert helpers_mod.required_permissions("channels", "PUT") == {
        Permission.UPDATE_CHANNELS.value,
        Permission.WRITE_CHANNELS.value,
    }
    assert helpers_mod.required_permissions("channels", "DELETE") == {Permission.DELETE_CHANNELS.value}
    assert helpers_mod.required_permissions("jira/config", "GET") == {Permission.MANAGE_TENANTS.value}
    assert helpers_mod.required_permissions("jira/issues", "GET") == {
        Permission.READ_INCIDENTS.value,
        Permission.UPDATE_INCIDENTS.value,
        Permission.READ_CHANNELS.value,
    }
    assert helpers_mod.required_permissions("jira/issues", "POST") == {Permission.UPDATE_INCIDENTS.value}
    assert helpers_mod.required_permissions("integrations/slack", "GET") == {
        Permission.READ_INCIDENTS.value,
        Permission.UPDATE_INCIDENTS.value,
        Permission.READ_CHANNELS.value,
    }
    assert helpers_mod.required_permissions("integrations/slack", "POST") == {Permission.UPDATE_INCIDENTS.value}
    assert helpers_mod.required_permissions("metrics/names", "GET") == {
        Permission.READ_METRICS.value,
        Permission.CREATE_RULES.value,
        Permission.UPDATE_RULES.value,
        Permission.WRITE_ALERTS.value,
    }
    assert helpers_mod.required_permissions("public/rules", "GET") == set()
    assert helpers_mod.required_permissions("unknown", "GET") is None


def test_permission_and_normalization_helpers():
    user = _user(permissions=[Permission.READ_ALERTS.value])
    helpers_mod.check_permissions(user, {Permission.READ_ALERTS.value})
    helpers_mod.check_permissions(_user(is_superuser=True), {Permission.DELETE_ALERTS.value})
    helpers_mod.check_permissions(user, set())
    with pytest.raises(HTTPException, match="Required permissions"):
        helpers_mod.check_permissions(user, {Permission.DELETE_ALERTS.value})

    assert helpers_mod.is_mutating("post") is True
    assert helpers_mod.is_mutating("get") is False
    assert helpers_mod.normalize_group_ids([None, " g1 ", "g1", "g2", 3]) == ["g1", "g2", "3"]
    assert helpers_mod.normalize_group_ids("bad") == []


def test_silence_meta_extraction_and_owner_checks():
    meta = helpers_mod._extract_silence_meta({helpers_mod.SILENCE_META_KEY: '{"createdBy": "u1"}'})
    assert meta == {"createdBy": "u1"}
    meta = helpers_mod._extract_silence_meta({"annotations": {helpers_mod.SILENCE_META_KEY: {"created_by": "u2"}}})
    assert meta == {"created_by": "u2"}
    assert helpers_mod._extract_silence_meta({helpers_mod.SILENCE_META_KEY: "{"}) == {}

    helpers_mod.assert_silence_owner(_user(is_superuser=True), {})
    helpers_mod.assert_silence_owner(_user(), {"created_by": "u1"})
    helpers_mod.assert_silence_owner(_user(), {"annotations": {helpers_mod.SILENCE_META_KEY: '{"createdBy": "u1"}'}})

    with pytest.raises(HTTPException, match="ownership metadata is missing"):
        helpers_mod.assert_silence_owner(_user(), {})
    with pytest.raises(HTTPException, match="only update or delete silences"):
        helpers_mod.assert_silence_owner(_user(), {"createdBy": "u2"})


def test_validate_and_extract_silence_payload():
    user = _user(group_ids=["g1", "g2"])

    with pytest.raises(HTTPException, match="Invalid silence payload"):
        helpers_mod.validate_and_normalize_silence_payload([], user)
    with pytest.raises(HTTPException, match="Invalid silence visibility"):
        helpers_mod.validate_and_normalize_silence_payload({"visibility": "world"}, user)
    with pytest.raises(HTTPException, match="At least one group"):
        helpers_mod.validate_and_normalize_silence_payload({"visibility": "group"}, user)
    with pytest.raises(HTTPException, match="not a member"):
        helpers_mod.validate_and_normalize_silence_payload(
            {"visibility": "group", "sharedGroupIds": ["g3"]},
            user,
        )

    normalized = helpers_mod.validate_and_normalize_silence_payload(
        {"visibility": "group", "shared_group_ids": ["g2", "g1", "g2"]},
        user,
    )
    assert normalized["sharedGroupIds"] == ["g2", "g1"]
    assert normalized["shared_group_ids"] == ["g2", "g1"]

    normalized = helpers_mod.validate_and_normalize_silence_payload(
        {"visibility": "tenant", "sharedGroupIds": ["g2"]},
        user,
    )
    assert normalized["sharedGroupIds"] == []

    superuser_normalized = helpers_mod.validate_and_normalize_silence_payload(
        {"visibility": "group", "sharedGroupIds": ["g3"]},
        _user(group_ids=["g1"], is_superuser=True),
    )
    assert superuser_normalized["sharedGroupIds"] == ["g3"]

    assert helpers_mod.extract_silence_id("silences/abc", None) == "abc"
    assert helpers_mod.extract_silence_id("other", {"silence_id": " sid "}) == "sid"
    assert helpers_mod.extract_silence_id("other", {}) is None


@pytest.mark.asyncio
async def test_find_silence_for_mutation_paths(monkeypatch):
    request = _request(headers=[(b"x-request-id", b"req-1")])
    user = _user()

    monkeypatch.setattr(helpers_mod.config, "get_secret", lambda key: None)
    with pytest.raises(HTTPException, match="service token not configured"):
        await helpers_mod.find_silence_for_mutation(request=request, current_user=user, silence_id="s1")

    monkeypatch.setattr(helpers_mod.config, "get_secret", lambda key: "service-token")
    monkeypatch.setattr(helpers_mod.benotified_proxy_service, "_sign_context_token", lambda **_: "ctx")
    monkeypatch.setattr(helpers_mod.benotified_proxy_service, "base_url", "https://benotified")

    async def raise_timeout(*_args, **_kwargs):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(helpers_mod.benotified_proxy_service._client, "request", raise_timeout)
    with pytest.raises(HTTPException, match="timed out"):
        await helpers_mod.find_silence_for_mutation(request=request, current_user=user, silence_id="s1")

    async def raise_http(*_args, **_kwargs):
        raise httpx.HTTPError("down")

    monkeypatch.setattr(helpers_mod.benotified_proxy_service._client, "request", raise_http)
    with pytest.raises(HTTPException, match="Failed to contact BeNotified"):
        await helpers_mod.find_silence_for_mutation(request=request, current_user=user, silence_id="s1")

    class ErrorResponse:
        status_code = 418
        text = "teapot"

        @staticmethod
        def json():
            raise ValueError("bad")

    async def error_response(*_args, **_kwargs):
        return ErrorResponse()

    monkeypatch.setattr(helpers_mod.benotified_proxy_service._client, "request", error_response)
    with pytest.raises(HTTPException) as exc_info:
        await helpers_mod.find_silence_for_mutation(request=request, current_user=user, silence_id="s1")
    assert exc_info.value.status_code == 418
    assert exc_info.value.detail == "teapot"

    class InvalidJsonResponse:
        status_code = 200

        @staticmethod
        def json():
            raise ValueError("bad")

    async def invalid_json_response(*_args, **_kwargs):
        return InvalidJsonResponse()

    monkeypatch.setattr(helpers_mod.benotified_proxy_service._client, "request", invalid_json_response)
    with pytest.raises(HTTPException, match="Invalid silence response"):
        await helpers_mod.find_silence_for_mutation(request=request, current_user=user, silence_id="s1")

    class OkResponse:
        status_code = 200

        @staticmethod
        def json():
            return [{"id": "s1"}, {"id": "s2"}]

    async def ok_response(*_args, **_kwargs):
        return OkResponse()

    monkeypatch.setattr(helpers_mod.benotified_proxy_service._client, "request", ok_response)
    assert await helpers_mod.find_silence_for_mutation(request=request, current_user=user, silence_id="s1") == {"id": "s1"}
    with pytest.raises(HTTPException, match="Silence not found"):
        await helpers_mod.find_silence_for_mutation(request=request, current_user=user, silence_id="missing")


@pytest.mark.asyncio
async def test_webhook_route_enforces_security_and_forwards(monkeypatch):
    calls = []

    monkeypatch.setattr(helpers_mod, "enforce_public_endpoint_security", lambda *args, **kwargs: calls.append(("public", kwargs)))
    monkeypatch.setattr(helpers_mod, "enforce_header_token", lambda *args, **kwargs: calls.append(("header", kwargs)))

    async def fake_forward(**kwargs):
        calls.append(("forward", kwargs))
        return Response(content=b"ok")

    monkeypatch.setattr(helpers_mod.benotified_proxy_service, "forward", fake_forward)
    handler = helpers_mod.webhook_route("firing", "alerts.webhook", "alerts")

    response = await handler(_request(headers=[(b"x-beobservant-webhook-token", b"secret")]))
    assert isinstance(response, Response)
    assert [call[0] for call in calls] == ["public", "header", "forward"]
    assert calls[-1][1]["upstream_path"] == "/internal/v1/alertmanager/alerts/firing"
    assert calls[-1][1]["current_user"] is None