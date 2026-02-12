"""Authentication models."""
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, EmailStr, validator
import re

from config import config

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


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    user_id: str
    username: str
    tenant_id: str
    org_id: str
    role: Role
    is_superuser: bool = False
    permissions: List[str]
    group_ids: List[str] = Field(default_factory=list)
