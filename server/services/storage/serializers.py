"""DB -> Pydantic serializers for storage domain objects."""
from datetime import datetime, timezone
import logging
from typing import Any, Dict

from models.alerting.rules import AlertRule as AlertRulePydantic
from models.alerting.channels import NotificationChannel as NotificationChannelPydantic
from models.alerting.incidents import AlertIncident as AlertIncidentPydantic

from services.common.meta import INCIDENT_META_KEY, _parse_meta, _safe_group_ids

logger = logging.getLogger(__name__)


def _rule_to_pydantic(r) -> AlertRulePydantic:
    return AlertRulePydantic(
        id=r.id, org_id=r.org_id, name=r.name, expr=r.expr, duration=r.duration,
        severity=r.severity, labels=r.labels or {}, annotations=r.annotations or {},
        enabled=r.enabled, group=r.group, notification_channels=r.notification_channels or [],
        visibility=r.visibility or "private", shared_group_ids=[g.id for g in r.shared_groups] if r.shared_groups else [],
    )


def _channel_to_pydantic(ch, viewer_user_id: Any) -> NotificationChannelPydantic:
    return _channel_to_pydantic_for_viewer(ch, viewer_user_id=ch.created_by)


def _channel_to_pydantic_for_viewer(ch, viewer_user_id: Any) -> NotificationChannelPydantic:
    # `ch.config` should already be decrypted by caller when needed
    raw_config = ch.config or {}
    return NotificationChannelPydantic(
        id=ch.id, name=ch.name, type=ch.type, enabled=ch.enabled,
        config=raw_config if (ch.created_by and ch.created_by == viewer_user_id) else {},
        createdBy=ch.created_by, visibility=ch.visibility or "private",
        shared_group_ids=[g.id for g in ch.shared_groups] if ch.shared_groups else [],
    )


def _incident_to_pydantic(incident) -> AlertIncidentPydantic:
    annotations = incident.annotations or {}
    meta = _parse_meta(annotations)

    note_items = [
        {"author": n.get("author", "system"), "text": n.get("text", ""), "createdAt": n.get("createdAt") or datetime.now(timezone.utc)}
        for n in (incident.notes or []) if isinstance(n, dict)
    ]

    status_value = incident.status
    try:
        from models.alerting.incidents import IncidentStatus
        if isinstance(status_value, IncidentStatus):
            status_value = status_value.value
    except ImportError:
        logger.debug("IncidentStatus import unavailable while normalizing incident status")
    if isinstance(status_value, str) and status_value.startswith("IncidentStatus."):
        status_value = status_value.split(".", 1)[1].lower()

    visibility_value = str(meta.get("visibility") or "public").lower()
    if visibility_value not in {"public", "private", "group"}:
        visibility_value = "public"

    safe_annotations = {
        str(k): str(v) for k, v in annotations.items()
        if isinstance(annotations, dict) and k != INCIDENT_META_KEY and v is not None
    }

    return AlertIncidentPydantic(
        id=incident.id, fingerprint=incident.fingerprint, alertName=incident.alert_name,
        severity=incident.severity, status=status_value, assignee=incident.assignee,
        notes=note_items, labels=incident.labels or {}, annotations=safe_annotations,
        visibility=visibility_value, sharedGroupIds=_safe_group_ids(meta),
        jiraTicketKey=meta.get("jira_ticket_key"), jiraTicketUrl=meta.get("jira_ticket_url"),
        jiraIntegrationId=meta.get("jira_integration_id"),
        startsAt=incident.starts_at, lastSeenAt=incident.last_seen_at,
        resolvedAt=incident.resolved_at, createdAt=incident.created_at,
        updatedAt=incident.updated_at,
        userManaged=bool(meta.get("user_managed")),
        hideWhenResolved=bool(meta.get("hide_when_resolved")),
    )
