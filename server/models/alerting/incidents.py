"""Incident history and ticketing models for AlertManager."""
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class IncidentStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class IncidentNote(BaseModel):
    author: str
    text: str
    created_at: datetime = Field(..., alias="createdAt")

    class Config:
        populate_by_name = True


class AlertIncident(BaseModel):
    id: str
    fingerprint: str
    alert_name: str = Field(..., alias="alertName")
    severity: str
    status: IncidentStatus
    assignee: Optional[str] = None
    notes: List[IncidentNote] = Field(default_factory=list)
    labels: Dict[str, str] = Field(default_factory=dict)
    annotations: Dict[str, str] = Field(default_factory=dict)
    starts_at: Optional[datetime] = Field(None, alias="startsAt")
    last_seen_at: datetime = Field(..., alias="lastSeenAt")
    resolved_at: Optional[datetime] = Field(None, alias="resolvedAt")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")

    class Config:
        use_enum_values = True
        populate_by_name = True


class AlertIncidentUpdateRequest(BaseModel):
    status: Optional[IncidentStatus] = None
    assignee: Optional[str] = None
    note: Optional[str] = None
