"""AlertManager related models."""
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field
from enum import Enum

class AlertState(str, Enum):
    """Alert state enum."""
    UNPROCESSED = "unprocessed"
    ACTIVE = "active"
    SUPPRESSED = "suppressed"

class ChannelType(str, Enum):
    """Notification channel types."""
    EMAIL = "email"
    SLACK = "slack"
    TEAMS = "teams"
    WEBHOOK = "webhook"
    PAGERDUTY = "pagerduty"
    OPSGENIE = "opsgenie"

class RuleSeverity(str, Enum):
    """Alert rule severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class AlertStatus(BaseModel):
    """Alert status information."""
    state: AlertState = Field(..., description="Current state of the alert")
    silenced_by: List[str] = Field(default_factory=list, alias="silencedBy", description="List of silences that silence this alert")
    inhibited_by: List[str] = Field(default_factory=list, alias="inhibitedBy", description="List of alerts that inhibit this alert")
    
    class Config:
        populate_by_name = True

class Alert(BaseModel):
    """Alert representation."""
    labels: Dict[str, str] = Field(..., description="Key-value pairs that identify the alert")
    annotations: Dict[str, str] = Field(default_factory=dict, description="Additional information about the alert")
    starts_at: str = Field(..., alias="startsAt", description="Time when the alert started firing")
    ends_at: Optional[str] = Field(None, alias="endsAt", description="Time when the alert stopped firing")
    generator_url: Optional[str] = Field(None, alias="generatorURL", description="URL of the alert generator")
    status: AlertStatus = Field(..., description="Current status of the alert")
    receivers: Optional[List[Union[str, Dict[str, Any]]]] = Field(default_factory=list, description="List of receivers for this alert")
    fingerprint: Optional[str] = Field(None, description="Unique identifier for the alert")
    
    class Config:
        populate_by_name = True

class AlertGroup(BaseModel):
    """Grouped alerts."""
    labels: Dict[str, str] = Field(..., description="Common labels for the group")
    receiver: str = Field(..., description="Receiver that will handle these alerts")
    alerts: List[Alert] = Field(..., description="List of alerts in this group")

class Matcher(BaseModel):
    """Alert matcher."""
    name: str = Field(..., description="Label name to match")
    value: str = Field(..., description="Value to match against")
    is_regex: bool = Field(False, alias="isRegex", description="Whether the value is a regular expression")
    is_equal: bool = Field(True, alias="isEqual", description="Whether to match equal values")
    
    class Config:
        populate_by_name = True

class Silence(BaseModel):
    """Silence representation."""
    id: Optional[str] = Field(None, description="Unique identifier for the silence")
    matchers: List[Matcher] = Field(..., description="Matchers that define which alerts to silence")
    starts_at: str = Field(..., alias="startsAt", description="Time when the silence starts")
    ends_at: str = Field(..., alias="endsAt", description="Time when the silence ends")
    created_by: str = Field(..., alias="createdBy", description="User who created the silence")
    comment: str = Field(..., description="Comment explaining the silence")
    status: Optional[Dict[str, str]] = Field(None, description="Current status of the silence")
    
    class Config:
        populate_by_name = True

class SilenceCreate(BaseModel):
    """Create a new silence."""
    matchers: List[Matcher] = Field(..., description="Matchers that define which alerts to silence")
    starts_at: str = Field(..., alias="startsAt", description="Time when the silence starts")
    ends_at: str = Field(..., alias="endsAt", description="Time when the silence ends")
    created_by: str = Field(..., alias="createdBy", description="User who created the silence")
    comment: str = Field(..., description="Comment explaining the silence")
    
    class Config:
        populate_by_name = True

class NotificationChannel(BaseModel):
    """Notification channel configuration."""
    id: Optional[str] = Field(None, description="Unique identifier")
    name: str = Field(..., description="Channel name")
    type: ChannelType = Field(..., description="Channel type")
    enabled: bool = Field(True, description="Whether the channel is enabled")
    config: Dict[str, Any] = Field(..., description="Channel-specific configuration")
    
    class Config:
        use_enum_values = True

class NotificationChannelCreate(BaseModel):
    """Create a notification channel."""
    name: str = Field(..., min_length=1, max_length=100, description="Channel name")
    type: ChannelType = Field(..., description="Channel type")
    enabled: bool = Field(True, description="Whether the channel is enabled")
    config: Dict[str, Any] = Field(..., description="Channel-specific configuration")
    
    class Config:
        use_enum_values = True

class AlertRule(BaseModel):
    """Alert rule definition."""
    id: Optional[str] = Field(None, description="Unique identifier")
    name: str = Field(..., description="Rule name")
    expr: str = Field(..., description="PromQL expression")
    duration: str = Field("1m", description="Duration for which the condition must be true")
    severity: RuleSeverity = Field(RuleSeverity.WARNING, description="Alert severity")
    labels: Dict[str, str] = Field(default_factory=dict, description="Additional labels")
    annotations: Dict[str, str] = Field(default_factory=dict, description="Annotations with description, summary, etc.")
    enabled: bool = Field(True, description="Whether the rule is enabled")
    group: str = Field("default", description="Rule group name")
    notification_channels: List[str] = Field(default_factory=list, alias="notificationChannels", description="List of notification channel IDs to send alerts to. If empty, sends to all channels.")
    
    class Config:
        use_enum_values = True
        populate_by_name = True

class AlertRuleCreate(BaseModel):
    """Create an alert rule."""
    name: str = Field(..., min_length=1, max_length=100, description="Rule name")
    expr: str = Field(..., min_length=1, description="PromQL expression")
    duration: str = Field("1m", description="Duration for which the condition must be true")
    severity: RuleSeverity = Field(RuleSeverity.WARNING, description="Alert severity")
    labels: Dict[str, str] = Field(default_factory=dict, description="Additional labels")
    annotations: Dict[str, str] = Field(default_factory=dict, description="Annotations")
    enabled: bool = Field(True, description="Whether the rule is enabled")
    group: str = Field("default", description="Rule group name")
    notification_channels: List[str] = Field(default_factory=list, alias="notificationChannels", description="List of notification channel IDs. Empty means all channels.")
    
    class Config:
        use_enum_values = True
        populate_by_name = True

class Receiver(BaseModel):
    """Alert receiver configuration."""
    name: str = Field(..., description="Name of the receiver")
    email_configs: Optional[List[Dict]] = Field(None, alias="emailConfigs", description="Email notification configurations")
    slack_configs: Optional[List[Dict]] = Field(None, alias="slackConfigs", description="Slack notification configurations")
    webhook_configs: Optional[List[Dict]] = Field(None, alias="webhookConfigs", description="Webhook notification configurations")
    
    class Config:
        populate_by_name = True

class AlertManagerStatus(BaseModel):
    """AlertManager status."""
    cluster: Dict[str, Any] = Field(..., description="Cluster information")
    version_info: Dict[str, str] = Field(..., alias="versionInfo", description="Version information")
    config: Dict[str, Any] = Field(..., description="Current configuration")
    uptime: str = Field(..., description="Uptime of the AlertManager instance")
    
    class Config:
        populate_by_name = True
