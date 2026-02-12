"""Database-backed storage service for alert rules and notification channels.

Primary storage backend using PostgreSQL.  Supports optional Fernet
encryption of sensitive channel config at rest and the same
visibility / access-control semantics (private / group / tenant).
"""
import json
import logging
import uuid
from typing import List, Optional, Dict, Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session, joinedload

from models.rules import (
    AlertRule as AlertRulePydantic,
    AlertRuleCreate,
)
from models.channels import (
    NotificationChannel as NotificationChannelPydantic,
    NotificationChannelCreate,
)
from db_models import (
    AlertRule as AlertRuleDB,
    NotificationChannel as NotificationChannelDB,
    Group,
)
from database import get_db_session
from config import config as app_config

logger = logging.getLogger(__name__)

def _get_shared_group_ids(db_obj) -> List[str]:
    """Extract group IDs from a DB object's shared_groups relationship."""
    return [g.id for g in db_obj.shared_groups] if db_obj.shared_groups else []


def _resolve_groups(db: Session, group_ids: List[str]) -> List[Group]:
    """Fetch Group ORM objects for a list of IDs."""
    if not group_ids:
        return []
    return db.query(Group).filter(Group.id.in_(group_ids)).all()


def _has_access(
    visibility: str,
    created_by: Optional[str],
    user_id: str,
    shared_group_ids: List[str],
    user_group_ids: List[str],
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
        return NotificationChannelPydantic(
            id=ch.id,
            name=ch.name,
            type=ch.type,
            enabled=ch.enabled,
            config=self._decrypt_config(ch.config or {}),
            visibility=ch.visibility or "private",
            shared_group_ids=_get_shared_group_ids(ch),
        )

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
                               _get_shared_group_ids(r), group_ids):
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
                rule.shared_groups = _resolve_groups(db, rule_create.shared_group_ids)
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
                r.shared_groups = _resolve_groups(db, rule_update.shared_group_ids)

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
                               _get_shared_group_ids(r), group_ids):
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
                self._channel_to_pydantic(ch) for ch in channels
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
            return self._channel_to_pydantic(ch)

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
                ch.shared_groups = _resolve_groups(db, channel_create.shared_group_ids)
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
            if not _has_access(ch.visibility or "private", ch.created_by, user_id,
                               _get_shared_group_ids(ch), group_ids):
                return None

            ch.name = channel_update.name
            ch.type = channel_update.type
            ch.config = self._encrypt_config(channel_update.config or {})
            ch.enabled = channel_update.enabled
            ch.visibility = channel_update.visibility or "private"
            if channel_update.shared_group_ids is not None:
                ch.shared_groups = _resolve_groups(db, channel_update.shared_group_ids)

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
            if not _has_access(ch.visibility or "private", ch.created_by, user_id,
                               _get_shared_group_ids(ch), group_ids):
                return False
            db.delete(ch)
            logger.info("Deleted channel %s", channel_id)
            return True

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
