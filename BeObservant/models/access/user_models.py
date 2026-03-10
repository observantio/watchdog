from datetime import datetime
import re
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from config import config
from .api_key_models import ApiKey
from .auth_models import Permission, Role

_USERNAME_RE = re.compile(r'^[a-z0-9._-]{3,50}$')


def _normalize_username(v: str, *, full_check: bool = True) -> str:
    if v is None:
        raise ValueError("username is required")
    if not isinstance(v, str):
        raise ValueError("username must be a string")
    uname = v.strip().lower()
    if " " in uname:
        raise ValueError("username must not contain spaces")
    if full_check and not _USERNAME_RE.match(uname):
        raise ValueError(
            "username must be 3-50 chars and contain only lowercase letters, "
            "numbers, dot, underscore or hyphen"
        )
    return uname


def _normalize_username_input(value: object, *, full_check: bool) -> str:
    if not isinstance(value, str):
        raise ValueError("username must be a string")
    return _normalize_username(value, full_check=full_check)

class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: Optional[str] = None
    org_id: str = Field(default=config.DEFAULT_ORG_ID, max_length=100, description="Organization ID for multi-tenant observability")
    role: Role = Role.USER
    group_ids: List[str] = Field(default_factory=list)
    is_active: bool = True

    @field_validator('username', mode='before')
    @classmethod
    def normalize_username(cls, v: object) -> str:
        return _normalize_username_input(v, full_check=True)

class UserCreate(UserBase):
    password: Optional[str] = Field(None, min_length=8)
    must_setup_mfa: Optional[bool] = False

class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    org_id: Optional[str] = None
    role: Optional[Role] = None
    group_ids: Optional[List[str]] = None
    is_active: Optional[bool] = None
    must_setup_mfa: Optional[bool] = None

    @field_validator("username", mode="before")
    @classmethod
    def normalize_update_username(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        return _normalize_username_input(v, full_check=True)

class UserPasswordUpdate(BaseModel):
    current_password: Optional[str] = None
    new_password: str = Field(..., min_length=8)

class User(UserBase):
    id: str
    tenant_id: str
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    needs_password_change: bool = False
    password_changed_at: Optional[datetime] = None
    session_invalid_before: Optional[datetime] = None
    grafana_user_id: Optional[int] = None
    api_keys: List[ApiKey] = Field(default_factory=list)
    mfa_enabled: bool = False
    must_setup_mfa: bool = False
    auth_provider: Optional[str] = "local"
    model_config = ConfigDict(from_attributes=True)

class UserInDB(User):
    hashed_password: str

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
    mfa_enabled: bool = False
    must_setup_mfa: bool = False
    auth_provider: Optional[str] = "local"

class LoginRequest(BaseModel):
    username: str
    password: str
    mfa_code: Optional[str] = None

    @field_validator('username', mode='before')
    @classmethod
    def normalize_login_username(cls, v: object) -> str:
        return _normalize_username_input(v, full_check=False)

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None

    @field_validator('username', mode='before')
    @classmethod
    def normalize_register_username(cls, v: object) -> str:
        return _normalize_username_input(v, full_check=True)

class TotpEnrollResponse(BaseModel):
    otpauth_url: str
    secret: str

class MfaVerifyRequest(BaseModel):
    code: str

class MfaDisableRequest(BaseModel):
    current_password: Optional[str] = None
    code: Optional[str] = None

class RecoveryCodesResponse(BaseModel):
    recovery_codes: List[str]

class TempPasswordResetResponse(BaseModel):
    temporary_password: str
    email_sent: bool
    message: str
