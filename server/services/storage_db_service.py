"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


"""Database-backed storage service for alert rules and notification channels.

Primary storage backend using PostgreSQL.  Supports optional Fernet
encryption of sensitive channel config at rest and the same
visibility / access-control semantics (private / group / tenant).
"""
import json
import logging
import uuid
import hashlib
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from models.alerting.rules import (
    AlertRule as AlertRulePydantic,
    AlertRuleCreate,
)
from models.alerting.channels import (
    NotificationChannel as NotificationChannelPydantic,
    NotificationChannelCreate,
)
from models.alerting.incidents import (
    AlertIncident as AlertIncidentPydantic,
    AlertIncidentUpdateRequest,
)
from db_models import (
    AlertRule as AlertRuleDB,
    AlertIncident as AlertIncidentDB,
    NotificationChannel as NotificationChannelDB,
    Group,
    User,
)
from database import get_db_session
from config import config as app_config

logger = logging.getLogger(__name__)
INCIDENT_META_KEY = "beobservant_meta"

def _get_shared_group_ids(db_obj) -> List[str]:
    """Extract group IDs from a DB object's shared_groups relationship."""
    return [g.id for g in db_obj.shared_groups] if db_obj.shared_groups else []


def _is_tenant_admin(db: Session, tenant_id: str, user_id: Optional[str]) -> bool:
    if not user_id:
        return False
    user = db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id).first()
    if not user:
        return False
    return bool(getattr(user, "is_superuser", False) or str(getattr(user, "role", "")).lower() == "admin")


def _resolve_groups(
    db: Session,
    tenant_id: str,
    group_ids: List[str],
    *,
    actor_user_id: Optional[str] = None,
    actor_group_ids: Optional[List[str]] = None,
    enforce_membership: bool = True,
) -> List[Group]:
    """Fetch and validate tenant-scoped Group ORM objects for a list of IDs."""
    normalized = [str(group_id).strip() for group_id in (group_ids or []) if str(group_id).strip()]
    if not normalized:
        return []

    groups = db.query(Group).filter(Group.tenant_id == tenant_id, Group.id.in_(normalized)).all()
    found_ids = {group.id for group in groups}
    missing = sorted(set(normalized) - found_ids)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid group ids: {missing}",
        )

    if enforce_membership and not _is_tenant_admin(db, tenant_id, actor_user_id):
        actor_groups = set(actor_group_ids or [])
        unauthorized = sorted({group_id for group_id in normalized if group_id not in actor_groups})
        if unauthorized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User not member of groups: {unauthorized}",
            )

    return groups


def _has_access(
    visibility: str,
    created_by: Optional[str],
    user_id: str,
    shared_group_ids: List[str],
    user_group_ids: List[str],
    require_write: bool = False,
) -> bool:
    """Check whether *user_id* may access a resource.

    Rules (evaluated in order):
    1. Owner always has access.
    2. ``tenant`` visibility grants access to every tenant member.
    3. ``group`` visibility grants access when the user shares at least
       one group with the resource.
    """
    if created_by == user_id:
        return True
    if require_write:
        return False
    if visibility == "public":
        return True
    if visibility == "tenant":
        return True
    if visibility == "group" and user_group_ids:
        return bool(set(shared_group_ids) & set(user_group_ids))
    return False


class DatabaseStorageService:
    """Persist alert rules and notification channels in PostgreSQL."""

    def __init__(self) -> None:
        self._fernet: Optional[Fernet] = None
        if app_config.DATA_ENCRYPTION_KEY:
            try:
                self._fernet = Fernet(app_config.DATA_ENCRYPTION_KEY)
                logger.info("Channel config encryption enabled (Fernet)")
            except ValueError:
                logger.error("Invalid DATA_ENCRYPTION_KEY – channel config will be stored unencrypted")

    # ------------------------------------------------------------------
    # Config encryption / decryption
    # ------------------------------------------------------------------

    def _encrypt_config(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """Return *cfg* wrapped in a Fernet token if a key is configured."""
        if not self._fernet:
            return cfg
        try:
            plaintext = json.dumps(cfg, default=str)
            token = self._fernet.encrypt(plaintext.encode()).decode()
            return {"__encrypted__": token}
        except Exception:
            logger.exception("Failed to encrypt channel config")
            return cfg

    def _decrypt_config(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """Unwrap a Fernet-encrypted config dict, or return as-is."""
        if "__encrypted__" not in cfg:
            return cfg
        if not self._fernet:
            raise ValueError("Encrypted channel config found but DATA_ENCRYPTION_KEY is not set")
        try:
            token = cfg["__encrypted__"]
            return json.loads(self._fernet.decrypt(token.encode()).decode())
        except InvalidToken as exc:
            raise ValueError("Cannot decrypt channel config – wrong key?") from exc


    def _rule_to_pydantic(self, r: AlertRuleDB) -> AlertRulePydantic:
        return AlertRulePydantic(
            id=r.id,
            org_id=r.org_id,
            name=r.name,
            expr=r.expr,
            duration=r.duration,
            severity=r.severity,
            labels=r.labels or {},
            annotations=r.annotations or {},
            enabled=r.enabled,
            group=r.group,
            notification_channels=r.notification_channels or [],
            visibility=r.visibility or "private",
            shared_group_ids=_get_shared_group_ids(r),
        )

    def _channel_to_pydantic(self, ch: NotificationChannelDB) -> NotificationChannelPydantic:
        return self._channel_to_pydantic_for_viewer(ch, viewer_user_id=ch.created_by)

    def _channel_to_pydantic_for_viewer(self, ch: NotificationChannelDB, viewer_user_id: Optional[str]) -> NotificationChannelPydantic:
        raw_config = self._decrypt_config(ch.config or {})
        is_owner = bool(ch.created_by and viewer_user_id and ch.created_by == viewer_user_id)
        safe_config = raw_config if is_owner else {}
        return NotificationChannelPydantic(
            id=ch.id,
            name=ch.name,
            type=ch.type,
            enabled=ch.enabled,
            config=safe_config,
            createdBy=ch.created_by,
            visibility=ch.visibility or "private",
            shared_group_ids=_get_shared_group_ids(ch),
        )

    def _incident_to_pydantic(self, incident: AlertIncidentDB) -> AlertIncidentPydantic:
        annotations = incident.annotations or {}
        raw_meta = annotations.get(INCIDENT_META_KEY) if isinstance(annotations, dict) else None
        meta: Dict[str, object] = {}
        if isinstance(raw_meta, str):
            try:
                meta = json.loads(raw_meta)
            except Exception:
                meta = {}
        elif isinstance(raw_meta, dict):
            meta = raw_meta

        note_items = []
        for note in (incident.notes or []):
            if not isinstance(note, dict):
                continue
            note_items.append({
                "author": note.get("author", "system"),
                "text": note.get("text", ""),
                "createdAt": note.get("createdAt") or datetime.now(timezone.utc),
            })

        # Normalize status so malformed/legacy values (e.g. 'IncidentStatus.OPEN')
        # don't break Pydantic enum validation. Ensure we pass the raw enum value
        # string ('open'|'resolved').
        status_value = incident.status
        try:
            from models.alerting.incidents import IncidentStatus
            if isinstance(status_value, IncidentStatus):
                status_value = status_value.value
        except Exception:
            pass
        if isinstance(status_value, str) and status_value.startswith("IncidentStatus."):
            status_value = status_value.split(".", 1)[1].lower()

        visibility_value = str(meta.get("visibility") or "public").lower()
        if visibility_value not in {"public", "private", "group"}:
            visibility_value = "public"

        raw_group_ids = meta.get("shared_group_ids") or []
        shared_group_ids = [str(group_id) for group_id in raw_group_ids if isinstance(group_id, str) and group_id.strip()]

        jira_ticket_key = meta.get("jira_ticket_key")
        jira_ticket_url = meta.get("jira_ticket_url")
        jira_integration_id = meta.get("jira_integration_id")
        user_managed_flag = bool(meta.get("user_managed"))
        hide_when_resolved_flag = bool(meta.get("hide_when_resolved"))

        # API schema expects string-valued annotations; sanitize legacy/non-string values
        safe_annotations: Dict[str, str] = {}
        if isinstance(annotations, dict):
            for key, value in annotations.items():
                if key == INCIDENT_META_KEY:
                    continue
                if value is None:
                    continue
                safe_annotations[str(key)] = str(value)

        return AlertIncidentPydantic(
            id=incident.id,
            fingerprint=incident.fingerprint,
            alertName=incident.alert_name,
            severity=incident.severity,
            status=status_value,
            assignee=incident.assignee,
            notes=note_items,
            labels=incident.labels or {},
            annotations=safe_annotations,
            visibility=visibility_value,
            sharedGroupIds=shared_group_ids,
            jiraTicketKey=jira_ticket_key,
            jiraTicketUrl=jira_ticket_url,
            jiraIntegrationId=jira_integration_id,
            startsAt=incident.starts_at,
            lastSeenAt=incident.last_seen_at,
            resolvedAt=incident.resolved_at,
            createdAt=incident.created_at,
            updatedAt=incident.updated_at,
            userManaged=user_managed_flag,
            hideWhenResolved=hide_when_resolved_flag,
        )

    def sync_incidents_from_alerts(self, tenant_id: str, alerts: List[Dict[str, Any]], resolve_missing: bool = True) -> None:
        """Upsert incidents from active alerts and resolve missing open incidents."""
        now = datetime.now(timezone.utc)
        active_fingerprints: set[str] = set()

        with get_db_session() as db:
            for alert in alerts or []:
                labels = alert.get("labels", {}) or {}
                annotations = alert.get("annotations", {}) or {}
                fingerprint = alert.get("fingerprint") or labels.get("fingerprint")
                if not fingerprint:
                    # Fallback fingerprint for integrations that omit explicit fingerprints.
                    # This preserves de-duplication behavior across repeated payloads.
                    stable_blob = json.dumps(
                        {
                            "alertname": labels.get("alertname") or "",
                            "severity": labels.get("severity") or "",
                            "labels": labels,
                            "annotations": annotations,
                        },
                        sort_keys=True,
                        default=str,
                    )
                    fingerprint = f"derived-{hashlib.sha256(stable_blob.encode()).hexdigest()}"
                active_fingerprints.add(fingerprint)

                incident = (
                    db.query(AlertIncidentDB)
                    .filter(AlertIncidentDB.tenant_id == tenant_id, AlertIncidentDB.fingerprint == fingerprint)
                    .first()
                )

                starts_at = alert.get("startsAt") or alert.get("starts_at")
                parsed_starts = None
                if starts_at:
                    try:
                        parsed_starts = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
                    except ValueError:
                        parsed_starts = None

                if not incident:
                    # Derive visibility and shared groups from the alert rule if available
                    rule_visibility = "public"
                    rule_shared_group_ids: List[str] = []
                    rule_created_by: Optional[str] = None
                    alertname = labels.get("alertname")
                    org_id_hint = str(
                        labels.get("org_id")
                        or labels.get("orgId")
                        or labels.get("tenant")
                        or labels.get("product")
                        or ""
                    ).strip()
                    if alertname:
                        try:
                            rule_query = db.query(AlertRuleDB).filter(
                                AlertRuleDB.tenant_id == tenant_id,
                                AlertRuleDB.name == alertname,
                            )
                            if org_id_hint:
                                rule = rule_query.filter(
                                    (AlertRuleDB.org_id == org_id_hint) | (AlertRuleDB.org_id.is_(None))
                                ).order_by(AlertRuleDB.org_id.desc()).first()
                            else:
                                rule = rule_query.first()
                            if rule is not None:
                                rule_visibility = rule.visibility or "public"
                                rule_shared_group_ids = _get_shared_group_ids(rule)
                                rule_created_by = rule.created_by
                        except Exception:
                            rule_visibility = "public"

                    metadata = {
                        "visibility": rule_visibility,
                        "shared_group_ids": rule_shared_group_ids,
                        "created_by": rule_created_by,
                    }
                    incident = AlertIncidentDB(
                        id=str(uuid.uuid4()),
                        tenant_id=tenant_id,
                        fingerprint=fingerprint,
                        alert_name=labels.get("alertname") or "Unnamed alert",
                        severity=labels.get("severity") or "warning",
                        status="open",
                        labels=labels,
                        starts_at=parsed_starts,
                        last_seen_at=now,
                        resolved_at=None,
                        notes=[],
                        annotations={**annotations, INCIDENT_META_KEY: json.dumps(metadata)},
                    )
                    db.add(incident)
                else:
                    existing_annotations = incident.annotations or {}
                    existing_meta: Dict[str, object] = {}
                    if isinstance(existing_annotations, dict):
                        maybe_meta = existing_annotations.get(INCIDENT_META_KEY)
                        if isinstance(maybe_meta, str):
                            try:
                                existing_meta = json.loads(maybe_meta)
                            except Exception:
                                existing_meta = {}
                        elif isinstance(maybe_meta, dict):
                            existing_meta = maybe_meta

                    # remember previous status so we can detect a reopen-by-alert
                    previous_status = incident.status

                    incident.alert_name = labels.get("alertname") or incident.alert_name
                    incident.severity = labels.get("severity") or incident.severity
                    incident.labels = labels

                    # If the alert refires after the incident was previously resolved,
                    # clear any previous assignee so the new occurrence is unassigned.
                    if previous_status == "resolved" or (incident.resolved_at is not None):
                        incident.assignee = None
                        # reopening by alert should clear any manual investigation lock
                        existing_meta.pop("user_managed", None)

                    # persist incoming annotations but keep our internal meta JSON
                    # Also update visibility/shared_group_ids from the alert rule when available
                    alertname = labels.get("alertname")
                    org_id_hint = str(
                        labels.get("org_id")
                        or labels.get("orgId")
                        or labels.get("tenant")
                        or labels.get("product")
                        or ""
                    ).strip()
                    if alertname:
                        try:
                            rule_query = db.query(AlertRuleDB).filter(
                                AlertRuleDB.tenant_id == tenant_id,
                                AlertRuleDB.name == alertname,
                            )
                            if org_id_hint:
                                rule = rule_query.filter(
                                    (AlertRuleDB.org_id == org_id_hint) | (AlertRuleDB.org_id.is_(None))
                                ).order_by(AlertRuleDB.org_id.desc()).first()
                            else:
                                rule = rule_query.first()
                            if rule is not None:
                                existing_meta["visibility"] = rule.visibility or existing_meta.get("visibility", "public")
                                existing_meta["shared_group_ids"] = _get_shared_group_ids(rule)
                                if rule.created_by:
                                    existing_meta["created_by"] = rule.created_by
                        except Exception:
                            pass

                    incident.annotations = {**annotations, INCIDENT_META_KEY: json.dumps(existing_meta)}
                    if parsed_starts and not incident.starts_at:
                        incident.starts_at = parsed_starts

                    # mark as active/open and update timestamps
                    incident.status = "open"
                    incident.last_seen_at = now
                    incident.resolved_at = None

            if resolve_missing:
                open_incidents = (
                    db.query(AlertIncidentDB)
                    .filter(AlertIncidentDB.tenant_id == tenant_id, AlertIncidentDB.status == "open")
                    .all()
                )
                for incident in open_incidents:
                    # respect incidents that were manually reopened / marked for investigation
                    annotations = incident.annotations or {}
                    raw_meta = annotations.get(INCIDENT_META_KEY) if isinstance(annotations, dict) else None
                    meta: Dict[str, object] = {}
                    if isinstance(raw_meta, str):
                        try:
                            meta = json.loads(raw_meta)
                        except Exception:
                            meta = {}
                    elif isinstance(raw_meta, dict):
                        meta = raw_meta

                    if meta.get("user_managed"):
                        # do not auto-resolve incidents under manual investigation
                        continue

                    if incident.fingerprint not in active_fingerprints:
                        incident.status = "resolved"
                        incident.resolved_at = now

    def list_incidents(
        self,
        tenant_id: str,
        user_id: str,
        group_ids: Optional[List[str]] = None,
        status: Optional[str] = None,
        visibility: Optional[str] = None,
        group_id: Optional[str] = None,
    ) -> List[AlertIncidentPydantic]:
        group_ids = group_ids or []
        with get_db_session() as db:
            query = db.query(AlertIncidentDB).filter(AlertIncidentDB.tenant_id == tenant_id)
            if status:
                query = query.filter(AlertIncidentDB.status == status)
            incidents = query.order_by(AlertIncidentDB.updated_at.desc()).all()
            result: List[AlertIncidentPydantic] = []
            for incident in incidents:
                annotations = incident.annotations or {}
                raw_meta = annotations.get(INCIDENT_META_KEY) if isinstance(annotations, dict) else None
                meta: Dict[str, object] = {}
                if isinstance(raw_meta, str):
                    try:
                        meta = json.loads(raw_meta)
                    except Exception:
                        meta = {}
                elif isinstance(raw_meta, dict):
                    meta = raw_meta
                incident_visibility = str(meta.get("visibility") or "public").lower()
                if incident_visibility not in {"public", "private", "group"}:
                    incident_visibility = "public"

                # If caller didn't explicitly request 'resolved' status, hide incidents marked to be hidden when resolved
                if incident.status == "resolved" and meta.get("hide_when_resolved") and not status:
                    continue

                if visibility and incident_visibility != visibility:
                    continue

                creator_id = meta.get("created_by")
                shared_group_ids = [
                    str(group_id)
                    for group_id in (meta.get("shared_group_ids") or [])
                    if isinstance(group_id, str) and group_id.strip()
                ]

                if group_id:
                    if group_id not in group_ids:
                        continue
                    if incident_visibility != "group":
                        continue
                    if group_id not in shared_group_ids:
                        continue

                if creator_id == user_id:
                    result.append(self._incident_to_pydantic(incident))
                    continue

                if incident_visibility == "public":
                    if group_id:
                        continue
                    result.append(self._incident_to_pydantic(incident))
                    continue

                if incident_visibility == "group":
                    if group_id:
                        # Filter by specific group
                        if group_id in group_ids and group_id in shared_group_ids:
                            result.append(self._incident_to_pydantic(incident))
                    elif group_ids and set(group_ids) & set(shared_group_ids):
                        # Show incidents visible to user's groups
                        result.append(self._incident_to_pydantic(incident))

            return result

    def get_incident(self, incident_id: str, tenant_id: str) -> Optional[AlertIncidentPydantic]:
        return self.get_incident_for_user(incident_id, tenant_id)

    def get_incident_for_user(
        self,
        incident_id: str,
        tenant_id: str,
        user_id: Optional[str] = None,
        group_ids: Optional[List[str]] = None,
        require_write: bool = False,
    ) -> Optional[AlertIncidentPydantic]:
        group_ids = group_ids or []
        with get_db_session() as db:
            incident = (
                db.query(AlertIncidentDB)
                .filter(AlertIncidentDB.id == incident_id, AlertIncidentDB.tenant_id == tenant_id)
                .first()
            )
            if not incident:
                return None

            if user_id:
                annotations = incident.annotations or {}
                raw_meta = annotations.get(INCIDENT_META_KEY) if isinstance(annotations, dict) else None
                meta: Dict[str, object] = {}
                if isinstance(raw_meta, str):
                    try:
                        meta = json.loads(raw_meta)
                    except Exception:
                        meta = {}
                elif isinstance(raw_meta, dict):
                    meta = raw_meta

                visibility = str(meta.get("visibility") or "public").lower()
                if visibility not in {"public", "private", "group"}:
                    visibility = "public"
                creator_id = str(meta.get("created_by") or "") or None
                shared_group_ids = [
                    str(group_id)
                    for group_id in (meta.get("shared_group_ids") or [])
                    if isinstance(group_id, str) and group_id.strip()
                ]

                if not _has_access(
                    visibility,
                    creator_id,
                    user_id,
                    shared_group_ids,
                    group_ids,
                    require_write=require_write,
                ):
                    return None

            return self._incident_to_pydantic(incident)

    def update_incident(
        self,
        incident_id: str,
        tenant_id: str,
        user_id: str,
        payload: AlertIncidentUpdateRequest,
    ) -> Optional[AlertIncidentPydantic]:
        with get_db_session() as db:
            incident = (
                db.query(AlertIncidentDB)
                .filter(AlertIncidentDB.id == incident_id, AlertIncidentDB.tenant_id == tenant_id)
                .first()
            )
            if not incident:
                return None

            if payload.assignee is not None:
                incident.assignee = payload.assignee.strip() or None

            # track whether the incoming status update represents a manual reopen/resolve
            manual_manage_flag: Optional[bool] = None
            if payload.status is not None:
                status_value = payload.status.value if hasattr(payload.status, "value") else str(payload.status)
                if status_value.startswith("IncidentStatus."):
                    status_value = status_value.split(".", 1)[1].lower()
                incident.status = status_value
                # compare the stored value when deciding resolved timestamp
                if incident.status == "resolved":
                    incident.resolved_at = datetime.now(timezone.utc)
                    manual_manage_flag = False
                else:
                    incident.resolved_at = None
                    # manual reopen / investigation should prevent auto-resolve
                    if incident.status == "open":
                        manual_manage_flag = True

            annotations = incident.annotations or {}
            raw_meta = annotations.get(INCIDENT_META_KEY) if isinstance(annotations, dict) else None
            meta: Dict[str, object] = {}
            if isinstance(raw_meta, str):
                try:
                    meta = json.loads(raw_meta)
                except Exception:
                    meta = {}
            elif isinstance(raw_meta, dict):
                meta = raw_meta
            if not meta.get("created_by"):
                meta["created_by"] = user_id

            # apply manual-management flag if status was changed by a user
            if manual_manage_flag is True:
                meta["user_managed"] = True
            elif manual_manage_flag is False:
                meta.pop("user_managed", None)

            # Visibility and shared groups are derived from the originating alert rule
            # and must not be overridden by client requests. Ignore payload visibility
            # and shared_group_ids to enforce inheritance.

            # Allow clients to set the hide-when-resolved flag
            try:
                hide_flag = getattr(payload, "hide_when_resolved", None)
            except Exception:
                hide_flag = None
            if hide_flag is True:
                meta["hide_when_resolved"] = True
            elif hide_flag is False:
                meta.pop("hide_when_resolved", None)

            if payload.jira_ticket_key is not None:
                jira_key = payload.jira_ticket_key.strip()
                if jira_key:
                    meta["jira_ticket_key"] = jira_key
                else:
                    meta.pop("jira_ticket_key", None)

            if payload.jira_ticket_url is not None:
                jira_url = payload.jira_ticket_url.strip()
                if jira_url:
                    meta["jira_ticket_url"] = jira_url
                else:
                    meta.pop("jira_ticket_url", None)

            if getattr(payload, "jira_integration_id", None) is not None:
                jira_integration_id = payload.jira_integration_id.strip()
                if jira_integration_id:
                    meta["jira_integration_id"] = jira_integration_id
                else:
                    meta.pop("jira_integration_id", None)

            meta["updated_by"] = user_id
            annotations = annotations if isinstance(annotations, dict) else {}
            incident.annotations = {**annotations, INCIDENT_META_KEY: json.dumps(meta)}

            if payload.note:
                try:
                    logger.debug("Appending note for incident %s by user %s: %s", incident_id, user_id, str(payload.note))
                except Exception:
                    pass
                existing_notes = incident.notes or []
                notes_before = list(existing_notes)
                notes = list(existing_notes)
                notes.append(
                    {
                        "author": user_id,
                        "text": payload.note,
                        "createdAt": datetime.now(timezone.utc).isoformat(),
                    }
                )
                incident.notes = notes
                try:
                    logger.debug("Incident %s notes before append: %s", incident_id, str(notes_before))
                    logger.debug("Incident %s notes after append: %s", incident_id, str(incident.notes))
                except Exception:
                    pass

            db.flush()
            return self._incident_to_pydantic(incident)

    def get_public_alert_rules(self, tenant_id: str) -> List[AlertRulePydantic]:
        with get_db_session() as db:
            rules = (
                db.query(AlertRuleDB)
                .options(joinedload(AlertRuleDB.shared_groups))
                .filter(AlertRuleDB.tenant_id == tenant_id, AlertRuleDB.visibility == "public", AlertRuleDB.enabled.is_(True))
                .all()
            )
            return [self._rule_to_pydantic(r) for r in rules]

    def get_alert_rules(
        self, tenant_id: str, user_id: str, group_ids: Optional[List[str]] = None,
    ) -> List[AlertRulePydantic]:
        group_ids = group_ids or []
        with get_db_session() as db:
            rules = (
                db.query(AlertRuleDB)
                .options(joinedload(AlertRuleDB.shared_groups))
                .filter(AlertRuleDB.tenant_id == tenant_id)
                .all()
            )
            return [
                self._rule_to_pydantic(r) for r in rules
                if _has_access(r.visibility or "private", r.created_by, user_id,
                               _get_shared_group_ids(r), group_ids)
            ]

    def get_alert_rules_for_org(self, tenant_id: str, org_id: str) -> List[AlertRulePydantic]:
        with get_db_session() as db:
            rules = (
                db.query(AlertRuleDB)
                .options(joinedload(AlertRuleDB.shared_groups))
                .filter(AlertRuleDB.tenant_id == tenant_id, AlertRuleDB.org_id == org_id)
                .all()
            )
            return [self._rule_to_pydantic(r) for r in rules]

    def get_alert_rules_with_owner(self, tenant_id: str, user_id: str, group_ids: Optional[List[str]] = None) -> List[tuple]:
        """Return list of (AlertRulePydantic, created_by) tuples for tenant rules.

        Useful when callers need owner metadata to decide whether to expose
        tenant-scoped sensitive fields like `org_id`.
        """
        group_ids = group_ids or []
        with get_db_session() as db:
            rules = (
                db.query(AlertRuleDB)
                .options(joinedload(AlertRuleDB.shared_groups))
                .filter(AlertRuleDB.tenant_id == tenant_id)
                .all()
            )
            result = []
            for r in rules:
                if _has_access(r.visibility or "private", r.created_by, user_id, _get_shared_group_ids(r), group_ids):
                    result.append((self._rule_to_pydantic(r), r.created_by))
            return result

    def get_alert_rule_raw(self, rule_id: str, tenant_id: str):
        """Return the raw DB object for a specific rule or None if not found."""
        with get_db_session() as db:
            r = (
                db.query(AlertRuleDB)
                .options(joinedload(AlertRuleDB.shared_groups))
                .filter(AlertRuleDB.id == rule_id, AlertRuleDB.tenant_id == tenant_id)
                .first()
            )
            return r

    def get_alert_rule(
        self, rule_id: str, tenant_id: str, user_id: str,
        group_ids: Optional[List[str]] = None,
    ) -> Optional[AlertRulePydantic]:
        group_ids = group_ids or []
        with get_db_session() as db:
            r = (
                db.query(AlertRuleDB)
                .options(joinedload(AlertRuleDB.shared_groups))
                .filter(AlertRuleDB.id == rule_id, AlertRuleDB.tenant_id == tenant_id)
                .first()
            )
            if not r:
                return None
            if not _has_access(r.visibility or "private", r.created_by, user_id,
                               _get_shared_group_ids(r), group_ids, require_write=True):
                return None
            return self._rule_to_pydantic(r)

    def create_alert_rule(
        self, rule_create: AlertRuleCreate, tenant_id: str, user_id: str,
        group_ids: Optional[List[str]] = None,
    ) -> AlertRulePydantic:
        with get_db_session() as db:
            rule = AlertRuleDB(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                created_by=user_id,
                org_id=rule_create.org_id or None,
                name=rule_create.name,
                group=rule_create.group,
                expr=rule_create.expr,
                duration=rule_create.duration,
                severity=rule_create.severity,
                labels=rule_create.labels or {},
                annotations=rule_create.annotations or {},
                enabled=rule_create.enabled,
                notification_channels=rule_create.notification_channels or [],
                visibility=rule_create.visibility or "private",
            )
            if rule_create.shared_group_ids:
                if (rule_create.visibility or "private") == "group":
                    rule.shared_groups = _resolve_groups(
                        db,
                        tenant_id,
                        rule_create.shared_group_ids,
                        actor_user_id=user_id,
                        actor_group_ids=group_ids,
                    )
                else:
                    rule.shared_groups = []
            db.add(rule)
            db.flush()
            logger.info("Created alert rule %s (%s) org_id=%s visibility=%s", rule.name, rule.id, rule.org_id, rule.visibility)
            return self._rule_to_pydantic(rule)

    def update_alert_rule(
        self, rule_id: str, rule_update: AlertRuleCreate, tenant_id: str,
        user_id: str, group_ids: Optional[List[str]] = None,
    ) -> Optional[AlertRulePydantic]:
        group_ids = group_ids or []
        with get_db_session() as db:
            r = (
                db.query(AlertRuleDB)
                .options(joinedload(AlertRuleDB.shared_groups))
                .filter(AlertRuleDB.id == rule_id, AlertRuleDB.tenant_id == tenant_id)
                .first()
            )
            if not r:
                return None
            if not _has_access(r.visibility or "private", r.created_by, user_id,
                               _get_shared_group_ids(r), group_ids):
                return None

            r.org_id = rule_update.org_id or None
            r.name = rule_update.name
            r.group = rule_update.group
            r.expr = rule_update.expr
            r.duration = rule_update.duration
            r.severity = rule_update.severity
            r.labels = rule_update.labels or {}
            r.annotations = rule_update.annotations or {}
            r.enabled = rule_update.enabled
            r.notification_channels = rule_update.notification_channels or []
            r.visibility = rule_update.visibility or "private"
            if rule_update.shared_group_ids is not None:
                if (rule_update.visibility or "private") == "group":
                    r.shared_groups = _resolve_groups(
                        db,
                        tenant_id,
                        rule_update.shared_group_ids,
                        actor_user_id=user_id,
                        actor_group_ids=group_ids,
                    )
                else:
                    r.shared_groups = []

            db.flush()
            logger.info("Updated alert rule %s (%s) org_id=%s", r.name, rule_id, r.org_id)
            return self._rule_to_pydantic(r)

    def delete_alert_rule(
        self, rule_id: str, tenant_id: str, user_id: str,
        group_ids: Optional[List[str]] = None,
    ) -> bool:
        group_ids = group_ids or []
        with get_db_session() as db:
            r = (
                db.query(AlertRuleDB)
                .options(joinedload(AlertRuleDB.shared_groups))
                .filter(AlertRuleDB.id == rule_id, AlertRuleDB.tenant_id == tenant_id)
                .first()
            )
            if not r:
                return False
            if not _has_access(r.visibility or "private", r.created_by, user_id,
                               _get_shared_group_ids(r), group_ids, require_write=True):
                return False
            db.delete(r)
            logger.info("Deleted alert rule %s", rule_id)
            return True

    def get_notification_channels(
        self, tenant_id: str, user_id: str, group_ids: Optional[List[str]] = None,
    ) -> List[NotificationChannelPydantic]:
        group_ids = group_ids or []
        with get_db_session() as db:
            channels = (
                db.query(NotificationChannelDB)
                .options(joinedload(NotificationChannelDB.shared_groups))
                .filter(NotificationChannelDB.tenant_id == tenant_id)
                .all()
            )
            return [
                self._channel_to_pydantic_for_viewer(ch, user_id) for ch in channels
                if _has_access(ch.visibility or "private", ch.created_by, user_id,
                               _get_shared_group_ids(ch), group_ids)
            ]

    def get_notification_channel(
        self, channel_id: str, tenant_id: str, user_id: str,
        group_ids: Optional[List[str]] = None,
    ) -> Optional[NotificationChannelPydantic]:
        group_ids = group_ids or []
        with get_db_session() as db:
            ch = (
                db.query(NotificationChannelDB)
                .options(joinedload(NotificationChannelDB.shared_groups))
                .filter(NotificationChannelDB.id == channel_id,
                        NotificationChannelDB.tenant_id == tenant_id)
                .first()
            )
            if not ch:
                return None
            if not _has_access(ch.visibility or "private", ch.created_by, user_id,
                               _get_shared_group_ids(ch), group_ids):
                return None
            return self._channel_to_pydantic_for_viewer(ch, user_id)

    def create_notification_channel(
        self, channel_create: NotificationChannelCreate, tenant_id: str,
        user_id: str, group_ids: Optional[List[str]] = None,
    ) -> NotificationChannelPydantic:
        with get_db_session() as db:
            ch = NotificationChannelDB(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                created_by=user_id,
                name=channel_create.name,
                type=channel_create.type,
                config=self._encrypt_config(channel_create.config or {}),
                enabled=channel_create.enabled,
                visibility=channel_create.visibility or "private",
            )
            if channel_create.shared_group_ids:
                if (channel_create.visibility or "private") == "group":
                    ch.shared_groups = _resolve_groups(
                        db,
                        tenant_id,
                        channel_create.shared_group_ids,
                        actor_user_id=user_id,
                        actor_group_ids=group_ids,
                    )
                else:
                    ch.shared_groups = []
            db.add(ch)
            db.flush()
            logger.info("Created channel %s (%s) visibility=%s", ch.name, ch.id, ch.visibility)
            return self._channel_to_pydantic(ch)

    def update_notification_channel(
        self, channel_id: str, channel_update: NotificationChannelCreate,
        tenant_id: str, user_id: str, group_ids: Optional[List[str]] = None,
    ) -> Optional[NotificationChannelPydantic]:
        group_ids = group_ids or []
        with get_db_session() as db:
            ch = (
                db.query(NotificationChannelDB)
                .options(joinedload(NotificationChannelDB.shared_groups))
                .filter(NotificationChannelDB.id == channel_id,
                        NotificationChannelDB.tenant_id == tenant_id)
                .first()
            )
            if not ch:
                return None
            if ch.created_by != user_id:
                return None

            ch.name = channel_update.name
            ch.type = channel_update.type
            ch.config = self._encrypt_config(channel_update.config or {})
            ch.enabled = channel_update.enabled
            ch.visibility = channel_update.visibility or "private"
            if channel_update.shared_group_ids is not None:
                if (channel_update.visibility or "private") == "group":
                    ch.shared_groups = _resolve_groups(
                        db,
                        tenant_id,
                        channel_update.shared_group_ids,
                        actor_user_id=user_id,
                        actor_group_ids=group_ids,
                    )
                else:
                    ch.shared_groups = []

            db.flush()
            logger.info("Updated channel %s (%s)", ch.name, channel_id)
            return self._channel_to_pydantic(ch)

    def delete_notification_channel(
        self, channel_id: str, tenant_id: str, user_id: str,
        group_ids: Optional[List[str]] = None,
    ) -> bool:
        group_ids = group_ids or []
        with get_db_session() as db:
            ch = (
                db.query(NotificationChannelDB)
                .options(joinedload(NotificationChannelDB.shared_groups))
                .filter(NotificationChannelDB.id == channel_id,
                        NotificationChannelDB.tenant_id == tenant_id)
                .first()
            )
            if not ch:
                return False
            if ch.created_by != user_id:
                return False
            db.delete(ch)
            logger.info("Deleted channel %s", channel_id)
            return True

    def is_notification_channel_owner(self, channel_id: str, tenant_id: str, user_id: str) -> bool:
        with get_db_session() as db:
            ch = (
                db.query(NotificationChannelDB)
                .filter(NotificationChannelDB.id == channel_id, NotificationChannelDB.tenant_id == tenant_id)
                .first()
            )
            if not ch:
                return False
            return ch.created_by == user_id

    def test_notification_channel(
        self, channel_id: str, tenant_id: str, user_id: str,
        group_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        channel = self.get_notification_channel(channel_id, tenant_id, user_id, group_ids)
        if not channel:
            return {"success": False, "error": "Channel not found"}
        logger.info("Testing channel: %s (%s)", channel.name, channel.type)
        return {
            "success": True,
            "message": f"Test notification would be sent to {channel.type} channel: {channel.name}",
        }

    def get_notification_channels_for_rule_name(self, rule_name: str) -> List[NotificationChannelPydantic]:
        """Return notification channels for alert rules matching *rule_name*.

        If a rule specifies explicit channel IDs, only those channels for the
        rule's tenant are returned. If a rule has no channels configured, all
        tenant channels are returned. This may return channels across multiple
        tenants if multiple rules share the same name.
        """
        with get_db_session() as db:
            results: List[NotificationChannelPydantic] = []
            rules = db.query(AlertRuleDB).filter(AlertRuleDB.name == rule_name, AlertRuleDB.enabled == True).all()
            for r in rules:
                if r.notification_channels:
                    chs = db.query(NotificationChannelDB).filter(
                        NotificationChannelDB.tenant_id == r.tenant_id,
                        NotificationChannelDB.id.in_(r.notification_channels)
                    ).all()
                else:
                    chs = db.query(NotificationChannelDB).filter(NotificationChannelDB.tenant_id == r.tenant_id).all()
                for ch in chs:
                    results.append(self._channel_to_pydantic(ch))
            return results
