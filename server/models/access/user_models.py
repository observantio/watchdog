"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

User models.

Defines Pydantic models for user creation, update, and retrieval, including authentication-related models for login and MFA management.
"""
from enum import Enum
from typing import List, Optional, TYPE_CHECKING
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr, validator
import re

from config import config
from .auth_models import Role, Permission
from .api_key_models import ApiKey

if TYPE_CHECKING:
    pass

_USERNAME_RE = re.compile(r'^[a-z0-9._-]{3,50}$')


def _normalize_username(v: str, *, full_check: bool = True) -> str:
    """Shared username normalization used by multiple models.

    Args:
        v: Raw username value.
        full_check: When ``True``, enforce the strict regex pattern
            (required for registration/creation).  When ``False``,
            only strip/lowercase and reject spaces (sufficient for login).
    """
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


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: Optional[str] = None
    org_id: str = Field(default=config.DEFAULT_ORG_ID, max_length=100, description="Organization ID for multi-tenant observability")
    role: Role = Role.USER
    group_ids: List[str] = Field(default_factory=list)
    is_active: bool = True

    @validator('username', pre=True, always=True)
    def normalize_username(cls, v):
        return _normalize_username(v, full_check=True)


class UserCreate(UserBase):
    password: Optional[str] = Field(None, min_length=8)
    must_setup_mfa: Optional[bool] = False


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    org_id: Optional[str] = None
    role: Optional[Role] = None
    group_ids: Optional[List[str]] = None
    is_active: Optional[bool] = None
    must_setup_mfa: Optional[bool] = None


class UserPasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


class User(UserBase):
    id: str
    tenant_id: str
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    needs_password_change: bool = False
    grafana_user_id: Optional[int] = None
    api_keys: List[ApiKey] = Field(default_factory=list)
    mfa_enabled: bool = False
    must_setup_mfa: bool = False

    class Config:
        from_attributes = True


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


class LoginRequest(BaseModel):
    username: str
    password: str
    mfa_code: Optional[str] = None

    @validator('username', pre=True, always=True)
    def normalize_login_username(cls, v):
        return _normalize_username(v, full_check=False)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None

    @validator('username', pre=True, always=True)
    def normalize_register_username(cls, v):
        return _normalize_username(v, full_check=True)


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
