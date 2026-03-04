"""
Request models for Grafana router endpoints.
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
