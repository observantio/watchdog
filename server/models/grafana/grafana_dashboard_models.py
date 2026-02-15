"""Grafana dashboard models (split from grafana_models.py)."""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class DashboardMeta(BaseModel):
    """Dashboard metadata."""
    is_starred: bool = Field(False, alias="isStarred", description="Whether the dashboard is starred")
    slug: Optional[str] = Field(None, description="URL slug of the dashboard")
    folder: Optional[int] = Field(None, description="Folder ID containing the dashboard")
    url: Optional[str] = Field(None, description="URL of the dashboard")
    version: Optional[int] = Field(None, description="Version number of the dashboard")
    
    class Config:
        populate_by_name = True


class Dashboard(BaseModel):
    """Dashboard representation."""
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
    
    class Config:
        populate_by_name = True


class DashboardCreate(BaseModel):
    """Create a new dashboard."""
    dashboard: Dashboard = Field(..., description="Dashboard configuration")
    folder_id: int = Field(0, alias="folderId", description="ID of the folder to create the dashboard in")
    overwrite: bool = Field(False, description="Whether to overwrite existing dashboard")
    message: Optional[str] = Field(None, description="Commit message for the dashboard creation")
    
    class Config:
        populate_by_name = True


class DashboardUpdate(BaseModel):
    """Update dashboard."""
    dashboard: Dashboard = Field(..., description="Updated dashboard configuration")
    folder_id: Optional[int] = Field(None, alias="folderId", description="ID of the folder containing the dashboard")
    overwrite: bool = Field(True, description="Whether to overwrite existing dashboard")
    message: Optional[str] = Field(None, description="Commit message for the dashboard update")
    
    class Config:
        populate_by_name = True


class DashboardSearchResult(BaseModel):
    """Dashboard search result."""
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

    # Extended fields for proxy server
    created_by: Optional[str] = Field(None, description="ID of the user who registered/created the dashboard")
    is_hidden: bool = Field(False, description="Whether the dashboard is hidden for the current user")
    is_owned: bool = Field(False, description="Whether the current user is the owner/creator")
    visibility: Optional[str] = Field(None, description="Visibility for the dashboard (private|group|tenant|public)")
    shared_group_ids: List[str] = Field(default_factory=list, alias="shared_group_ids")
    sharedGroupIds: List[str] = Field(default_factory=list, alias="sharedGroupIds")

    class Config:
        populate_by_name = True
