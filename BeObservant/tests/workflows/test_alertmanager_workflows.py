"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from models.access.auth_models import Permission, Role
from routers.observability import alertmanager_router

from .helpers import WorkflowState, patch_auth_service


def _build_alertmanager_forwarder(state: dict[str, Any], forward_calls: list[dict[str, Any]]):
    async def fake_forward(**kwargs: Any) -> JSONResponse:
        forward_calls.append(
            {
                "method": kwargs["request"].method,
                "path": kwargs["upstream_path"],
                "require_api_key": kwargs["require_api_key"],
                "user_id": getattr(kwargs.get("current_user"), "user_id", None),
            }
        )

        request = kwargs["request"]
        method = request.method.upper()
        path = kwargs["upstream_path"].removeprefix("/internal/v1/api/alertmanager/")
        current_user = kwargs.get("current_user")
        body = await request.body()
        payload = json.loads(body.decode("utf-8")) if body else {}

        if path == "public/rules":
            return JSONResponse({"groups": list(state["rules"].values())})

        if path == "rules" and method == "GET":
            return JSONResponse(list(state["rules"].values()))
        if path == "rules" and method == "POST":
            rule_id = f"rule-{state['next_rule_id']}"
            state["next_rule_id"] += 1
            rule = {
                "id": rule_id,
                "name": payload.get("name", rule_id),
                "expr": payload.get("expr", "up == 0"),
                "for": payload.get("for", "5m"),
                "labels": payload.get("labels", {}),
                "annotations": payload.get("annotations", {}),
                "created_by": getattr(current_user, "user_id", None),
            }
            state["rules"][rule_id] = rule
            return JSONResponse(rule)
        if path == "rules/import" and method == "POST":
            imported = []
            for raw_rule in payload.get("rules", []):
                rule_id = f"rule-{state['next_rule_id']}"
                state["next_rule_id"] += 1
                rule = {
                    "id": rule_id,
                    "name": raw_rule.get("name", rule_id),
                    "expr": raw_rule.get("expr", "up == 0"),
                    "for": raw_rule.get("for", "1m"),
                    "labels": raw_rule.get("labels", {}),
                    "annotations": raw_rule.get("annotations", {}),
                    "created_by": getattr(current_user, "user_id", None),
                }
                state["rules"][rule_id] = rule
                imported.append(rule)
            return JSONResponse({"imported": imported, "count": len(imported)})
        if path.startswith("rules/") and method == "PUT":
            rule_id = path.split("/", 1)[1]
            rule = state["rules"][rule_id]
            rule.update({
                "name": payload.get("name", rule["name"]),
                "expr": payload.get("expr", rule["expr"]),
                "labels": payload.get("labels", rule["labels"]),
                "annotations": payload.get("annotations", rule["annotations"]),
            })
            return JSONResponse(rule)
        if path.startswith("rules/") and method == "DELETE":
            rule_id = path.split("/", 1)[1]
            state["rules"].pop(rule_id, None)
            return JSONResponse({"deleted": True, "id": rule_id})

        if path == "channels" and method == "GET":
            return JSONResponse(list(state["channels"].values()))
        if path == "channels" and method == "POST":
            channel_id = f"chan-{state['next_channel_id']}"
            state["next_channel_id"] += 1
            channel = {
                "id": channel_id,
                "name": payload.get("name", channel_id),
                "type": payload.get("type", "email"),
                "config": payload.get("config", {}),
                "created_by": getattr(current_user, "user_id", None),
            }
            state["channels"][channel_id] = channel
            return JSONResponse(channel)
        if path.startswith("channels/") and method == "PUT":
            channel_id = path.split("/", 1)[1]
            channel = state["channels"][channel_id]
            channel.update(
                {
                    "name": payload.get("name", channel["name"]),
                    "type": payload.get("type", channel["type"]),
                    "config": payload.get("config", channel["config"]),
                }
            )
            return JSONResponse(channel)
        if path.startswith("channels/") and method == "DELETE":
            channel_id = path.split("/", 1)[1]
            state["channels"].pop(channel_id, None)
            return JSONResponse({"deleted": True, "id": channel_id})

        if path == "silences" and method == "GET":
            return JSONResponse(list(state["silences"].values()))
        if path == "silences" and method == "POST":
            silence_id = payload.get("id") or f"sil-{state['next_silence_id']}"
            state["next_silence_id"] += 1
            silence = {
                "id": silence_id,
                "matchers": payload.get("matchers", []),
                "visibility": payload.get("visibility", "private"),
                "sharedGroupIds": payload.get("sharedGroupIds", []),
                "annotations": payload.get("annotations", {}),
                "created_by": getattr(current_user, "user_id", None),
            }
            state["silences"][silence_id] = silence
            return JSONResponse(silence)
        if path.startswith("silences/") and method == "PUT":
            silence_id = path.split("/", 1)[1]
            silence = state["silences"][silence_id]
            silence.update(
                {
                    "matchers": payload.get("matchers", silence["matchers"]),
                    "visibility": payload.get("visibility", silence["visibility"]),
                    "sharedGroupIds": payload.get("sharedGroupIds", silence.get("sharedGroupIds", [])),
                    "annotations": payload.get("annotations", silence.get("annotations", {})),
                }
            )
            return JSONResponse(silence)
        if path.startswith("silences/") and method == "DELETE":
            silence_id = path.split("/", 1)[1]
            state["silences"].pop(silence_id, None)
            return JSONResponse({"deleted": True, "id": silence_id})

        if path == "jira/config" and method == "GET":
            return JSONResponse(state["jira_config"])
        if path == "jira/config" and method == "POST":
            state["jira_config"] = {
                "projectKey": payload.get("projectKey"),
                "issueType": payload.get("issueType"),
                "strategy": payload.get("strategy", "create"),
            }
            return JSONResponse(state["jira_config"])
        if path == "jira/issues" and method == "POST":
            issue_id = f"jira-{state['next_issue_id']}"
            state["next_issue_id"] += 1
            issue = {
                "id": issue_id,
                "summary": payload.get("summary"),
                "labels": payload.get("labels", []),
            }
            state["issues"][issue_id] = issue
            return JSONResponse(issue)

        if path.startswith("integrations/") and method == "POST":
            integration_name = path.split("/", 1)[1]
            state["integrations"][integration_name] = payload
            return JSONResponse({"name": integration_name, "config": payload})

        if path == "metrics/names" and method == "GET":
            return JSONResponse(["cpu_usage", "error_rate", "latency_p95"])

        if path.startswith("incidents/") and method == "PATCH":
            incident_id = path.split("/", 1)[1]
            incident = state["incidents"].setdefault(incident_id, {"id": incident_id, "status": "open"})
            incident.update(payload)
            return JSONResponse(incident)

        raise AssertionError(f"Unhandled alertmanager path: {method} {path}")

    return fake_forward


def test_alertmanager_rules_channels_and_integrations_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)

    operator = state.create_user(
        SimpleNamespace(username="operator", email="operator@example.com", password="password123", role=Role.USER),
        state.tenant_id,
    )
    read_only = state.create_user(
        SimpleNamespace(username="reader", email="reader@example.com", password="password123", role=Role.VIEWER),
        state.tenant_id,
    )
    tenant_manager = state.create_user(
        SimpleNamespace(username="tenantmgr", email="tenantmgr@example.com", password="password123", role=Role.USER),
        state.tenant_id,
    )

    state.update_user_permissions(
        operator.id,
        [
            Permission.READ_RULES.value,
            Permission.CREATE_RULES.value,
            Permission.UPDATE_RULES.value,
            Permission.DELETE_RULES.value,
            Permission.TEST_RULES.value,
            Permission.WRITE_ALERTS.value,
            Permission.READ_CHANNELS.value,
            Permission.CREATE_CHANNELS.value,
            Permission.UPDATE_CHANNELS.value,
            Permission.DELETE_CHANNELS.value,
            Permission.TEST_CHANNELS.value,
            Permission.WRITE_CHANNELS.value,
            Permission.READ_INCIDENTS.value,
            Permission.UPDATE_INCIDENTS.value,
            Permission.READ_ALERTS.value,
            Permission.READ_SILENCES.value,
            Permission.READ_METRICS.value,
        ],
        state.tenant_id,
    )
    state.update_user_permissions(tenant_manager.id, [Permission.MANAGE_TENANTS.value], state.tenant_id)

    store = {
        "rules": {},
        "channels": {},
        "silences": {},
        "issues": {},
        "jira_config": {"projectKey": None, "issueType": None, "strategy": "create"},
        "integrations": {},
        "incidents": {},
        "next_rule_id": 1,
        "next_channel_id": 1,
        "next_silence_id": 1,
        "next_issue_id": 1,
    }
    forward_calls: list[dict[str, Any]] = []

    monkeypatch.setattr(alertmanager_router, "enforce_public_endpoint_security", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        alertmanager_router.benotified_proxy_service,
        "forward",
        _build_alertmanager_forwarder(store, forward_calls),
    )

    operator_headers = state.auth_header(f"token-{operator.id}")
    read_only_headers = state.auth_header(f"token-{read_only.id}")
    tenant_manager_headers = state.auth_header(f"token-{tenant_manager.id}")

    cpu_rule_response = client.post(
        "/api/alertmanager/rules",
        headers=operator_headers,
        json={
            "name": "cpu-high",
            "expr": "sum(rate(cpu_usage[5m])) > 0.8",
            "labels": {"severity": "critical"},
            "annotations": {"summary": "CPU saturation"},
        },
    )
    assert cpu_rule_response.status_code == 200
    cpu_rule_id = cpu_rule_response.json()["id"]

    import_rules_response = client.post(
        "/api/alertmanager/rules/import",
        headers=operator_headers,
        json={
            "rules": [
                {"name": "latency-spike", "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 1"},
                {"name": "error-burst", "expr": "sum(rate(errors_total[5m])) > 10"},
            ]
        },
    )
    assert import_rules_response.status_code == 200
    assert import_rules_response.json()["count"] == 2

    list_rules_response = client.get("/api/alertmanager/rules", headers=operator_headers)
    assert list_rules_response.status_code == 200
    assert {rule["name"] for rule in list_rules_response.json()} == {"cpu-high", "latency-spike", "error-burst"}

    update_rule_response = client.put(
        f"/api/alertmanager/rules/{cpu_rule_id}",
        headers=operator_headers,
        json={"name": "cpu-critical", "expr": "sum(rate(cpu_usage[5m])) > 0.9"},
    )
    assert update_rule_response.status_code == 200
    assert update_rule_response.json()["name"] == "cpu-critical"

    email_channel_response = client.post(
        "/api/alertmanager/channels",
        headers=operator_headers,
        json={"name": "email-primary", "type": "email", "config": {"to": ["ops@example.com"]}},
    )
    assert email_channel_response.status_code == 200
    email_channel_id = email_channel_response.json()["id"]

    slack_channel_response = client.post(
        "/api/alertmanager/channels",
        headers=operator_headers,
        json={"name": "slack-war-room", "type": "slack", "config": {"webhook": "https://hooks.slack.test"}},
    )
    assert slack_channel_response.status_code == 200
    slack_channel_id = slack_channel_response.json()["id"]

    assert client.get("/api/alertmanager/channels", headers=operator_headers).status_code == 200

    update_channel_response = client.put(
        f"/api/alertmanager/channels/{email_channel_id}",
        headers=operator_headers,
        json={"name": "email-escalation", "type": "email", "config": {"to": ["sre@example.com"], "cc": ["mgr@example.com"]}},
    )
    assert update_channel_response.status_code == 200
    assert update_channel_response.json()["name"] == "email-escalation"

    delete_channel_response = client.delete(f"/api/alertmanager/channels/{slack_channel_id}", headers=operator_headers)
    assert delete_channel_response.status_code == 200

    metrics_response = client.get("/api/alertmanager/metrics/names", headers=operator_headers)
    assert metrics_response.status_code == 200
    assert "error_rate" in metrics_response.json()

    jira_config_response = client.post(
        "/api/alertmanager/jira/config",
        headers=tenant_manager_headers,
        json={"projectKey": "OPS", "issueType": "Incident", "strategy": "dedupe"},
    )
    assert jira_config_response.status_code == 200
    assert jira_config_response.json()["projectKey"] == "OPS"

    issue_response = client.post(
        "/api/alertmanager/jira/issues",
        headers=operator_headers,
        json={"summary": "Checkout failure", "labels": ["prod", "checkout"]},
    )
    assert issue_response.status_code == 200
    assert issue_response.json()["summary"] == "Checkout failure"

    slack_integration_response = client.post(
        "/api/alertmanager/integrations/slack",
        headers=operator_headers,
        json={"method": "webhook", "channel": "#ops", "severity": "critical"},
    )
    assert slack_integration_response.status_code == 200

    webhook_integration_response = client.post(
        "/api/alertmanager/integrations/webhook",
        headers=operator_headers,
        json={"method": "signed", "url": "https://hooks.example.com/incidents"},
    )
    assert webhook_integration_response.status_code == 200

    incident_patch_response = client.patch(
        "/api/alertmanager/incidents/inc-42",
        headers=operator_headers,
        json={"status": "acknowledged", "owner": "oncall"},
    )
    assert incident_patch_response.status_code == 200
    assert incident_patch_response.json()["status"] == "acknowledged"

    public_rules_response = client.get("/api/alertmanager/public/rules")
    assert public_rules_response.status_code == 200
    assert len(public_rules_response.json()["groups"]) == 3

    assert client.post("/api/alertmanager/channels", headers=read_only_headers, json={"name": "blocked"}).status_code == 403
    assert client.get("/api/alertmanager/jira/config", headers=read_only_headers).status_code == 403

    delete_rule_response = client.delete(f"/api/alertmanager/rules/{cpu_rule_id}", headers=operator_headers)
    assert delete_rule_response.status_code == 200
    assert set(store["integrations"]) == {"slack", "webhook"}
    assert store["jira_config"]["strategy"] == "dedupe"
    assert all(call["require_api_key"] for call in forward_calls if call["method"] in {"POST", "PUT", "PATCH", "DELETE"})


def test_alertmanager_silence_validation_and_ownership_workflow(client, monkeypatch: pytest.MonkeyPatch) -> None:
    state = WorkflowState()
    patch_auth_service(monkeypatch, state)

    operator_one = state.create_user(
        SimpleNamespace(username="operator1", email="operator1@example.com", password="password123", role=Role.USER),
        state.tenant_id,
    )
    operator_two = state.create_user(
        SimpleNamespace(username="operator2", email="operator2@example.com", password="password123", role=Role.USER),
        state.tenant_id,
    )

    common_permissions = [
        Permission.READ_SILENCES.value,
        Permission.CREATE_SILENCES.value,
        Permission.UPDATE_SILENCES.value,
        Permission.DELETE_SILENCES.value,
        Permission.WRITE_ALERTS.value,
    ]
    state.update_user_permissions(operator_one.id, common_permissions, state.tenant_id)
    state.update_user_permissions(operator_two.id, common_permissions, state.tenant_id)

    ops_group = state.create_group(SimpleNamespace(name="ops", description="Operations"), state.tenant_id)
    state.update_group_members(ops_group.id, [operator_one.id], state.tenant_id)

    store = {
        "rules": {},
        "channels": {},
        "silences": {},
        "issues": {},
        "jira_config": {},
        "integrations": {},
        "incidents": {},
        "next_rule_id": 1,
        "next_channel_id": 1,
        "next_silence_id": 1,
        "next_issue_id": 1,
    }
    forward_calls: list[dict[str, Any]] = []

    async def fake_find_silence_for_mutation(**kwargs: Any) -> dict[str, Any]:
        silence = store["silences"].get(kwargs["silence_id"])
        if silence is None:
            raise HTTPException(status_code=404, detail="Silence not found")
        return silence

    monkeypatch.setattr(
        alertmanager_router.benotified_proxy_service,
        "forward",
        _build_alertmanager_forwarder(store, forward_calls),
    )
    monkeypatch.setattr(alertmanager_router, "find_silence_for_mutation", fake_find_silence_for_mutation)

    operator_one_headers = state.auth_header(f"token-{operator_one.id}")
    operator_two_headers = state.auth_header(f"token-{operator_two.id}")

    created_silence_response = client.post(
        "/api/alertmanager/silences",
        headers=operator_one_headers,
        json={
            "id": "sil-ops-1",
            "matchers": [{"name": "service", "value": "checkout"}],
            "visibility": "group",
            "sharedGroupIds": [ops_group.id],
            "annotations": {"reason": "maintenance"},
        },
    )
    assert created_silence_response.status_code == 200
    assert created_silence_response.json()["sharedGroupIds"] == [ops_group.id]

    missing_group_response = client.post(
        "/api/alertmanager/silences",
        headers=operator_one_headers,
        json={"id": "sil-invalid-1", "visibility": "group", "sharedGroupIds": []},
    )
    assert missing_group_response.status_code == 400

    unauthorized_group_response = client.post(
        "/api/alertmanager/silences",
        headers=operator_one_headers,
        json={"id": "sil-invalid-2", "visibility": "group", "sharedGroupIds": ["g-unauthorized"]},
    )
    assert unauthorized_group_response.status_code == 403

    assert client.put(
        "/api/alertmanager/silences/sil-ops-1",
        headers=operator_two_headers,
        json={"id": "sil-ops-1", "visibility": "private"},
    ).status_code == 403

    assert client.delete("/api/alertmanager/silences/sil-ops-1", headers=operator_two_headers).status_code == 403

    owner_update_response = client.put(
        "/api/alertmanager/silences/sil-ops-1",
        headers=operator_one_headers,
        json={"id": "sil-ops-1", "visibility": "private", "annotations": {"reason": "extended"}},
    )
    assert owner_update_response.status_code == 200
    assert owner_update_response.json()["visibility"] == "private"

    owner_delete_response = client.delete("/api/alertmanager/silences/sil-ops-1", headers=operator_one_headers)
    assert owner_delete_response.status_code == 200
    assert store["silences"] == {}
    assert any(call["path"].endswith("/silences") for call in forward_calls)