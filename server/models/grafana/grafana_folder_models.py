"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


"""Grafana folder model (split from grafana_models.py)."""
from typing import Optional
from pydantic import BaseModel, Field


class Folder(BaseModel):
    """Grafana folder."""
    id: Optional[int] = Field(None, description="Unique identifier for the folder")
    uid: Optional[str] = Field(None, description="Unique identifier string for the folder")
    title: str = Field(..., description="Title of the folder")
    
    class Config:
        populate_by_name = True
