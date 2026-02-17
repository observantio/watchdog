"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


"""API Key models."""
from typing import Optional
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


class ApiKey(ApiKeyBase):
    id: str
    key: str
    otlp_token: Optional[str] = Field(None, description="Secure OTLP ingest token for gateway authentication")
    is_default: bool = False
    is_enabled: bool = True
    created_at: datetime
    updated_at: Optional[datetime] = None