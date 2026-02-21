"""
Pydantic models for AlertManager API request payloads, particularly
Jira integration and rule import related structures.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class JiraCreateRequest(BaseModel):
    integrationId: str
    projectKey: str
    issueType: Optional[str] = "Task"
    summary: Optional[str] = None
    description: Optional[str] = None


class JiraConfigRequest(BaseModel):
    enabled: bool = True
    baseUrl: str
    email: Optional[str] = None
    apiToken: Optional[str] = None
    bearerToken: Optional[str] = None


class RuleImportRequest(BaseModel):
    yamlContent: str
    dryRun: bool = False
    defaults: Optional[Dict[str, object]] = None


class JiraIntegrationCreateRequest(BaseModel):
    name: str
    visibility: str = "private"
    sharedGroupIds: List[str] = Field(default_factory=list)
    enabled: bool = True
    baseUrl: Optional[str] = None
    email: Optional[str] = None
    apiToken: Optional[str] = None
    bearerToken: Optional[str] = None
    authMode: Optional[str] = "api_token"
    supportsSso: bool = False


class JiraIntegrationUpdateRequest(BaseModel):
    name: Optional[str] = None
    visibility: Optional[str] = None
    sharedGroupIds: Optional[List[str]] = None
    enabled: Optional[bool] = None
    baseUrl: Optional[str] = None
    email: Optional[str] = None
    apiToken: Optional[str] = None
    bearerToken: Optional[str] = None
    authMode: Optional[str] = None
    supportsSso: Optional[bool] = None


class JiraCommentRequest(BaseModel):
    text: str
