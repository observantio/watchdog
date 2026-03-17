"""
This manages the API key models for the server,
including creation, updating, and sharing of API keys with users and groups.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

class ApiKeyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

class ApiKeyCreate(ApiKeyBase):
    key: Optional[str] = Field(None, min_length=3, max_length=200, description="Optional custom API key value (org_id / X-Scope-OrgID)")

class ApiKeyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_enabled: Optional[bool] = None
    is_default: Optional[bool] = None

class ApiKeyShareUser(BaseModel):
    user_id: str
    username: Optional[str] = None
    email: Optional[str] = None
    can_use: bool = True
    created_at: datetime

class ApiKeyShareUpdateRequest(BaseModel):
    user_ids: List[str] = Field(default_factory=list)
    group_ids: List[str] = Field(default_factory=list)

class ApiKey(ApiKeyBase):
    id: str
    key: str
    otlp_token: Optional[str] = Field(None, description="Secure OTLP ingest token for gateway authentication")
    owner_user_id: Optional[str] = None
    owner_username: Optional[str] = None
    is_shared: bool = False
    can_use: bool = True
    shared_with: List[ApiKeyShareUser] = Field(default_factory=list)
    is_default: bool = False
    is_enabled: bool = True
    is_hidden: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
