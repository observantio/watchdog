"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import logging
import secrets
import threading
from typing import Any, Dict, List, Optional, Union

from cryptography.fernet import Fernet
from passlib.context import CryptContext
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

try:
    from db_models import AuditLog, Group, Permission, Tenant, User, UserApiKey
except ImportError:
    import importlib.util
    import os
    import sys

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    db_models_path = os.path.join(repo_root, "db_models.py")
    if not os.path.exists(db_models_path):
        raise
    spec = importlib.util.spec_from_file_location("db_models", db_models_path)
    db_models = importlib.util.module_from_spec(spec)
    sys.modules["db_models"] = db_models
    spec.loader.exec_module(db_models)
    from db_models import AuditLog, Group, Permission, Tenant, User, UserApiKey

from config import config
from database import get_db_session
from models.access.api_key_models import ApiKey, ApiKeyCreate, ApiKeyUpdate
from models.access.auth_models import ROLE_PERMISSIONS, Role, Token, TokenData
from models.access.group_models import Group as GroupSchema, GroupCreate, GroupUpdate, PermissionInfo
from models.access.user_models import (
    User as UserSchema,
    UserCreate,
    UserPasswordUpdate,
    UserResponse,
    UserUpdate,
)
from services.auth.api_key_ops import (
    backfill_otlp_tokens as backfill_otlp_tokens_op,
    create_api_key as create_api_key_op,
    delete_api_key as delete_api_key_op,
    delete_api_key_share as delete_api_key_share_op,
    list_api_key_shares as list_api_key_shares_op,
    list_api_keys as list_api_keys_op,
    replace_api_key_shares as replace_api_key_shares_op,
    update_api_key as update_api_key_op,
)
from services.auth.auth_ops import (
    authenticate_user as authenticate_user_op,
    create_access_token as create_access_token_op,
    create_mfa_setup_token as create_mfa_setup_token_op,
    decode_token as decode_token_op,
    update_password as update_password_op,
    validate_otlp_token as validate_otlp_token_op,
)
from services.auth.group_ops import (
    create_group as create_group_op,
    delete_group as delete_group_op,
    get_group as get_group_op,
    list_groups as list_groups_op,
    update_group as update_group_op,
    update_group_members as update_group_members_op,
    update_group_permissions as update_group_permissions_op,
)
from services.auth.oidc_service import OIDCService
from services.auth.permission_defs import PERMISSION_DEFS
from services.auth.user_ops import (
    create_user as create_user_op,
    delete_user as delete_user_op,
    get_user_by_id as get_user_by_id_op,
    get_user_by_username as get_user_by_username_op,
    list_users as list_users_op,
    set_grafana_user_id as set_grafana_user_id_op,
    update_user as update_user_op,
    update_user_permissions as update_user_permissions_op,
)
from services.database_auth import (
    audit as db_audit,
    auth as db_auth,
    bootstrap as db_bootstrap,
    mfa as db_mfa,
    oidc as db_oidc,
    password as db_password,
    permissions as db_permissions,
    schema_converters as db_schema,
    token as db_token,
)

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_MFA_SETUP_RESPONSE = "mfa_setup_required"
_MFA_REQUIRED_RESPONSE = "mfa_required"


class DatabaseAuthService:
    _MFA_SETUP_RESPONSE = "mfa_setup_required"
    _MFA_REQUIRED_RESPONSE = "mfa_required"

    """Enterprise authentication service backed by PostgreSQL."""

    def __init__(self):
        super().__init__()
        self._initialized = False
        self.logger = logger
        self.oidc_service = OIDCService()
        self._password_op_semaphore = threading.Semaphore(1)

    def is_external_auth_enabled(self) -> bool:
        return config.AUTH_PROVIDER == "keycloak" and self.oidc_service.is_enabled()

    def is_password_auth_enabled(self) -> bool:
        return bool(config.AUTH_PASSWORD_FLOW_ENABLED)

    def _lazy_init(self):
        if not self._initialized:
            try:
                self._ensure_default_setup()
                self._initialized = True
            except (SQLAlchemyError, ValueError) as exc:
                logger.warning("Failed to initialize auth service: %s", exc)

    def _ensure_default_setup(self):
        return db_bootstrap.ensure_default_setup(self)

    def _ensure_permissions(self, db: Session):
        return db_bootstrap.ensure_permissions(self, db)

    def _ensure_default_api_key(self, db: Session, user: User):
        return db_bootstrap.ensure_default_api_key(self, db, user)


    def hash_password(self, password: str) -> str:
        return db_password.hash_password(self, password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return db_password.verify_password(self, plain_password, hashed_password)

    def _get_fernet(self) -> Optional[Fernet]:
        return db_mfa._get_fernet(self)

    def _encrypt_mfa_secret(self, secret: str) -> str:
        return db_mfa._encrypt_mfa_secret(self, secret)

    def _decrypt_mfa_secret(self, token: str) -> str:
        return db_mfa._decrypt_mfa_secret(self, token)

    def _generate_recovery_codes(self, count: int = 10) -> List[str]:
        return db_mfa._generate_recovery_codes(self, count)

    def _hash_recovery_codes(self, codes: List[str]) -> List[str]:
        return db_mfa._hash_recovery_codes(self, codes)

    def _consume_recovery_code(self, db_user: User, code: str) -> bool:
        return db_mfa._consume_recovery_code(self, db_user, code)

    @staticmethod
    def _generate_otlp_token() -> str:
        return f"bo_{secrets.token_urlsafe(32)}"

    def _resolve_default_otlp_token(self) -> str:
        return config.DEFAULT_OTLP_TOKEN or self._generate_otlp_token()

    def enroll_totp(self, user_id: str) -> Dict[str, str]:
        return db_mfa.enroll_totp(self, user_id)

    def verify_enable_totp(self, user_id: str, code: str) -> List[str]:
        return db_mfa.verify_enable_totp(self, user_id, code)

    def verify_totp_code(self, user: User, code: str) -> bool:
        return db_mfa.verify_totp_code(self, user, code)

    def disable_totp(
        self,
        user_id: str,
        *,
        current_password: Optional[str] = None,
        code: Optional[str] = None,
    ) -> bool:
        return db_mfa.disable_totp(self, user_id, current_password=current_password, code=code)

    def reset_totp(self, user_id: str, admin_id: str) -> bool:
        return db_mfa.reset_totp(self, user_id, admin_id)

    def _mfa_setup_challenge(self, user: User) -> dict:
        return db_mfa._mfa_setup_challenge(self, user)

    def _needs_mfa_setup(self, user: User) -> bool:
        return db_mfa._needs_mfa_setup(self, user)

    def create_access_token(self, user: User) -> Token:
        return create_access_token_op(self, user)

    def _build_token_data_for_user(self, user: User) -> TokenData:
        return db_token.build_token_data_for_user(self, user)

    def decode_token(self, token: str) -> Optional[TokenData]:
        return db_token.decode_token(self, token)

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        if self.is_external_auth_enabled() and not self.is_password_auth_enabled():
            return None
        return authenticate_user_op(self, username, password)

    def login(
        self, username: str, password: str, mfa_code: Optional[str] = None
    ) -> Optional[Union[Token, dict]]:
        return db_auth.login(self, username, password, mfa_code)

    def exchange_oidc_authorization_code(self, code: str, redirect_uri: str) -> Optional[Union[Token, dict]]:
        return db_auth.exchange_oidc_authorization_code(self, code, redirect_uri)

    def get_oidc_authorization_url(self, redirect_uri: str, state: str, nonce: str) -> str:
        return db_auth.get_oidc_authorization_url(self, redirect_uri, state, nonce)

    def provision_external_user(
        self, *, email: str, username: str, full_name: Optional[str]
    ) -> Optional[str]:
        return db_auth.provision_external_user(self, email=email, username=username, full_name=full_name)


    def _extract_permissions_from_oidc_claims(self, claims: Dict[str, Any]) -> List[str]:
        return db_oidc.extract_permissions_from_oidc_claims(self, claims)

    def _sync_user_from_oidc_claims(self, claims: Dict[str, Any]) -> Optional[User]:
        return db_oidc.sync_user_from_oidc_claims(self, claims)

    def _provision_oidc_user(
        self,
        db: Session,
        email: str,
        preferred_username: str,
        full_name: Optional[str],
        subject: str,
    ) -> User:
        return db_oidc.provision_oidc_user(self, db, email, preferred_username, full_name, subject)

    def _update_oidc_user(
        self, db: Session, user: User, email: str, full_name: Optional[str], subject: str
    ):
        return db_oidc.update_oidc_user(self, db, user, email, full_name, subject)


    def get_user_permissions(self, user: User) -> List[str]:
        return db_permissions.get_user_permissions(self, user)

    def get_user_direct_permissions(self, user: User) -> List[str]:
        return db_permissions.get_user_direct_permissions(self, user)

    def _collect_permissions(self, user: User) -> List[str]:
        return db_permissions.collect_permissions(self, user)

    def list_all_permissions(self) -> List[Dict[str, Any]]:
        return db_permissions.list_all_permissions(self)

    def _to_user_schema(self, user: User) -> UserSchema:
        return db_schema.to_user_schema(self, user)

    def build_user_response(
        self,
        user: UserSchema,
        fallback_permissions: Optional[List[str]] = None,
    ) -> UserResponse:
        return db_schema.build_user_response(self, user, fallback_permissions)

    def _to_api_key_schema(self, key: UserApiKey) -> ApiKey:
        return db_schema.to_api_key_schema(self, key)

    def _to_group_schema(self, group: Group) -> GroupSchema:
        return db_schema.to_group_schema(self, group)

    # -------------------------------------------------------------------------
    # User CRUD
    # -------------------------------------------------------------------------

    def get_user_by_id(self, user_id: str) -> Optional[UserSchema]:
        return get_user_by_id_op(self, user_id)

    def get_user_by_username(self, username: str) -> Optional[UserSchema]:
        return get_user_by_username_op(self, username)

    def create_user(self, user_create: UserCreate, tenant_id: str, creator_id: str = None) -> UserSchema:
        return create_user_op(self, user_create, tenant_id, creator_id)

    def list_users(self, tenant_id: str, *, limit: Optional[int] = None, offset: int = 0) -> List[UserSchema]:
        return list_users_op(self, tenant_id, limit=limit, offset=offset)

    def update_user(
        self, user_id: str, user_update: UserUpdate, tenant_id: str, updater_id: str = None
    ) -> Optional[UserSchema]:
        return update_user_op(self, user_id, user_update, tenant_id, updater_id)

    def set_grafana_user_id(self, user_id: str, grafana_user_id: int, tenant_id: str) -> bool:
        return set_grafana_user_id_op(self, user_id, grafana_user_id, tenant_id)

    def delete_user(self, user_id: str, tenant_id: str, deleter_id: str = None) -> bool:
        return delete_user_op(self, user_id, tenant_id, deleter_id)

    def update_user_permissions(self, user_id: str, permission_names: List[str], tenant_id: str) -> bool:
        return update_user_permissions_op(self, user_id, permission_names, tenant_id)

    def update_password(self, user_id: str, password_update: UserPasswordUpdate, tenant_id: str) -> bool:
        if self.is_external_auth_enabled():
            raise ValueError("Password updates are managed by the external identity provider")
        return update_password_op(self, user_id, password_update, tenant_id)

    def list_api_keys(self, user_id: str) -> List[ApiKey]:
        return list_api_keys_op(self, user_id)

    def create_api_key(self, user_id: str, tenant_id: str, key_create: ApiKeyCreate) -> ApiKey:
        return create_api_key_op(self, user_id, tenant_id, key_create)

    def update_api_key(self, user_id: str, key_id: str, key_update: ApiKeyUpdate) -> ApiKey:
        return update_api_key_op(self, user_id, key_id, key_update)

    def delete_api_key(self, user_id: str, key_id: str) -> bool:
        return delete_api_key_op(self, user_id, key_id)

    def list_api_key_shares(self, owner_user_id: str, tenant_id: str, key_id: str):
        return list_api_key_shares_op(self, owner_user_id, tenant_id, key_id)

    def replace_api_key_shares(
        self,
        owner_user_id: str,
        tenant_id: str,
        key_id: str,
        user_ids: List[str],
        group_ids: Optional[List[str]] = None,
    ):
        return replace_api_key_shares_op(self, owner_user_id, tenant_id, key_id, user_ids, group_ids=group_ids)

    def delete_api_key_share(
        self, owner_user_id: str, tenant_id: str, key_id: str, shared_user_id: str
    ) -> bool:
        return delete_api_key_share_op(self, owner_user_id, tenant_id, key_id, shared_user_id)

    def validate_otlp_token(self, token: str) -> Optional[str]:
        return validate_otlp_token_op(self, token)

    def backfill_otlp_tokens(self):
        backfill_otlp_tokens_op(self)


    def create_group(self, group_create: GroupCreate, tenant_id: str, creator_id: str = None) -> GroupSchema:
        return create_group_op(self, group_create, tenant_id, creator_id)

    def list_groups(self, tenant_id: str) -> List[GroupSchema]:
        return list_groups_op(self, tenant_id)

    def get_group(self, group_id: str, tenant_id: str) -> Optional[GroupSchema]:
        return get_group_op(self, group_id, tenant_id)

    def delete_group(self, group_id: str, tenant_id: str, deleter_id: str = None) -> bool:
        return delete_group_op(self, group_id, tenant_id, deleter_id)

    def update_group(
        self, group_id: str, group_update: GroupUpdate, tenant_id: str, updater_id: str = None
    ) -> Optional[GroupSchema]:
        return update_group_op(self, group_id, group_update, tenant_id, updater_id)

    def update_group_permissions(
        self, group_id: str, permission_names: List[str], tenant_id: str
    ) -> bool:
        return update_group_permissions_op(self, group_id, permission_names, tenant_id)

    def update_group_members(self, group_id: str, user_ids: List[str], tenant_id: str) -> bool:
        return update_group_members_op(self, group_id, user_ids, tenant_id)

        
    def _log_audit(
        self,
        db: Session,
        tenant_id: str,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: Dict[str, Any],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        return db_audit.log_audit(
            self, db, tenant_id, user_id, action, resource_type, resource_id, details,
            ip_address=ip_address, user_agent=user_agent,
        )