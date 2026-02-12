"""Grafana related models."""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum

class DatasourceType(str, Enum):
    """Datasource types."""
    PROMETHEUS = "prometheus"
    LOKI = "loki"
    TEMPO = "tempo"
    GRAPHITE = "graphite"
    INFLUXDB = "influxdb"
    ELASTICSEARCH = "elasticsearch"

DS_DISPLAY_NAME_DESC = "Display name of the datasource"
DS_URL_DESC = "URL of the datasource"
DS_IS_DEFAULT_DESC = "Whether this is the default datasource"
DS_JSON_DATA_DESC = "Additional JSON configuration"

class Datasource(BaseModel):
    """Datasource representation."""
    id: Optional[int] = Field(None, description="Unique identifier for the datasource")
    uid: Optional[str] = Field(None, description="Unique identifier string for the datasource")
    org_id: Optional[int] = Field(None, alias="orgId", description="Organization ID")
    name: str = Field(..., description=DS_DISPLAY_NAME_DESC)
    type: str = Field(..., description="Type of the datasource (e.g., prometheus, loki)")
    type_logo_url: Optional[str] = Field(None, alias="typeLogoUrl", description="URL to the datasource type logo")
    access: str = Field("proxy", description="Access mode (proxy or direct)")
    url: str = Field(..., description=DS_URL_DESC)
    password: Optional[str] = Field(None, description="Password for authentication")
    user: Optional[str] = Field(None, description="Username for authentication")
    database: Optional[str] = Field(None, description="Database name")
    basic_auth: bool = Field(False, alias="basicAuth", description="Whether to use basic authentication")
    basic_auth_user: Optional[str] = Field(None, alias="basicAuthUser", description="Basic auth username")
    basic_auth_password: Optional[str] = Field(None, alias="basicAuthPassword", description="Basic auth password")
    with_credentials: bool = Field(False, alias="withCredentials", description="Whether to send credentials with requests")
    is_default: bool = Field(False, alias="isDefault", description=DS_IS_DEFAULT_DESC)
    json_data: Optional[Dict[str, Any]] = Field(None, alias="jsonData", description=DS_JSON_DATA_DESC)
    secure_json_data: Optional[Dict[str, Any]] = Field(None, alias="secureJsonData", description="Secure JSON configuration")
    secure_json_fields: Optional[Dict[str, bool]] = Field(None, alias="secureJsonFields", description="Secure JSON fields metadata")
    version: Optional[int] = Field(None, description="Version of the datasource")
    read_only: bool = Field(False, alias="readOnly", description="Whether the datasource is read-only")
    # Extended fields for proxy server
    created_by: Optional[str] = Field(None, description="ID of the user who registered/created the datasource")
    is_hidden: bool = Field(False, description="Whether the datasource is hidden for the current user")
    is_owned: bool = Field(False, description="Whether the current user is the owner/creator")
    
    class Config:
        populate_by_name = True


class DatasourceCreate(BaseModel):
    """Create a new datasource."""
    name: str = Field(..., description=DS_DISPLAY_NAME_DESC)
    type: str = Field(..., description="Type of the datasource")
    url: str = Field(..., description=DS_URL_DESC)
    access: str = Field("proxy", description="Access mode")
    is_default: bool = Field(False, alias="isDefault", description=DS_IS_DEFAULT_DESC)
    org_id: Optional[str] = Field(None, description="Organization ID for multi-tenant datasources")
    json_data: Optional[Dict[str, Any]] = Field(None, alias="jsonData", description=DS_JSON_DATA_DESC)
    secure_json_data: Optional[Dict[str, Any]] = Field(None, alias="secureJsonData", description="Secure JSON configuration")
    
    class Config:
        populate_by_name = True


class DatasourceUpdate(BaseModel):
    """Update datasource."""
    name: Optional[str] = Field(None, description=DS_DISPLAY_NAME_DESC)
    url: Optional[str] = Field(None, description=DS_URL_DESC)
    access: Optional[str] = Field(None, description="Access mode")
    is_default: Optional[bool] = Field(None, alias="isDefault", description=DS_IS_DEFAULT_DESC)
    org_id: Optional[str] = Field(None, description="Organization ID for multi-tenant datasources")
    json_data: Optional[Dict[str, Any]] = Field(None, alias="jsonData", description=DS_JSON_DATA_DESC)
    secure_json_data: Optional[Dict[str, Any]] = Field(None, alias="secureJsonData", description="Secure JSON configuration")
    
    class Config:
        populate_by_name = True

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
    
    class Config:
        populate_by_name = True

class Folder(BaseModel):
    """Grafana folder."""
    id: Optional[int] = Field(None, description="Unique identifier for the folder")
    uid: Optional[str] = Field(None, description="Unique identifier string for the folder")
    title: str = Field(..., description="Title of the folder")
    
    class Config:
        populate_by_name = True
