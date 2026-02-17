"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

Rule import helpers for AlertManager bulk YAML uploads.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import yaml

from models.alerting.rules import AlertRuleCreate


class RuleImportError(ValueError):
    """Raised when uploaded rule YAML cannot be parsed/normalized."""


def _as_str_map(raw: Any) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    result: Dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            continue
        result[str(key)] = str(value)
    return result


def _normalize_visibility(value: Any, default_value: str = "private") -> str:
    normalized = str(value or default_value).strip().lower()
    if normalized == "tenant":
        return "tenant"
    if normalized == "group":
        return "group"
    if normalized == "public":
        return "public"
    return "private"


def _normalize_rule_entry(
    group_name: str,
    rule_data: Dict[str, Any],
    defaults: Dict[str, Any],
) -> AlertRuleCreate:
    alert_name = (rule_data.get("alert") or rule_data.get("name") or "").strip()
    expr = (rule_data.get("expr") or "").strip()
    if not alert_name:
        raise RuleImportError("Rule is missing required field 'alert'")
    if not expr:
        raise RuleImportError(f"Rule '{alert_name}' is missing required field 'expr'")

    be_meta = rule_data.get("beobservant") if isinstance(rule_data.get("beobservant"), dict) else {}

    labels = _as_str_map(rule_data.get("labels"))
    annotations = _as_str_map(rule_data.get("annotations"))

    severity = str(
        be_meta.get("severity")
        or labels.get("severity")
        or defaults.get("severity")
        or "warning"
    ).strip().lower()
    if severity not in {"info", "warning", "error", "critical"}:
        severity = "warning"

    duration = str(rule_data.get("for") or defaults.get("duration") or "5m").strip() or "5m"
    org_id = be_meta.get("orgId") or be_meta.get("org_id") or defaults.get("orgId")
    visibility = _normalize_visibility(be_meta.get("visibility") or defaults.get("visibility"), "private")

    channels_raw = be_meta.get("channels") if isinstance(be_meta.get("channels"), list) else defaults.get("channels")
    channels = [str(channel_id).strip() for channel_id in (channels_raw or []) if str(channel_id).strip()]

    shared_group_ids_raw = be_meta.get("sharedGroupIds") if isinstance(be_meta.get("sharedGroupIds"), list) else []
    shared_group_ids = [str(group_id).strip() for group_id in shared_group_ids_raw if str(group_id).strip()]

    merged_labels = {**labels}
    merged_labels.pop("severity", None)

    return AlertRuleCreate(
        orgId=str(org_id).strip() if org_id else None,
        name=alert_name,
        expression=expr,
        severity=severity,
        description=annotations.get("description"),
        enabled=bool(be_meta.get("enabled", defaults.get("enabled", True))),
        labels=merged_labels,
        annotations=annotations,
        **{"for": duration},
        groupName=(str(be_meta.get("group") or group_name or defaults.get("group") or "default").strip() or "default"),
        notificationChannels=channels,
        visibility=visibility,
        sharedGroupIds=shared_group_ids,
    )


def parse_rules_yaml(yaml_content: str, defaults: Optional[Dict[str, Any]] = None) -> List[AlertRuleCreate]:
    """Parse Prometheus-style rules YAML into AlertRuleCreate payloads.

    Supported shapes:
    - groups: [{name, rules:[...]}]
    - spec.groups: [{name, rules:[...]}] (Mimir style)
    - list of groups directly
    """
    if not (yaml_content or "").strip():
        raise RuleImportError("YAML content is required")

    defaults = defaults or {}
    try:
        parsed = yaml.safe_load(yaml_content)
    except Exception as exc:  # noqa: BLE001
        raise RuleImportError(f"Failed to parse YAML: {exc}") from exc

    if parsed is None:
        raise RuleImportError("YAML content is empty")

    groups: List[Dict[str, Any]]
    if isinstance(parsed, dict):
        if isinstance(parsed.get("groups"), list):
            groups = parsed["groups"]
        elif isinstance(parsed.get("spec"), dict) and isinstance(parsed["spec"].get("groups"), list):
            groups = parsed["spec"]["groups"]
        else:
            raise RuleImportError("Expected 'groups' or 'spec.groups' in YAML")
    elif isinstance(parsed, list):
        groups = parsed
    else:
        raise RuleImportError("Unsupported YAML structure for rules import")

    results: List[AlertRuleCreate] = []
    for group_idx, group in enumerate(groups):
        if not isinstance(group, dict):
            continue
        group_name = str(group.get("name") or defaults.get("group") or f"group-{group_idx + 1}").strip()
        rules = group.get("rules") if isinstance(group.get("rules"), list) else []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            results.append(_normalize_rule_entry(group_name, rule, defaults))

    if not results:
        raise RuleImportError("No valid alert rules found in YAML")
    return results
