"""
Module defines Pydantic models for Grafana datasource-related data structures used in the API layer.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


from typing import Dict, Optional, Any, List
from pydantic import BaseModel, ConfigDict, Field
from enum import Enum

DS_DISPLAY_NAME_DESC = "Display name of the datasource"
DS_URL_DESC = "URL of the datasource"
DS_IS_DEFAULT_DESC = "Whether this is the default datasource"
DS_JSON_DATA_DESC = "Additional JSON configuration"

class DatasourceType(str, Enum):
    PROMETHEUS = "prometheus"
    LOKI = "loki"
    TEMPO = "tempo"
    GRAPHITE = "graphite"
    INFLUXDB = "influxdb"
    ELASTICSEARCH = "elasticsearch"

class Datasource(BaseModel):
    id: Optional[int] = Field(None, description="Unique identifier for the datasource")
    uid: Optional[str] = Field(None, description="Unique identifier string for the datasource")
    org_id: Optional[int] = Field(None, alias="orgId", description="Organization ID")
    name: str = Field(..., description=DS_DISPLAY_NAME_DESC)
    type: str = Field(..., description="Type of the datasource (prometheus, loki)")
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
    created_by: Optional[str] = Field(None, description="ID of the user who registered/created the datasource")
    is_hidden: bool = Field(False, description="Whether the datasource is hidden for the current user")
    is_owned: bool = Field(False, description="Whether the current user is the owner/creator")
    visibility: Optional[str] = Field(None, description="Visibility for the datasource (private|group|tenant|public)")
    shared_group_ids: List[str] = Field(default_factory=list, alias="shared_group_ids", description="IDs of groups shared with this datasource")
    model_config = ConfigDict(populate_by_name=True)


class DatasourceCreate(BaseModel):
    name: str = Field(..., description=DS_DISPLAY_NAME_DESC)
    type: str = Field(..., description="Type of the datasource")
    url: str = Field(..., description=DS_URL_DESC)
    access: str = Field("proxy", description="Access mode")
    is_default: bool = Field(False, alias="isDefault", description=DS_IS_DEFAULT_DESC)
    org_id: Optional[str] = Field(None, alias="orgId", description="Organization ID for multi-tenant datasources")
    json_data: Optional[Dict[str, Any]] = Field(None, alias="jsonData", description=DS_JSON_DATA_DESC)
    secure_json_data: Optional[Dict[str, Any]] = Field(None, alias="secureJsonData", description="Secure JSON configuration")
    model_config = ConfigDict(populate_by_name=True)


class DatasourceUpdate(BaseModel):
    name: Optional[str] = Field(None, description=DS_DISPLAY_NAME_DESC)
    url: Optional[str] = Field(None, description=DS_URL_DESC)
    access: Optional[str] = Field(None, description="Access mode")
    is_default: Optional[bool] = Field(None, alias="isDefault", description=DS_IS_DEFAULT_DESC)
    org_id: Optional[str] = Field(None, alias="orgId", description="Organization ID for multi-tenant datasources")
    json_data: Optional[Dict[str, Any]] = Field(None, alias="jsonData", description=DS_JSON_DATA_DESC)
    secure_json_data: Optional[Dict[str, Any]] = Field(None, alias="secureJsonData", description="Secure JSON configuration")
    model_config = ConfigDict(populate_by_name=True)
