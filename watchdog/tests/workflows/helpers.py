"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from types import SimpleNamespace
from typing import Any

from models.access.api_key_models import ApiKey, ApiKeyShareUser, ApiKeyUpdate
from models.access.auth_models import Permission, ROLE_PERMISSIONS, Role, Token, TokenData
from models.access.group_models import Group
from models.access.group_models import PermissionInfo
from models.access.user_models import UserResponse
from models.grafana.grafana_datasource_models import Datasource, DatasourceCreate, DatasourceUpdate
from models.grafana.grafana_folder_models import Folder


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class UserState:
    id: str
    username: str
    email: str
    full_name: str
    tenant_id: str
    org_id: str
    role: Role
    permissions: list[str]
    group_ids: list[str] = field(default_factory=list)
    is_active: bool = True
    is_superuser: bool = False
    mfa_enabled: bool = False
    must_setup_mfa: bool = False
    password: str = "password123"
    created_at: datetime = field(default_factory=utcnow)
    hidden_api_key_ids: set[str] = field(default_factory=set)

    def as_runtime(self) -> SimpleNamespace:
        return SimpleNamespace(
            id=self.id,
            username=self.username,
            email=self.email,
            full_name=self.full_name,
            tenant_id=self.tenant_id,
            org_id=self.org_id,
            role=self.role,
            group_ids=list(self.group_ids),
            is_active=self.is_active,
            is_superuser=self.is_superuser,
            mfa_enabled=self.mfa_enabled,
            must_setup_mfa=self.must_setup_mfa,
            created_at=self.created_at,
        )


@dataclass
class ApiKeyState:
    id: str
    owner_user_id: str
    owner_username: str
    name: str
    key: str
    otlp_token: str
    is_default: bool = False
    is_enabled: bool = True
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime | None = None
    shared_user_ids: set[str] = field(default_factory=set)
    shared_group_ids: set[str] = field(default_factory=set)


@dataclass
class FolderState:
    id: int
    uid: str
    title: str
    created_by: str
    tenant_id: str
    visibility: str
    shared_group_ids: list[str]
    allow_dashboard_writes: bool
    version: int = 1
    hidden_by: set[str] = field(default_factory=set)


@dataclass
class DatasourceState:
    id: int
    uid: str
    name: str
    type: str
    url: str
    created_by: str
    tenant_id: str
    visibility: str
    shared_group_ids: list[str]
    version: int = 1
    is_default: bool = False
    hidden_by: set[str] = field(default_factory=set)


@dataclass
class DashboardState:
    id: int
    uid: str
    title: str
    created_by: str
    tenant_id: str
    visibility: str
    shared_group_ids: list[str]
    folder_uid: str | None = None
    folder_id: int | None = None
    version: int = 1
    hidden_by: set[str] = field(default_factory=set)


class WorkflowState:
    def __init__(self, *, admin_requires_mfa: bool = False) -> None:
        self._lock = RLock()
        self.tenant_id = "tenant-a"
        self.org_id = "org-a"
        self.users: dict[str, UserState] = {}
        self.groups: dict[str, Group] = {}
        self.tokens: dict[str, TokenData] = {}
        self.api_keys: dict[str, ApiKeyState] = {}
        self.folders: dict[str, FolderState] = {}
        self.datasources: dict[str, DatasourceState] = {}
        self.dashboards: dict[str, DashboardState] = {}
        self.audit_rows: list[tuple[Any, str, str]] = []
        self.next_user_id = 2
        self.next_group_id = 1
        self.next_api_key_id = 1
        self.next_folder_id = 1
        self.next_datasource_id = 1
        self.next_dashboard_id = 1
        self._add_user(
            user_id="u-admin",
            username="admin",
            email="admin@example.com",
            full_name="Admin",
            role=Role.ADMIN,
            permissions=[permission.value for permission in Permission],
            is_superuser=True,
            must_setup_mfa=admin_requires_mfa,
            mfa_enabled=not admin_requires_mfa,
            password="secret-pass",
        )

    def _permission_enums(self, permission_names: list[str]) -> list[Permission]:
        return [Permission(name) for name in permission_names]

    def _sync_user_tokens(self, user: UserState) -> None:
        with self._lock:
            self.tokens[f"token-{user.id}"] = self._token_data_for_user(user)
            self.tokens[f"setup-{user.id}"] = self._token_data_for_user(user, is_mfa_setup=True)

    def _add_user(
        self,
        *,
        user_id: str,
        username: str,
        email: str,
        full_name: str,
        role: Role,
        permissions: list[str],
        is_superuser: bool = False,
        must_setup_mfa: bool = False,
        mfa_enabled: bool = False,
        group_ids: list[str] | None = None,
        password: str = "password123",
    ) -> UserState:
        with self._lock:
            user = UserState(
                id=user_id,
                username=username,
                email=email,
                full_name=full_name,
                tenant_id=self.tenant_id,
                org_id=self.org_id,
                role=role,
                permissions=list(permissions),
                group_ids=list(group_ids or []),
                is_superuser=is_superuser,
                must_setup_mfa=must_setup_mfa,
                mfa_enabled=mfa_enabled,
                password=password,
            )
            self.users[user_id] = user
            self._sync_user_tokens(user)
            return user

    def _token_data_for_user(self, user: UserState, *, is_mfa_setup: bool = False) -> TokenData:
        return TokenData(
            user_id=user.id,
            username=user.username,
            tenant_id=user.tenant_id,
            org_id=user.org_id,
            role=user.role,
            is_superuser=user.is_superuser,
            permissions=list(user.permissions),
            group_ids=list(user.group_ids),
            iat=1,
            is_mfa_setup=is_mfa_setup,
        )

    def auth_header(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def decode_token(self, token: str) -> TokenData | None:
        with self._lock:
            token_data = self.tokens.get(token)
            return token_data.model_copy(deep=True) if token_data else None

    def get_user_by_id(self, user_id: str) -> SimpleNamespace | None:
        with self._lock:
            user = self.users.get(user_id)
            return user.as_runtime() if user else None

    def get_user_by_id_in_tenant(self, user_id: str, tenant_id: str) -> SimpleNamespace | None:
        with self._lock:
            user = self.users.get(user_id)
            if user is None or user.tenant_id != tenant_id:
                return None
            return user.as_runtime()

    def get_user_permissions(self, user: object) -> list[str]:
        with self._lock:
            user_id = str(getattr(user, "id", "") or getattr(user, "user_id", ""))
            state = self.users.get(user_id)
            return list(state.permissions if state else [])

    def is_external_auth_enabled(self) -> bool:
        return False

    def is_password_auth_enabled(self) -> bool:
        return True

    def login(self, username: str, password: str, mfa_code: str | None = None) -> Token | dict[str, Any] | None:
        with self._lock:
            user = next((item for item in self.users.values() if item.username == username), None)
            if user is None or not user.is_active or user.password != password:
                return None
            if user.must_setup_mfa and not user.mfa_enabled:
                return {"mfa_setup_required": True, "setup_token": f"setup-{user.id}"}
            if user.mfa_enabled:
                if not mfa_code:
                    return {"mfa_required": True}
                if mfa_code != "123456":
                    return None
            return Token(access_token=f"token-{user.id}", expires_in=3600)

    def enroll_totp(self, user_id: str) -> dict[str, str]:
        if user_id not in self.users:
            raise ValueError("user not found")
        return {
            "secret": "ABC123",
            "otpauth_url": "otpauth://totp/watchdog:admin?secret=ABC123",
        }

    def verify_enable_totp(self, user_id: str, code: str) -> list[str]:
        if code != "123456":
            raise ValueError("Invalid TOTP code")
        with self._lock:
            user = self.users[user_id]
            user.mfa_enabled = True
            user.must_setup_mfa = False
            self._sync_user_tokens(user)
            return ["recovery-1", "recovery-2"]

    def disable_totp(self, user_id: str, *, current_password: str | None = None, code: str | None = None) -> bool:
        with self._lock:
            user = self.users.get(user_id)
            if user is None or not user.mfa_enabled:
                return False
            if current_password and current_password != user.password:
                return False
            if code and code != "123456":
                return False
            user.mfa_enabled = False
            self._sync_user_tokens(user)
            return True

    def reset_totp(self, user_id: str, _admin_id: str) -> bool:
        with self._lock:
            user = self.users.get(user_id)
            if user is None:
                return False
            user.mfa_enabled = False
            user.must_setup_mfa = True
            self._sync_user_tokens(user)
            return True

    def create_user(self, payload: Any, tenant_id: str, *_args: Any) -> SimpleNamespace:
        with self._lock:
            user_id = f"u-{self.next_user_id}"
            self.next_user_id += 1
            role = getattr(payload, "role", Role.USER)
            permissions = [permission.value for permission in ROLE_PERMISSIONS[role]]
            user = self._add_user(
                user_id=user_id,
                username=payload.username,
                email=payload.email,
                full_name=getattr(payload, "full_name", None) or payload.username,
                role=role,
                permissions=permissions,
                group_ids=list(getattr(payload, "group_ids", []) or []),
                password=getattr(payload, "password", None) or "password123",
            )
            user.tenant_id = tenant_id
            user.org_id = getattr(payload, "org_id", self.org_id) or self.org_id
            self._sync_user_tokens(user)
            return user.as_runtime()

    def build_user_response(self, user: object, _permissions: list[str]) -> UserResponse:
        with self._lock:
            state = self.users[str(getattr(user, "id"))]
            return UserResponse(
                id=state.id,
                username=state.username,
                email=state.email,
                full_name=state.full_name,
                role=state.role,
                group_ids=list(state.group_ids),
                is_active=state.is_active,
                org_id=state.org_id,
                tenant_id=state.tenant_id,
                created_at=state.created_at,
                last_login=None,
                permissions=self._permission_enums(state.permissions),
                direct_permissions=[],
                needs_password_change=False,
                api_keys=[],
                mfa_enabled=state.mfa_enabled,
                must_setup_mfa=state.must_setup_mfa,
                auth_provider="local",
            )

    def get_user_by_username(self, username: str) -> SimpleNamespace | None:
        with self._lock:
            user = next((item for item in self.users.values() if item.username == username), None)
            return user.as_runtime() if user else None

    def list_users(self, tenant_id: str, limit: int = 100, offset: int = 0) -> list[SimpleNamespace]:
        with self._lock:
            users = [user for user in self.users.values() if user.tenant_id == tenant_id]
            return [user.as_runtime() for user in users[offset : offset + limit]]

    def update_user(self, user_id: str, payload: Any, tenant_id: str, *_args: Any) -> SimpleNamespace | None:
        with self._lock:
            user = self.users.get(user_id)
            if user is None or user.tenant_id != tenant_id:
                return None
            data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else dict(payload)
            for field_name, value in data.items():
                if field_name == "permissions":
                    continue
                if value is None:
                    continue
                setattr(user, field_name, value)
            self._sync_user_tokens(user)
            return user.as_runtime()

    def update_password(self, user_id: str, payload: Any, tenant_id: str) -> bool:
        with self._lock:
            user = self.users.get(user_id)
            if user is None or user.tenant_id != tenant_id:
                return False
            current_password = getattr(payload, "current_password", None)
            if current_password is not None and current_password != user.password:
                return False
            user.password = payload.new_password
            return True

    def reset_user_password_temp(self, actor_user_id: str, target_user_id: str, tenant_id: str) -> dict[str, str]:
        del actor_user_id
        with self._lock:
            user = self.users[target_user_id]
            if user.tenant_id != tenant_id:
                raise ValueError("target user not in tenant")
            user.password = "Temp-Password-123"
            return {
                "temporary_password": user.password,
                "target_email": user.email,
                "target_username": user.username,
            }

    def delete_user(self, user_id: str, tenant_id: str, _actor_user_id: str) -> bool:
        with self._lock:
            user = self.users.get(user_id)
            if user is None or user.tenant_id != tenant_id:
                return False
            self.users.pop(user_id, None)
            self.tokens.pop(f"token-{user_id}", None)
            self.tokens.pop(f"setup-{user_id}", None)
            return True

    def update_user_permissions(
        self,
        user_id: str,
        permission_names: list[str],
        tenant_id: str,
        *_args: Any,
    ) -> bool:
        with self._lock:
            user = self.users.get(user_id)
            if user is None or user.tenant_id != tenant_id:
                return False
            user.permissions = sorted({str(name) for name in permission_names})
            self._sync_user_tokens(user)
            return True

    def list_all_permissions(self) -> list[dict[str, object]]:
        return [{"name": permission.value, "resource_type": permission.value.split(":", 1)[-1]} for permission in Permission]

    def list_groups(self, tenant_id: str, *_args: Any, **_kwargs: Any) -> list[Group]:
        with self._lock:
            return [group for group in self.groups.values() if group.tenant_id == tenant_id]

    def create_group(self, payload: Any, tenant_id: str, *_args: Any) -> Group:
        with self._lock:
            group_id = f"g-{self.next_group_id}"
            self.next_group_id += 1
            group = Group(
                id=group_id,
                tenant_id=tenant_id,
                name=payload.name,
                description=getattr(payload, "description", None),
                created_at=utcnow(),
                updated_at=utcnow(),
                permissions=[],
            )
            self.groups[group_id] = group
            return group

    def get_group(self, group_id: str, tenant_id: str, *_args: Any, **_kwargs: Any) -> Group | None:
        with self._lock:
            group = self.groups.get(group_id)
            if group is None or group.tenant_id != tenant_id:
                return None
            return group

    def update_group(self, group_id: str, payload: Any, tenant_id: str, *_args: Any, **_kwargs: Any) -> Group | None:
        with self._lock:
            group = self.get_group(group_id, tenant_id)
            if group is None:
                return None
            data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else dict(payload)
            updates = group.model_copy(update={key: value for key, value in data.items() if value is not None})
            updates.updated_at = utcnow()
            self.groups[group_id] = updates
            return updates

    def delete_group(self, group_id: str, tenant_id: str, *_args: Any, **_kwargs: Any) -> bool:
        with self._lock:
            group = self.get_group(group_id, tenant_id)
            if group is None:
                return False
            self.groups.pop(group_id, None)
            for user in self.users.values():
                user.group_ids = [existing for existing in user.group_ids if existing != group_id]
                self._sync_user_tokens(user)
            return True

    def update_group_permissions(self, group_id: str, permission_names: list[str], tenant_id: str, *_args: Any, **_kwargs: Any) -> bool:
        with self._lock:
            group = self.get_group(group_id, tenant_id)
            if group is None:
                return False
            updated = group.model_copy(
                update={
                    "permissions": [
                        PermissionInfo(id=name, name=name, display_name=name, description=None, resource_type="workflow", action="test")
                        for name in permission_names
                    ]
                }
            )
            self.groups[group_id] = updated
            return True

    def update_group_members(self, group_id: str, user_ids: list[str], *_args: Any, **_kwargs: Any) -> bool:
        with self._lock:
            if group_id not in self.groups:
                return False
            for user in self.users.values():
                user.group_ids = [existing for existing in user.group_ids if existing != group_id]
            for user_id in user_ids:
                user = self.users.get(user_id)
                if user is None:
                    continue
                user.group_ids.append(group_id)
                self._sync_user_tokens(user)
            return True

    def _api_key_visible_to_user(self, key: ApiKeyState, user: UserState, show_hidden: bool) -> bool:
        if key.owner_user_id == user.id:
            return show_hidden or key.id not in user.hidden_api_key_ids
        if user.id in key.shared_user_ids:
            return show_hidden or key.id not in user.hidden_api_key_ids
        return bool(set(user.group_ids).intersection(key.shared_group_ids)) and (show_hidden or key.id not in user.hidden_api_key_ids)

    def _api_key_model(self, key: ApiKeyState, user: UserState) -> ApiKey:
        shared_with = [
            ApiKeyShareUser(
                user_id=user_id,
                username=self.users[user_id].username,
                email=self.users[user_id].email,
                can_use=True,
                created_at=key.created_at,
            )
            for user_id in sorted(key.shared_user_ids)
            if user_id in self.users
        ]
        return ApiKey(
            id=key.id,
            name=key.name,
            key=key.key,
            otlp_token=key.otlp_token,
            owner_user_id=key.owner_user_id,
            owner_username=key.owner_username,
            is_shared=key.owner_user_id != user.id,
            can_use=(key.owner_user_id == user.id or user.id in key.shared_user_ids or bool(set(user.group_ids).intersection(key.shared_group_ids))),
            shared_with=shared_with,
            is_default=key.is_default,
            is_enabled=key.is_enabled,
            is_hidden=key.id in user.hidden_api_key_ids,
            created_at=key.created_at,
            updated_at=key.updated_at,
        )

    def list_api_keys(self, user_id: str, show_hidden: bool = False) -> list[ApiKey]:
        with self._lock:
            user = self.users[user_id]
            visible = [key for key in self.api_keys.values() if self._api_key_visible_to_user(key, user, show_hidden)]
            return [self._api_key_model(key, user) for key in sorted(visible, key=lambda item: item.id)]

    def create_api_key(self, user_id: str, _tenant_id: str, payload: Any) -> ApiKey:
        with self._lock:
            key_id = f"key-{self.next_api_key_id}"
            self.next_api_key_id += 1
            state = ApiKeyState(
                id=key_id,
                owner_user_id=user_id,
                owner_username=self.users[user_id].username,
                name=payload.name,
                key=str(getattr(payload, "key", None) or f"org-{self.next_api_key_id}"),
                otlp_token=f"otlp-{key_id}",
                is_default=not any(key.owner_user_id == user_id for key in self.api_keys.values()),
            )
            self.api_keys[key_id] = state
            return self._api_key_model(state, self.users[user_id])

    def update_api_key(self, user_id: str, key_id: str, payload: ApiKeyUpdate) -> ApiKey:
        with self._lock:
            key = self.api_keys[key_id]
            if key.owner_user_id != user_id:
                raise ValueError("API key not found")
            if payload.name is not None:
                key.name = payload.name
            if payload.is_enabled is not None:
                key.is_enabled = payload.is_enabled
            if payload.is_default is not None:
                key.is_default = payload.is_default
            key.updated_at = utcnow()
            return self._api_key_model(key, self.users[user_id])

    def regenerate_api_key_otlp_token(self, user_id: str, key_id: str) -> ApiKey:
        with self._lock:
            key = self.api_keys[key_id]
            if key.owner_user_id != user_id:
                raise ValueError("API key not found")
            key.otlp_token = f"regen-{key_id}"
            key.updated_at = utcnow()
            return self._api_key_model(key, self.users[user_id])

    def delete_api_key(self, user_id: str, key_id: str) -> bool:
        with self._lock:
            key = self.api_keys.get(key_id)
            if key is None or key.owner_user_id != user_id:
                return False
            self.api_keys.pop(key_id, None)
            return True

    def set_api_key_hidden(self, user_id: str, key_id: str, hidden: bool) -> None:
        with self._lock:
            user = self.users[user_id]
            if hidden:
                user.hidden_api_key_ids.add(key_id)
            else:
                user.hidden_api_key_ids.discard(key_id)

    def list_api_key_shares(self, user_id: str, _tenant_id: str, key_id: str) -> list[dict[str, object]]:
        with self._lock:
            key = self.api_keys[key_id]
            if key.owner_user_id != user_id:
                raise ValueError("API key not found")
            return [
                {
                    "user_id": shared_user_id,
                    "username": self.users[shared_user_id].username,
                    "email": self.users[shared_user_id].email,
                    "can_use": True,
                    "created_at": key.created_at,
                }
                for shared_user_id in sorted(key.shared_user_ids)
                if shared_user_id in self.users
            ]

    def replace_api_key_shares(
        self,
        user_id: str,
        _tenant_id: str,
        key_id: str,
        user_ids: list[str],
        group_ids: list[str],
    ) -> list[dict[str, object]]:
        with self._lock:
            key = self.api_keys[key_id]
            if key.owner_user_id != user_id:
                raise ValueError("API key not found")
            key.shared_user_ids = {item for item in user_ids if item in self.users}
            key.shared_group_ids = set(group_ids)
            key.updated_at = utcnow()
            return self.list_api_key_shares(user_id, self.tenant_id, key_id)

    def delete_api_key_share(self, user_id: str, _tenant_id: str, key_id: str, shared_user_id: str) -> bool:
        with self._lock:
            key = self.api_keys[key_id]
            if key.owner_user_id != user_id or shared_user_id not in key.shared_user_ids:
                return False
            key.shared_user_ids.discard(shared_user_id)
            key.updated_at = utcnow()
            return True

    def validate_otlp_token(self, token: str, *, suppress_errors: bool = True) -> str | None:
        del suppress_errors
        with self._lock:
            key = next((item for item in self.api_keys.values() if item.otlp_token == token), None)
            return key.key if key and key.is_enabled else None

    def _resource_visible(self, visibility: str, owner_id: str, tenant_id: str, shared_group_ids: list[str], current_user: TokenData) -> bool:
        if getattr(current_user, "is_superuser", False):
            return True
        if tenant_id != current_user.tenant_id:
            return False
        if owner_id == current_user.user_id:
            return True
        if visibility == "tenant":
            return True
        if visibility == "group":
            return bool(set(shared_group_ids).intersection(current_user.group_ids))
        return False

    def get_dashboard_metadata(self, **_kwargs: Any) -> dict[str, list[str]]:
        return {"visibility": ["private", "group", "tenant"]}

    def build_dashboard_search_context(self, _db: object, tenant_id: str, uid: str | None = None) -> dict[str, object]:
        dashboard = self.dashboards.get(uid or "")
        return {"uid_db_dashboard": dashboard if dashboard and dashboard.tenant_id == tenant_id else None}

    async def create_dashboard(
        self,
        *,
        dashboard_create: dict[str, Any],
        user_id: str,
        tenant_id: str,
        visibility: str,
        shared_group_ids: list[str],
        **_kwargs: Any,
    ) -> dict[str, Any]:
        payload = dashboard_create.get("dashboard", {}) if isinstance(dashboard_create, dict) else {}
        uid = str(payload.get("uid") or f"dash-{self.next_dashboard_id}")
        title = str(payload.get("title") or uid)
        folder_id = dashboard_create.get("folderId") if isinstance(dashboard_create, dict) else None
        folder_uid = None
        if folder_id is not None:
            folder_uid = next((folder.uid for folder in self.folders.values() if folder.id == folder_id), None)
        self.dashboards[uid] = DashboardState(
            id=self.next_dashboard_id,
            uid=uid,
            title=title,
            created_by=user_id,
            tenant_id=tenant_id,
            visibility=visibility,
            shared_group_ids=list(shared_group_ids),
            folder_uid=folder_uid,
            folder_id=folder_id,
        )
        self.next_dashboard_id += 1
        return {"id": self.dashboards[uid].id, "uid": uid, "status": "success", "slug": uid}

    async def update_dashboard(
        self,
        *,
        uid: str,
        dashboard_update: dict[str, Any],
        user_id: str,
        tenant_id: str,
        visibility: str | None,
        shared_group_ids: list[str] | None,
        is_admin: bool,
        **_kwargs: Any,
    ) -> dict[str, Any] | None:
        current_user = TokenData(user_id=user_id, username="user", tenant_id=tenant_id, org_id=self.org_id, role=Role.ADMIN if is_admin else Role.USER, is_superuser=is_admin, permissions=[], group_ids=list(self.users[user_id].group_ids))
        item = self.dashboards.get(uid)
        if item is None or not self._resource_visible(item.visibility, item.created_by, item.tenant_id, item.shared_group_ids, current_user):
            return None
        payload = dashboard_update.get("dashboard", {}) if isinstance(dashboard_update, dict) else {}
        item.title = str(payload.get("title") or item.title)
        if visibility is not None:
            item.visibility = visibility
        if shared_group_ids is not None:
            item.shared_group_ids = list(shared_group_ids)
        item.version += 1
        return {"id": item.id, "uid": uid, "status": "success", "version": item.version}

    async def delete_dashboard(self, *, uid: str, user_id: str, tenant_id: str, group_ids: list[str], **_kwargs: Any) -> bool:
        current_user = TokenData(user_id=user_id, username="user", tenant_id=tenant_id, org_id=self.org_id, role=Role.USER, permissions=[], group_ids=list(group_ids))
        item = self.dashboards.get(uid)
        if item is None or not self._resource_visible(item.visibility, item.created_by, item.tenant_id, item.shared_group_ids, current_user):
            return False
        self.dashboards.pop(uid, None)
        return True

    async def search_dashboards(self, *, user_id: str, tenant_id: str, group_ids: list[str], is_admin: bool, show_hidden: bool = False, **_kwargs: Any) -> list[dict[str, Any]]:
        current_user = TokenData(user_id=user_id, username=self.users[user_id].username, tenant_id=tenant_id, org_id=self.org_id, role=self.users[user_id].role, permissions=[], group_ids=list(group_ids), is_superuser=is_admin)
        items = []
        for item in self.dashboards.values():
            if user_id in item.hidden_by and not show_hidden:
                continue
            if not self._resource_visible(item.visibility, item.created_by, item.tenant_id, item.shared_group_ids, current_user):
                continue
            folder = self.folders.get(item.folder_uid or "") if item.folder_uid else None
            items.append(
                {
                    "id": item.id,
                    "uid": item.uid,
                    "title": item.title,
                    "uri": f"db/{item.uid}",
                    "url": f"/d/{item.uid}",
                    "slug": item.uid,
                    "type": "dash-db",
                    "tags": [],
                    "isStarred": False,
                    "folderId": item.folder_id,
                    "folderUid": item.folder_uid,
                    "folderTitle": folder.title if folder else None,
                    "created_by": item.created_by,
                    "is_hidden": user_id in item.hidden_by,
                    "is_owned": item.created_by == user_id,
                    "visibility": item.visibility,
                    "sharedGroupIds": list(item.shared_group_ids),
                }
            )
        return sorted(items, key=lambda item: item["uid"])

    async def get_dashboard(self, *, uid: str, user_id: str, tenant_id: str, group_ids: list[str], is_admin: bool, **_kwargs: Any) -> dict[str, Any] | None:
        current_user = TokenData(user_id=user_id, username=self.users[user_id].username, tenant_id=tenant_id, org_id=self.org_id, role=self.users[user_id].role, permissions=[], group_ids=list(group_ids), is_superuser=is_admin)
        item = self.dashboards.get(uid)
        if item is None or user_id in item.hidden_by:
            return None
        if not self._resource_visible(item.visibility, item.created_by, item.tenant_id, item.shared_group_ids, current_user):
            return None
        return {
            "dashboard": {"uid": item.uid, "title": item.title, "version": item.version},
            "meta": {"visibility": item.visibility, "sharedGroupIds": list(item.shared_group_ids)},
        }

    def toggle_dashboard_hidden(self, *, uid: str, user_id: str, hidden: bool, **_kwargs: Any) -> bool:
        item = self.dashboards.get(uid)
        if item is None:
            return False
        if hidden:
            item.hidden_by.add(user_id)
        else:
            item.hidden_by.discard(user_id)
        return True

    def get_datasource_metadata(self, **_kwargs: Any) -> dict[str, list[str]]:
        return {"types": ["loki", "tempo", "prometheus"]}

    def build_datasource_list_context(self, _db: object, **_kwargs: Any) -> dict[str, object]:
        return {"ok": True}

    async def create_datasource(
        self,
        *,
        datasource_create: DatasourceCreate,
        user_id: str,
        tenant_id: str,
        visibility: str,
        shared_group_ids: list[str],
        **_kwargs: Any,
    ) -> Datasource:
        uid = f"ds-{self.next_datasource_id}"
        item = DatasourceState(
            id=self.next_datasource_id,
            uid=uid,
            name=datasource_create.name,
            type=datasource_create.type,
            url=datasource_create.url,
            created_by=user_id,
            tenant_id=tenant_id,
            visibility=visibility,
            shared_group_ids=list(shared_group_ids),
            is_default=bool(datasource_create.is_default),
        )
        self.next_datasource_id += 1
        self.datasources[uid] = item
        return self._datasource_model(item, self.users[user_id])

    def _datasource_model(self, item: DatasourceState, user: UserState) -> Datasource:
        return Datasource(
            id=item.id,
            uid=item.uid,
            orgId=1,
            name=item.name,
            type=item.type,
            access="proxy",
            url=item.url,
            isDefault=item.is_default,
            version=item.version,
            created_by=item.created_by,
            is_hidden=user.id in item.hidden_by,
            is_owned=item.created_by == user.id,
            visibility=item.visibility,
            shared_group_ids=list(item.shared_group_ids),
        )

    async def get_datasource_by_name(self, *, name: str, user_id: str, tenant_id: str, group_ids: list[str], **_kwargs: Any) -> Datasource | None:
        item = next((entry for entry in self.datasources.values() if entry.name == name), None)
        if item is None:
            return None
        current = TokenData(user_id=user_id, username=self.users[user_id].username, tenant_id=tenant_id, org_id=self.org_id, role=self.users[user_id].role, permissions=[], group_ids=list(group_ids))
        if not self._resource_visible(item.visibility, item.created_by, item.tenant_id, item.shared_group_ids, current):
            return None
        return self._datasource_model(item, self.users[user_id])

    async def get_datasources(self, *, user_id: str, tenant_id: str, group_ids: list[str], show_hidden: bool = False, **_kwargs: Any) -> list[Datasource]:
        current = TokenData(user_id=user_id, username=self.users[user_id].username, tenant_id=tenant_id, org_id=self.org_id, role=self.users[user_id].role, permissions=[], group_ids=list(group_ids))
        results = []
        for item in self.datasources.values():
            if not self._resource_visible(item.visibility, item.created_by, item.tenant_id, item.shared_group_ids, current):
                continue
            if user_id in item.hidden_by and not show_hidden:
                continue
            results.append(self._datasource_model(item, self.users[user_id]))
        return results

    async def get_datasource(self, *, uid: str, user_id: str, tenant_id: str, group_ids: list[str], **_kwargs: Any) -> Datasource | None:
        item = self.datasources.get(uid)
        if item is None or user_id in item.hidden_by:
            return None
        current = TokenData(user_id=user_id, username=self.users[user_id].username, tenant_id=tenant_id, org_id=self.org_id, role=self.users[user_id].role, permissions=[], group_ids=list(group_ids))
        if not self._resource_visible(item.visibility, item.created_by, item.tenant_id, item.shared_group_ids, current):
            return None
        return self._datasource_model(item, self.users[user_id])

    async def update_datasource(self, *, uid: str, datasource_update: DatasourceUpdate, user_id: str, tenant_id: str, visibility: str | None, shared_group_ids: list[str] | None, **_kwargs: Any) -> Datasource | None:
        item = self.datasources.get(uid)
        if item is None or item.tenant_id != tenant_id:
            return None
        if datasource_update.name is not None:
            item.name = datasource_update.name
        if datasource_update.url is not None:
            item.url = datasource_update.url
        if visibility is not None:
            item.visibility = visibility
        if shared_group_ids is not None:
            item.shared_group_ids = list(shared_group_ids)
        item.version += 1
        return self._datasource_model(item, self.users[user_id])

    async def delete_datasource(self, *, uid: str, user_id: str, **_kwargs: Any) -> bool:
        item = self.datasources.get(uid)
        if item is None or item.created_by != user_id:
            return False
        self.datasources.pop(uid, None)
        return True

    def toggle_datasource_hidden(self, *, uid: str, user_id: str, hidden: bool, **_kwargs: Any) -> bool:
        item = self.datasources.get(uid)
        if item is None:
            return False
        if hidden:
            item.hidden_by.add(user_id)
        else:
            item.hidden_by.discard(user_id)
        return True

    async def enforce_datasource_query_access(self, **_kwargs: Any) -> None:
        return None

    async def query_datasource(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"results": payload}

    async def create_folder(
        self,
        *,
        title: str,
        user_id: str,
        tenant_id: str,
        visibility: str,
        shared_group_ids: list[str],
        allow_dashboard_writes: bool,
        **_kwargs: Any,
    ) -> Folder:
        uid = f"folder-{self.next_folder_id}"
        item = FolderState(
            id=self.next_folder_id,
            uid=uid,
            title=title,
            created_by=user_id,
            tenant_id=tenant_id,
            visibility=visibility,
            shared_group_ids=list(shared_group_ids),
            allow_dashboard_writes=allow_dashboard_writes,
        )
        self.next_folder_id += 1
        self.folders[uid] = item
        return self._folder_model(item, self.users[user_id])

    def _folder_model(self, item: FolderState, user: UserState) -> Folder:
        return Folder(
            id=item.id,
            uid=item.uid,
            title=item.title,
            version=item.version,
            created_by=item.created_by,
            visibility=item.visibility,
            sharedGroupIds=list(item.shared_group_ids),
            allowDashboardWrites=item.allow_dashboard_writes,
            isHidden=user.id in item.hidden_by,
            is_owned=item.created_by == user.id,
        )

    async def get_folders(self, *, user_id: str, tenant_id: str, group_ids: list[str], show_hidden: bool = False, is_admin: bool = False, **_kwargs: Any) -> list[Folder]:
        current = TokenData(user_id=user_id, username=self.users[user_id].username, tenant_id=tenant_id, org_id=self.org_id, role=self.users[user_id].role, permissions=[], group_ids=list(group_ids), is_superuser=is_admin)
        results = []
        for item in self.folders.values():
            if not self._resource_visible(item.visibility, item.created_by, item.tenant_id, item.shared_group_ids, current):
                continue
            if user_id in item.hidden_by and not show_hidden:
                continue
            results.append(self._folder_model(item, self.users[user_id]))
        return results

    async def get_folder(self, *, uid: str, user_id: str, tenant_id: str, group_ids: list[str], is_admin: bool = False, **_kwargs: Any) -> Folder | None:
        item = self.folders.get(uid)
        if item is None or user_id in item.hidden_by:
            return None
        current = TokenData(user_id=user_id, username=self.users[user_id].username, tenant_id=tenant_id, org_id=self.org_id, role=self.users[user_id].role, permissions=[], group_ids=list(group_ids), is_superuser=is_admin)
        if not self._resource_visible(item.visibility, item.created_by, item.tenant_id, item.shared_group_ids, current):
            return None
        return self._folder_model(item, self.users[user_id])

    async def update_folder(self, *, uid: str, user_id: str, tenant_id: str, title: str | None, visibility: str | None, shared_group_ids: list[str] | None, allow_dashboard_writes: bool | None, **_kwargs: Any) -> Folder | None:
        item = self.folders.get(uid)
        if item is None or item.tenant_id != tenant_id:
            return None
        if title is not None:
            item.title = title
        if visibility is not None:
            item.visibility = visibility
        if shared_group_ids is not None:
            item.shared_group_ids = list(shared_group_ids)
        if allow_dashboard_writes is not None:
            item.allow_dashboard_writes = allow_dashboard_writes
        item.version += 1
        return self._folder_model(item, self.users[user_id])

    async def delete_folder(self, *, uid: str, user_id: str, **_kwargs: Any) -> bool:
        item = self.folders.get(uid)
        if item is None or item.created_by != user_id:
            return False
        self.folders.pop(uid, None)
        return True

    def toggle_folder_hidden(self, *, uid: str, user_id: str, hidden: bool, **_kwargs: Any) -> bool:
        item = self.folders.get(uid)
        if item is None:
            return False
        if hidden:
            item.hidden_by.add(user_id)
        else:
            item.hidden_by.discard(user_id)
        return True


def patch_auth_service(monkeypatch: Any, state: WorkflowState) -> None:
    from middleware import dependencies

    monkeypatch.setattr(dependencies.auth_service, "decode_token", state.decode_token)
    monkeypatch.setattr(dependencies.auth_service, "get_user_by_id", state.get_user_by_id)
    monkeypatch.setattr(dependencies.auth_service, "get_user_by_id_in_tenant", state.get_user_by_id_in_tenant)
    monkeypatch.setattr(dependencies.auth_service, "get_user_permissions", state.get_user_permissions)
    monkeypatch.setattr(dependencies.auth_service, "is_external_auth_enabled", state.is_external_auth_enabled)
    monkeypatch.setattr(dependencies.auth_service, "is_password_auth_enabled", state.is_password_auth_enabled)
    monkeypatch.setattr(dependencies.auth_service, "login", state.login)
    monkeypatch.setattr(dependencies.auth_service, "enroll_totp", state.enroll_totp)
    monkeypatch.setattr(dependencies.auth_service, "verify_enable_totp", state.verify_enable_totp)
    monkeypatch.setattr(dependencies.auth_service, "disable_totp", state.disable_totp)
    monkeypatch.setattr(dependencies.auth_service, "reset_totp", state.reset_totp)
    monkeypatch.setattr(dependencies.auth_service, "create_user", state.create_user)
    monkeypatch.setattr(dependencies.auth_service, "build_user_response", state.build_user_response)
    monkeypatch.setattr(dependencies.auth_service, "get_user_by_username", state.get_user_by_username)
    monkeypatch.setattr(dependencies.auth_service, "list_users", state.list_users)
    monkeypatch.setattr(dependencies.auth_service, "update_user", state.update_user)
    monkeypatch.setattr(dependencies.auth_service, "update_password", state.update_password)
    monkeypatch.setattr(dependencies.auth_service, "reset_user_password_temp", state.reset_user_password_temp)
    monkeypatch.setattr(dependencies.auth_service, "delete_user", state.delete_user)
    monkeypatch.setattr(dependencies.auth_service, "update_user_permissions", state.update_user_permissions)
    monkeypatch.setattr(dependencies.auth_service, "list_all_permissions", state.list_all_permissions)
    monkeypatch.setattr(dependencies.auth_service, "list_groups", state.list_groups)
    monkeypatch.setattr(dependencies.auth_service, "create_group", state.create_group)
    monkeypatch.setattr(dependencies.auth_service, "get_group", state.get_group)
    monkeypatch.setattr(dependencies.auth_service, "update_group", state.update_group)
    monkeypatch.setattr(dependencies.auth_service, "delete_group", state.delete_group)
    monkeypatch.setattr(dependencies.auth_service, "update_group_permissions", state.update_group_permissions)
    monkeypatch.setattr(dependencies.auth_service, "update_group_members", state.update_group_members)
    monkeypatch.setattr(dependencies.auth_service, "list_api_keys", state.list_api_keys)
    monkeypatch.setattr(dependencies.auth_service, "create_api_key", state.create_api_key)
    monkeypatch.setattr(dependencies.auth_service, "update_api_key", state.update_api_key)
    monkeypatch.setattr(dependencies.auth_service, "regenerate_api_key_otlp_token", state.regenerate_api_key_otlp_token)
    monkeypatch.setattr(dependencies.auth_service, "delete_api_key", state.delete_api_key)
    monkeypatch.setattr(dependencies.auth_service, "set_api_key_hidden", state.set_api_key_hidden)
    monkeypatch.setattr(dependencies.auth_service, "list_api_key_shares", state.list_api_key_shares)
    monkeypatch.setattr(dependencies.auth_service, "replace_api_key_shares", state.replace_api_key_shares)
    monkeypatch.setattr(dependencies.auth_service, "delete_api_key_share", state.delete_api_key_share)
    monkeypatch.setattr(dependencies.auth_service, "validate_otlp_token", state.validate_otlp_token)
