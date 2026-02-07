"""Storage service for alert rules and notification channels."""
import json
import logging
import uuid
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, Any

from cryptography.fernet import Fernet, InvalidToken
from models.alertmanager_models import (
    AlertRule, AlertRuleCreate, NotificationChannel, NotificationChannelCreate
)
from config import config

logger = logging.getLogger(__name__)

class StorageService:
    """Service for persisting alert rules and notification channels."""
    
    def __init__(self, data_dir: str = config.STORAGE_DIR):
        """Initialize storage service.
        
        Args:
            data_dir: Directory for storing data files
        """
        self.data_dir = self._find_writable_dir(Path(data_dir))

        self.rules_file = self.data_dir / "alert_rules.json"
        self.channels_file = self.data_dir / "notification_channels.json"

        self._fernet = None
        if config.DATA_ENCRYPTION_KEY:
            try:
                self._fernet = Fernet(config.DATA_ENCRYPTION_KEY)
            except ValueError:
                logger.error("Invalid DATA_ENCRYPTION_KEY; encryption disabled")
        
        try:
            self._ensure_files_exist()
        except PermissionError:
            logger.warning("Configured storage dir %s not writable, attempting fallback", data_dir)
            alternate = self._find_writable_dir(Path(tempfile.gettempdir()) / "beobservant")
            if str(alternate) != str(self.data_dir):
                self.data_dir = alternate
                self.rules_file = self.data_dir / "alert_rules.json"
                self.channels_file = self.data_dir / "notification_channels.json"
                self._ensure_files_exist()
            else:
                raise
    
    def _ensure_files_exist(self):
        """Ensure storage files exist with default data."""
        if not self.rules_file.exists():
            try:
                self.rules_file.write_text(self._serialize([]))
            except PermissionError as e:
                logger.error("Permission denied when creating %s: %s", self.rules_file, e)
                raise

        if not self.channels_file.exists():
            try:
                self.channels_file.write_text(self._serialize([]))
            except PermissionError as e:
                logger.error("Permission denied when creating %s: %s", self.channels_file, e)
                raise

    def _find_writable_dir(self, candidate: Path) -> Path:
        """Return a directory Path that is writable, trying fallbacks.

        Tries the configured `candidate` first, then `/tmp/beobservant`, then
        an application-local `data/` directory next to the server package.
        """
        candidates = [candidate, Path(tempfile.gettempdir()) / "beobservant",
                      Path(__file__).resolve().parent.parent / "data"]

        last_exc = None
        for p in candidates:
            try:
                p.mkdir(parents=True, exist_ok=True)
                test_file = p / ".writetest"
                with test_file.open("w") as f:
                    f.write("ok")
                try:
                    test_file.unlink()
                except Exception:
                    pass
                logger.info("Using storage directory: %s", p)
                return p
            except PermissionError as e:
                last_exc = e
                logger.warning("No write access to %s: %s", p, e)
            except Exception as e:
                last_exc = e
                logger.warning("Unable to prepare storage dir %s: %s", p, e)

        logger.error("No writable storage directory found; last error: %s", last_exc)
        raise PermissionError("No writable storage directory available")

    def _serialize(self, payload: List[Dict[str, Any]]) -> str:
        content = json.dumps(payload, indent=2, default=str)
        if not self._fernet:
            return content
        token = self._fernet.encrypt(content.encode("utf-8")).decode("utf-8")
        return f"ENC::{token}"

    def _deserialize(self, content: str) -> List[Dict[str, Any]]:
        if content.startswith("ENC::"):
            if not self._fernet:
                raise ValueError("Encrypted storage requires DATA_ENCRYPTION_KEY")
            token = content.replace("ENC::", "", 1)
            try:
                decrypted = self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
            except InvalidToken as exc:
                raise ValueError("Invalid encryption token or key") from exc
            return json.loads(decrypted)
        return json.loads(content)
    
    def get_alert_rules(self) -> List[AlertRule]:
        """Get all alert rules.
        
        Returns:
            List of alert rules
        """
        try:
            data = self._deserialize(self.rules_file.read_text())
            return [AlertRule(**rule) for rule in data]
        except Exception as e:
            logger.error(f"Error loading alert rules: {e}")
            return []
    
    def get_alert_rule(self, rule_id: str) -> Optional[AlertRule]:
        """Get a specific alert rule by ID.
        
        Args:
            rule_id: Rule ID
            
        Returns:
            Alert rule or None
        """
        rules = self.get_alert_rules()
        for rule in rules:
            if rule.id == rule_id:
                return rule
        return None
    
    def create_alert_rule(self, rule_create: AlertRuleCreate) -> AlertRule:
        """Create a new alert rule.
        
        Args:
            rule_create: Rule creation data
            
        Returns:
            Created alert rule
        """
        rules = self.get_alert_rules()
        
        new_rule = AlertRule(
            id=str(uuid.uuid4()),
            **rule_create.model_dump()
        )
        
        rules.append(new_rule)
        self._save_rules(rules)
        
        logger.info(f"Created alert rule: {new_rule.name} ({new_rule.id})")
        return new_rule
    
    def update_alert_rule(self, rule_id: str, rule_update: AlertRuleCreate) -> Optional[AlertRule]:
        """Update an existing alert rule.
        
        Args:
            rule_id: Rule ID
            rule_update: Updated rule data
            
        Returns:
            Updated alert rule or None
        """
        rules = self.get_alert_rules()
        
        for i, rule in enumerate(rules):
            if rule.id == rule_id:
                updated_rule = AlertRule(
                    id=rule_id,
                    **rule_update.model_dump()
                )
                rules[i] = updated_rule
                self._save_rules(rules)
                logger.info(f"Updated alert rule: {updated_rule.name} ({rule_id})")
                return updated_rule
        
        return None
    
    def delete_alert_rule(self, rule_id: str) -> bool:
        """Delete an alert rule.
        
        Args:
            rule_id: Rule ID
            
        Returns:
            True if deleted, False if not found
        """
        rules = self.get_alert_rules()
        original_count = len(rules)
        
        rules = [r for r in rules if r.id != rule_id]
        
        if len(rules) < original_count:
            self._save_rules(rules)
            logger.info(f"Deleted alert rule: {rule_id}")
            return True
        
        return False
    
    def _save_rules(self, rules: List[AlertRule]):
        """Save rules to file.
        
        Args:
            rules: List of rules to save
        """
        data = [rule.model_dump() for rule in rules]
        self.rules_file.write_text(self._serialize(data))
    
    def get_notification_channels(self) -> List[NotificationChannel]:
        """Get all notification channels.
        
        Returns:
            List of notification channels
        """
        try:
            data = self._deserialize(self.channels_file.read_text())
            return [NotificationChannel(**channel) for channel in data]
        except Exception as e:
            logger.error(f"Error loading notification channels: {e}")
            return []
    
    def get_notification_channel(self, channel_id: str) -> Optional[NotificationChannel]:
        """Get a specific notification channel by ID.
        
        Args:
            channel_id: Channel ID
            
        Returns:
            Notification channel or None
        """
        channels = self.get_notification_channels()
        for channel in channels:
            if channel.id == channel_id:
                return channel
        return None
    
    def create_notification_channel(
        self,
        channel_create: NotificationChannelCreate
    ) -> NotificationChannel:
        """Create a new notification channel.
        
        Args:
            channel_create: Channel creation data
            
        Returns:
            Created notification channel
        """
        channels = self.get_notification_channels()
        
        new_channel = NotificationChannel(
            id=str(uuid.uuid4()),
            **channel_create.model_dump()
        )
        
        channels.append(new_channel)
        self._save_channels(channels)
        
        logger.info(f"Created notification channel: {new_channel.name} ({new_channel.id})")
        return new_channel
    
    def update_notification_channel(
        self,
        channel_id: str,
        channel_update: NotificationChannelCreate
    ) -> Optional[NotificationChannel]:
        """Update an existing notification channel.
        
        Args:
            channel_id: Channel ID
            channel_update: Updated channel data
            
        Returns:
            Updated notification channel or None
        """
        channels = self.get_notification_channels()
        
        for i, channel in enumerate(channels):
            if channel.id == channel_id:
                updated_channel = NotificationChannel(
                    id=channel_id,
                    **channel_update.model_dump()
                )
                channels[i] = updated_channel
                self._save_channels(channels)
                logger.info(f"Updated notification channel: {updated_channel.name} ({channel_id})")
                return updated_channel
        
        return None
    
    def delete_notification_channel(self, channel_id: str) -> bool:
        """Delete a notification channel.
        
        Args:
            channel_id: Channel ID
            
        Returns:
            True if deleted, False if not found
        """
        channels = self.get_notification_channels()
        original_count = len(channels)
        
        channels = [c for c in channels if c.id != channel_id]
        
        if len(channels) < original_count:
            self._save_channels(channels)
            logger.info(f"Deleted notification channel: {channel_id}")
            return True
        
        return False
    
    def _save_channels(self, channels: List[NotificationChannel]):
        """Save channels to file.
        
        Args:
            channels: List of channels to save
        """
        data = [channel.model_dump() for channel in channels]
        self.channels_file.write_text(self._serialize(data))
    
    def test_notification_channel(self, channel_id: str) -> Dict[str, Any]:
        """Test a notification channel.
        
        Args:
            channel_id: Channel ID to test
            
        Returns:
            Test result
        """
        channel = self.get_notification_channel(channel_id)
        if not channel:
            return {"success": False, "error": "Channel not found"}
        
        logger.info(f"Testing notification channel: {channel.name} ({channel.type})")
        
        return {
            "success": True,
            "message": f"Test notification would be sent to {channel.type} channel: {channel.name}",
            "config": channel.config
        }
