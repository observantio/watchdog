"""
Module defines Pydantic models for Grafana folder-related data structures used in the API layer.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

class Folder(BaseModel):
    id: Optional[int] = Field(None, description="Unique identifier for the folder")
    uid: Optional[str] = Field(None, description="Unique identifier string for the folder")
    title: str = Field(..., description="Title of the folder")
    version: Optional[int] = Field(None, description="Current folder version")
    created_by: Optional[str] = Field(None, description="ID of the user who created the folder")
    visibility: str = Field("tenant", description="Visibility for the folder (private|group|tenant)")
    shared_group_ids: List[str] = Field(default_factory=list, alias="sharedGroupIds")
    allow_dashboard_writes: bool = Field(False, alias="allowDashboardWrites")
    is_hidden: bool = Field(False, alias="isHidden")
    is_owned: bool = Field(False, description="Whether the current user owns the folder")
    model_config = ConfigDict(populate_by_name=True)
