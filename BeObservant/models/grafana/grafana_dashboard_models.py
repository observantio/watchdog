"""
Module defines Pydantic models for Grafana dashboard-related data structures used in the API layer.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, ConfigDict, Field

class DashboardMeta(BaseModel):
    is_starred: bool = Field(False, alias="isStarred", description="Whether the dashboard is starred")
    slug: Optional[str] = Field(None, description="URL slug of the dashboard")
    folder: Optional[int] = Field(None, description="Folder ID containing the dashboard")
    url: Optional[str] = Field(None, description="URL of the dashboard")
    version: Optional[int] = Field(None, description="Version number of the dashboard")
    model_config = ConfigDict(populate_by_name=True)

class Dashboard(BaseModel):
    id: Optional[int] = Field(None, description="Unique identifier for the dashboard")
    uid: Optional[str] = Field(None, description="Unique identifier string for the dashboard")
    title: str = Field(..., description="Title of the dashboard")
    tags: List[str] = Field(default_factory=list, description="Tags associated with the dashboard")
    timezone: str = Field("browser", description="Timezone setting for the dashboard")
    schema_version: int = Field(16, alias="schemaVersion", description="Schema version of the dashboard")
    version: Optional[int] = Field(None, description="Version number of the dashboard")
    refresh: Optional[str] = Field(None, description="Auto-refresh interval")
    panels: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="List of panels in the dashboard")
    templating: Optional[Dict[str, Any]] = Field(None, description="Template variables configuration")
    time: Optional[Dict[str, Any]] = Field(None, description="Time range configuration")
    time_picker: Optional[Dict[str, Any]] = Field(None, alias="timePicker", description="Time picker configuration")
    editable: bool = Field(True, description="Whether the dashboard is editable")
    model_config = ConfigDict(populate_by_name=True)

class DashboardCreate(BaseModel):
    dashboard: Dashboard = Field(..., description="Dashboard configuration")
    folder_id: int = Field(0, alias="folderId", description="ID of the folder to create the dashboard in")
    overwrite: bool = Field(False, description="Whether to overwrite existing dashboard")
    message: Optional[str] = Field(None, description="Commit message for the dashboard creation")
    model_config = ConfigDict(populate_by_name=True)

class DashboardUpdate(BaseModel):
    dashboard: Dashboard = Field(..., description="Updated dashboard configuration")
    folder_id: Optional[int] = Field(None, alias="folderId", description="ID of the folder containing the dashboard")
    overwrite: bool = Field(True, description="Whether to overwrite existing dashboard")
    message: Optional[str] = Field(None, description="Commit message for the dashboard update")
    model_config = ConfigDict(populate_by_name=True)

class DashboardSearchResult(BaseModel):
    id: int = Field(..., description="Unique identifier for the dashboard")
    uid: str = Field(..., description="Unique identifier string for the dashboard")
    title: str = Field(..., description="Title of the dashboard")
    uri: str = Field(..., description="URI of the dashboard")
    url: str = Field(..., description="URL of the dashboard")
    slug: str = Field(..., description="URL slug of the dashboard")
    type: str = Field(..., description="Type of the item (dashboard)")
    tags: List[str] = Field(default_factory=list, description="Tags associated with the dashboard")
    is_starred: bool = Field(False, alias="isStarred", description="Whether the dashboard is starred")
    folder_id: Optional[int] = Field(None, alias="folderId", description="ID of the containing folder")
    folder_uid: Optional[str] = Field(None, alias="folderUid", description="UID of the containing folder")
    folder_title: Optional[str] = Field(None, alias="folderTitle", description="Title of the containing folder")
    created_by: Optional[str] = Field(None, description="ID of the user who registered/created the dashboard")
    is_hidden: bool = Field(False, description="Whether the dashboard is hidden for the current user")
    is_owned: bool = Field(False, description="Whether the current user is the owner/creator")
    visibility: str = Field("private", description="Visibility (private|group|tenant|public)")
    shared_group_ids: List[str] = Field(default_factory=list, alias="sharedGroupIds")

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
    )