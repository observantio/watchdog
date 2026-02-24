"""
Request models for Grafana router endpoints.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


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
