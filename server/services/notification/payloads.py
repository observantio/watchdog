"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import Optional
from datetime import datetime
from models.alerting.alerts import Alert

NO_VALUE = "(none)"


def get_label(alert: Alert, key: str, default: str = "") -> str:
    labels = alert.labels or {}
    return str(labels.get(key, default))


def get_annotation(alert: Alert, key: str) -> Optional[str]:
    annotations = alert.annotations or {}
    value = annotations.get(key)
    if value is None:
        return None
    return str(value)


def get_alert_text(alert: Alert) -> str:
    summary = get_annotation(alert, "summary")
    description = get_annotation(alert, "description")
    if summary and description and summary != description:
        return f"{summary}\n{description}"
    return summary or description or "No description"


def format_alert_body(alert: Alert, action: str) -> str:
    summary = get_annotation(alert, "summary")
    description = get_annotation(alert, "description")
    lines = [
        f"Alert: {get_label(alert, 'alertname', 'Unknown')}",
        f"Status: {action}",
        f"Severity: {get_label(alert, 'severity', 'unknown')}",
        f"Started: {alert.starts_at}",
        "",
        "Summary:",
        summary or "No summary",
        "",
        "Description:",
        description or "No description",
        "",
        "Labels:",
    ]

    for key, value in (alert.labels or {}).items():
        lines.append(f"  {key}: {value}")

    return "\n".join(lines)


def build_slack_payload(alert: Alert, action: str) -> dict:
    color = "danger" if action == "firing" else "good"
    if get_label(alert, "severity") == "warning":
        color = "warning"
    return {
        "attachments": [{
            "color": color,
            "title": f"[{action.upper()}] {get_label(alert, 'alertname', 'Alert')}",
            "text": get_alert_text(alert),
            "fields": [
                {"title": "Severity", "value": get_label(alert, 'severity', 'unknown'), "short": True},
                {"title": "Status", "value": action, "short": True},
                {"title": "Summary", "value": get_annotation(alert, 'summary') or NO_VALUE, "short": False},
                {"title": "Description", "value": get_annotation(alert, 'description') or NO_VALUE, "short": False},
            ],
            "footer": f"Started: {alert.starts_at}",
            "ts": int(datetime.now().timestamp()),
        }]
    }


def build_teams_payload(alert: Alert, action: str) -> dict:
    theme_color = "FF0000" if action == "firing" else "00FF00"
    if get_label(alert, "severity") == "warning":
        theme_color = "FFA500"
    return {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": theme_color,
        "title": f"[{action.upper()}] {get_label(alert, 'alertname', 'Alert')}",
        "text": get_alert_text(alert),
        "sections": [{
            "facts": [
                {"name": "Severity", "value": get_label(alert, 'severity', 'unknown')},
                {"name": "Status", "value": action},
                {"name": "Started", "value": alert.starts_at},
                {"name": "Summary", "value": get_annotation(alert, 'summary') or NO_VALUE},
                {"name": "Description", "value": get_annotation(alert, 'description') or NO_VALUE},
            ]
        }]
    }


def build_pagerduty_payload(alert: Alert, action: str, routing_key: str) -> dict:
    event_action = "trigger" if action == "firing" else "resolve"
    summary = get_annotation(alert, "summary")
    description = get_annotation(alert, "description")
    return {
        "routing_key": routing_key,
        "event_action": event_action,
        "dedup_key": alert.fingerprint,
        "payload": {
            "summary": summary or description or get_label(alert, 'alertname', 'Alert'),
            "severity": get_label(alert, 'severity', 'warning'),
            "source": get_label(alert, 'instance', 'unknown'),
            "custom_details": {"labels": alert.labels or {}, "annotations": alert.annotations or {}, "summary": summary, "description": description},
        },
    }
