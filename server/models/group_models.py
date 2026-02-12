"""Group models."""
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class GroupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class GroupCreate(GroupBase):
    pass


class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class GroupMembersUpdate(BaseModel):
    user_ids: List[str] = Field(default_factory=list)


class PermissionInfo(BaseModel):
    id: str
    name: str
    display_name: str
    description: Optional[str] = None
    resource_type: str
    action: str

    class Config:
        from_attributes = True


class Group(GroupBase):
    id: str
    tenant_id: str
    created_at: datetime
    updated_at: datetime
    permissions: List[PermissionInfo] = Field(default_factory=list)

    class Config:
        from_attributes = True