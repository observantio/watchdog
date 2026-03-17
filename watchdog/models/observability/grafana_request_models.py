"""
Grafana request models for Watchdog observability integration.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

class GrafanaBootstrapSessionRequest(BaseModel):
    next: Optional[str] = None

class GrafanaDatasourceQueryRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

class GrafanaDashboardPayloadRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

class GrafanaHiddenToggleRequest(BaseModel):
    hidden: bool = True

class GrafanaCreateFolderRequest(BaseModel):
    title: str
    allow_dashboard_writes: bool = Field(False, alias="allowDashboardWrites")
    model_config = ConfigDict(populate_by_name=True)


class GrafanaUpdateFolderRequest(BaseModel):
    title: Optional[str] = None
    allow_dashboard_writes: Optional[bool] = Field(None, alias="allowDashboardWrites")
    model_config = ConfigDict(populate_by_name=True)
