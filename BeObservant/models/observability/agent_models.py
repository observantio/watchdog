"""
Module defines Pydantic models for Agent-related data structures used in the API layer.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0 
"""

from datetime import datetime
from typing import Dict, Optional, List
from pydantic import BaseModel, Field

class AgentHeartbeat(BaseModel):
    name: str = Field(..., description="Agent name")
    tenant_id: str = Field(..., description="Tenant ID (API key) associated with the agent")
    signal: Optional[str] = Field(None, description="Signal type (logs, traces, metrics)")
    attributes: Dict[str, str] = Field(default_factory=dict)
    timestamp: Optional[datetime] = None

class AgentInfo(BaseModel):
    id: str
    name: str
    tenant_id: str
    host_name: Optional[str] = None
    last_seen: datetime
    signals: List[str] = Field(default_factory=list)
    attributes: Dict[str, str] = Field(default_factory=dict)
