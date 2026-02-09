from enum import Enum
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr

from config import config

class Role(str, Enum):
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"

class Permission(str, Enum):
    READ_ALERTS = "read:alerts"
    WRITE_ALERTS = "write:alerts"
    DELETE_ALERTS = "delete:alerts"
    READ_CHANNELS = "read:channels"
    WRITE_CHANNELS = "write:channels"
    DELETE_CHANNELS = "delete:channels"
    READ_LOGS = "read:logs"
    READ_TRACES = "read:traces"
    READ_DASHBOARDS = "read:dashboards"
    WRITE_DASHBOARDS = "write:dashboards"
    DELETE_DASHBOARDS = "delete:dashboards"
    READ_AGENTS = "read:agents"
    MANAGE_USERS = "manage:users"
    READ_USERS = "read:users"
    MANAGE_GROUPS = "manage:groups"
    READ_GROUPS = "read:groups"
    MANAGE_TENANTS = "manage:tenants"

ROLE_PERMISSIONS = {
    Role.ADMIN: list(Permission),
    Role.USER: [
        Permission.READ_ALERTS,
        Permission.READ_CHANNELS,
        Permission.READ_LOGS,
        Permission.READ_TRACES,
        Permission.READ_DASHBOARDS,
        Permission.READ_AGENTS,
        Permission.READ_USERS,
        Permission.READ_GROUPS
    ],
    Role.VIEWER: []
}


class GroupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class GroupCreate(GroupBase):
    pass


class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


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


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: Optional[str] = None
    org_id: str = Field(default=config.DEFAULT_ORG_ID, max_length=100, description="Organization ID for multi-tenant observability")
    role: Role = Role.USER
    group_ids: List[str] = Field(default_factory=list)
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    org_id: Optional[str] = None
    role: Optional[Role] = None
    group_ids: Optional[List[str]] = None
    is_active: Optional[bool] = None


class UserPasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


class ApiKeyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class ApiKeyCreate(ApiKeyBase):
    key: Optional[str] = Field(None, min_length=3, max_length=200, description="Optional custom API key value")


class ApiKeyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_enabled: Optional[bool] = None
    is_default: Optional[bool] = None


class ApiKey(ApiKeyBase):
    id: str
    key: str
    is_default: bool = False
    is_enabled: bool = True
    created_at: datetime
    updated_at: Optional[datetime] = None


class User(UserBase):
    id: str
    tenant_id: str
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    needs_password_change: bool = False
    api_keys: List[ApiKey] = Field(default_factory=list)

    class Config:
        from_attributes = True


class UserInDB(User):
    hashed_password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    user_id: str
    username: str
    tenant_id: str
    org_id: str  # Organization ID for multi-tenant observability
    role: Role
    is_superuser: bool = False
    permissions: List[str]  # Changed to List[str] for flexibility
    group_ids: List[str] = Field(default_factory=list)  # User's group IDs


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: Optional[str]
    role: Role
    group_ids: List[str]
    is_active: bool
    org_id: str
    tenant_id: str
    created_at: datetime
    last_login: Optional[datetime]
    permissions: List[Permission]
    direct_permissions: List[str] = Field(default_factory=list)
    needs_password_change: bool = False
    api_keys: List[ApiKey] = Field(default_factory=list)
