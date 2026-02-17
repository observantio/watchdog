"""Database-backed authentication service with enterprise IAM."""
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from passlib.context import CryptContext
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func
from fastapi import HTTPException
import pyotp
from cryptography.fernet import Fernet, InvalidToken

try:
    from db_models import User, Tenant, Group, Permission, AuditLog, UserApiKey
except Exception:
    
    import importlib.util
    import os
    import sys

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    db_models_path = os.path.join(repo_root, "db_models.py")
    if os.path.exists(db_models_path):
        spec = importlib.util.spec_from_file_location("db_models", db_models_path)
        db_models = importlib.util.module_from_spec(spec)
        sys.modules["db_models"] = db_models
        spec.loader.exec_module(db_models)
        from db_models import User, Tenant, Group, Permission, AuditLog, UserApiKey
    else:
        raise
from models.access.user_models import (
    User as UserSchema, UserCreate, UserUpdate, UserPasswordUpdate, UserResponse
)
from models.access.group_models import (
    Group as GroupSchema, GroupCreate, GroupUpdate, PermissionInfo
)
from models.access.api_key_models import (
    ApiKey, ApiKeyCreate, ApiKeyUpdate
)
from models.access.auth_models import Role, Token, TokenData, ROLE_PERMISSIONS
from config import config
from database import get_db_session
from services.auth.permission_defs import PERMISSION_DEFS
from services.auth.oidc_service import OIDCService
from services.auth.auth_ops import (
    authenticate_user as authenticate_user_op,
    create_access_token as create_access_token_op,
    create_mfa_setup_token as create_mfa_setup_token_op,
    decode_token as decode_token_op,
    update_password as update_password_op,
    validate_otlp_token as validate_otlp_token_op,
)
from services.auth.user_ops import (
    get_user_by_id as get_user_by_id_op,
    get_user_by_username as get_user_by_username_op,
    create_user as create_user_op,
    list_users as list_users_op,
    update_user as update_user_op,
    set_grafana_user_id as set_grafana_user_id_op,
    delete_user as delete_user_op,
    update_user_permissions as update_user_permissions_op,
)
from services.auth.group_ops import (
    create_group as create_group_op,
    list_groups as list_groups_op,
    get_group as get_group_op,
    delete_group as delete_group_op,
    update_group as update_group_op,
    update_group_permissions as update_group_permissions_op,
    update_group_members as update_group_members_op,
)
from services.auth.api_key_ops import (
    list_api_keys as list_api_keys_op,
    create_api_key as create_api_key_op,
    update_api_key as update_api_key_op,
    delete_api_key as delete_api_key_op,
    backfill_otlp_tokens as backfill_otlp_tokens_op,
)

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class DatabaseAuthService:
    """Enterprise authentication service using PostgreSQL."""
    
    def __init__(self):
        self._initialized = False
        self.logger = logger
        self.oidc_service = OIDCService()

    def is_external_auth_enabled(self) -> bool:
        return config.AUTH_PROVIDER == "keycloak" and self.oidc_service.is_enabled()

    def is_password_auth_enabled(self) -> bool:
        return bool(config.AUTH_PASSWORD_FLOW_ENABLED)
    
    def _lazy_init(self):
        """Lazy initialization to ensure database is ready."""
        if not self._initialized:
            try:
                self._ensure_default_setup()
                self._initialized = True
            except Exception as e:
                logger.warning(f"Failed to initialize auth service: {e}")
    
    def _ensure_default_setup(self):
        """Ensure default tenant, permissions, and admin user exist."""
        try:
            with get_db_session() as db:
                default_tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
                self._ensure_permissions(db)

                if not config.DEFAULT_ADMIN_BOOTSTRAP_ENABLED:
                    if not default_tenant:
                        logger.warning(
                            "DEFAULT_ADMIN_BOOTSTRAP_ENABLED is false and default tenant is missing. Run explicit bootstrap before serving production traffic."
                        )
                    return

                if not default_tenant:
                    default_tenant = Tenant(
                        name=config.DEFAULT_ADMIN_TENANT,
                        display_name="Default Organization",
                        is_active=True
                    )
                    db.add(default_tenant)
                    db.flush()
                    logger.info("Created default tenant")

                admin_username = (config.DEFAULT_ADMIN_USERNAME or '').strip().lower()
                admin_user = db.query(User).filter_by(
                    tenant_id=default_tenant.id,
                    username=admin_username
                ).first()
                
                if not admin_user:
                    admin_user = User(
                        tenant_id=default_tenant.id,
                        username=admin_username,
                        email=config.DEFAULT_ADMIN_EMAIL,
                        full_name="System Administrator",
                        org_id=config.DEFAULT_ORG_ID,
                        role=Role.ADMIN,
                        is_active=True,
                        is_superuser=True,
                        hashed_password=self.hash_password(config.DEFAULT_ADMIN_PASSWORD),
                        must_setup_mfa=True,
                    )
                    db.add(admin_user)
                    db.flush()
                    
                    
                    all_permissions = db.query(Permission).all()
                    admin_user.permissions.extend(all_permissions)
                    
                    logger.info(f"Created default admin user: {config.DEFAULT_ADMIN_USERNAME}")

                self._ensure_default_api_key(db, admin_user)
                
                db.commit()
        except Exception as e:
            logger.error(f"Error setting up defaults: {e}")
    
    def _ensure_permissions(self, db: Session):
        """Create all predefined permissions."""
        for name, display_name, description, resource_type, action in PERMISSION_DEFS:
            if not db.query(Permission).filter_by(name=name).first():
                perm = Permission(
                    name=name,
                    display_name=display_name,
                    description=description,
                    resource_type=resource_type,
                    action=action
                )
                db.add(perm)
        
        db.flush()

    @staticmethod
    def _generate_otlp_token() -> str:
        """Generate a secure random OTLP ingest token."""
        return f"bo_{secrets.token_urlsafe(32)}"

    def _resolve_default_otlp_token(self) -> str:
        """Return the OTLP token to use for the default API key."""
        if config.DEFAULT_OTLP_TOKEN:
            return config.DEFAULT_OTLP_TOKEN
        return self._generate_otlp_token()

    def _ensure_default_api_key(self, db: Session, user: User):
        """Ensure a default API key exists for the user.

        Only the *system-created* "Default" key (name == "Default") has its
        ``key`` and ``otlp_token`` synchronised with the environment
        variables on every startup.  User-created keys that were later
        promoted to default are left untouched so their unique OTLP tokens
        and org-id values are preserved.
        """
        if not user:
            return

        is_system_user = (
            getattr(user, "username", None)
            and getattr(user, "username", "").strip().lower()
            == (config.DEFAULT_ADMIN_USERNAME or "").strip().lower()
        )

        existing_default = db.query(UserApiKey).filter_by(user_id=user.id, is_default=True).first()
        if existing_default:
            is_system_key = existing_default.name == "Default" and is_system_user
            if is_system_key:
                desired_token = self._resolve_default_otlp_token()
                if existing_default.key != (user.org_id or config.DEFAULT_ORG_ID):
                    existing_default.key = user.org_id or config.DEFAULT_ORG_ID
                    existing_default.updated_at = datetime.now(timezone.utc)
                if not existing_default.otlp_token or (
                    config.DEFAULT_OTLP_TOKEN and existing_default.otlp_token != config.DEFAULT_OTLP_TOKEN
                ):
                    existing_default.otlp_token = desired_token
                    existing_default.updated_at = datetime.now(timezone.utc)
            elif not existing_default.otlp_token:
                existing_default.otlp_token = self._generate_otlp_token()
                existing_default.updated_at = datetime.now(timezone.utc)
            return

        if is_system_user:
            desired_token = self._resolve_default_otlp_token()
        else:
            desired_token = self._generate_otlp_token()

        default_key = UserApiKey(
            tenant_id=user.tenant_id,
            user_id=user.id,
            name="Default",
            key=user.org_id or config.DEFAULT_ORG_ID,
            otlp_token=desired_token,
            is_default=True,
            is_enabled=True
        )
        db.add(default_key)
    
    def hash_password(self, password: str) -> str:
        return pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    # ------------------------- TOTP / MFA helpers -------------------------
    def _get_fernet(self) -> Optional[Fernet]:
        if not config.DATA_ENCRYPTION_KEY:
            if config.REQUIRE_TOTP_ENCRYPTION_KEY:
                raise ValueError("DATA_ENCRYPTION_KEY must be configured for MFA/TOTP operations")
            return None
        try:
            return Fernet(config.DATA_ENCRYPTION_KEY)
        except Exception:
            raise ValueError("Invalid DATA_ENCRYPTION_KEY format")

    def _encrypt_mfa_secret(self, secret: str) -> str:
        f = self._get_fernet()
        if not f:
            raise ValueError("DATA_ENCRYPTION_KEY is not configured")
        return f.encrypt(secret.encode()).decode()

    def _decrypt_mfa_secret(self, token: str) -> str:
        f = self._get_fernet()
        if not f:
            raise ValueError("DATA_ENCRYPTION_KEY is not configured")
        try:
            return f.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("Cannot decrypt TOTP secret") from exc

    def _generate_recovery_codes(self, count: int = 10) -> List[str]:
        codes = [secrets.token_urlsafe(10) for _ in range(count)]
        return codes

    def _hash_recovery_codes(self, codes: List[str]) -> List[str]:
        return [pwd_context.hash(c) for c in codes]

    def _verify_and_consume_recovery_code(self, db, user: User, code: str) -> bool:
        hashes = getattr(user, 'mfa_recovery_hashes', []) or []
        for i, h in enumerate(hashes):
            try:
                if pwd_context.verify(code, h):
                    # consume this code
                    hashes.pop(i)
                    user.mfa_recovery_hashes = hashes
                    return True
            except Exception:
                continue
        return False

    def enroll_totp(self, user_id: str) -> Dict[str, str]:
        """Generate a TOTP secret for user and persist encrypted secret (not enabled yet)."""
        if not config.DATA_ENCRYPTION_KEY:
            raise ValueError("DATA_ENCRYPTION_KEY must be configured to use TOTP")
        with get_db_session() as db:
            user = db.query(User).filter_by(id=user_id).first()
            if not user:
                raise ValueError("User not found")
            secret = pyotp.random_base32()
            encrypted = self._encrypt_mfa_secret(secret)
            user.totp_secret = encrypted
            db.add(user)
            db.flush()
            otp = pyotp.totp.TOTP(secret)
            uri = otp.provisioning_uri(name=user.email or user.username, issuer_name= "Be Observant")
            return {"otpauth_url": uri, "secret": secret}

    def verify_enable_totp(self, user_id: str, code: str) -> List[str]:
        """Verify provided TOTP code and enable MFA for the user, returning recovery codes."""
        with get_db_session() as db:
            user = db.query(User).filter_by(id=user_id).first()
            if not user or not user.totp_secret:
                raise ValueError("TOTP not enrolled for user")
            secret = self._decrypt_mfa_secret(user.totp_secret)
            if not pyotp.TOTP(secret).verify(code, valid_window=1):
                raise ValueError("Invalid TOTP code")
            # enable MFA and generate recovery codes
            user.mfa_enabled = True
            user.must_setup_mfa = False
            codes = self._generate_recovery_codes()
            user.mfa_recovery_hashes = self._hash_recovery_codes(codes)
            db.add(user)
            self._log_audit(db, user.tenant_id, user.id, "mfa.enabled", "users", user.id, {})
            return codes

    def verify_totp_code(self, user: User, code: str) -> bool:
        """Verify a TOTP or recovery code for *user*. If recovery code used, consume it (single-use)."""
        if not user or not user.totp_secret:
            return False
        # operate with a fresh DB session to consume recovery codes safely
        with get_db_session() as db:
            db_user = db.query(User).filter_by(id=user.id).first()
            if not db_user or not db_user.totp_secret:
                return False
            # check recovery codes
            hashes = getattr(db_user, 'mfa_recovery_hashes', []) or []
            for i, h in enumerate(hashes):
                try:
                    if pwd_context.verify(code, h):
                        hashes.pop(i)
                        db_user.mfa_recovery_hashes = hashes
                        db.add(db_user)
                        return True
                except Exception:
                    continue
            # verify TOTP
            try:
                secret = self._decrypt_mfa_secret(db_user.totp_secret)
            except Exception:
                return False
            return bool(pyotp.TOTP(secret).verify(code, valid_window=1))

    def disable_totp(self, user_id: str, *, current_password: Optional[str] = None, code: Optional[str] = None) -> bool:
        """Disable MFA for the given user after verifying password or TOTP code."""
        with get_db_session() as db:
            user = db.query(User).filter_by(id=user_id).first()
            if not user or not user.mfa_enabled:
                return False
            # require either password verification or valid code
            ok = False
            if current_password and self.verify_password(current_password, user.hashed_password):
                ok = True
            if not ok and code:
                if self.verify_totp_code(user, code):
                    ok = True
            if not ok:
                return False
            user.mfa_enabled = False
            user.totp_secret = None
            user.mfa_recovery_hashes = None
            db.add(user)
            self._log_audit(db, user.tenant_id, user.id, "mfa.disabled", "users", user.id, {})
            return True

    def reset_totp(self, user_id: str, admin_id: str) -> bool:
        """Admin-initiated reset of a user's TOTP state (clears secret and recovery codes)."""
        with get_db_session() as db:
            user = db.query(User).filter_by(id=user_id).first()
            if not user:
                return False
            user.mfa_enabled = False
            user.totp_secret = None
            user.mfa_recovery_hashes = None
            db.add(user)
            self._log_audit(db, user.tenant_id, admin_id, "mfa.reset", "users", user.id, {"admin_id": admin_id})
            return True

    # ------------------------------------------------------------------
    def create_access_token(self, user: User) -> Token:
        """Create JWT access token for user."""
        return create_access_token_op(self, user)

    def _build_token_data_for_user(self, user: User) -> TokenData:
        permissions = self.get_user_permissions(user)
        return TokenData(
            user_id=user.id,
            username=user.username,
            tenant_id=user.tenant_id,
            org_id=user.org_id,
            role=Role(user.role),
            is_superuser=user.is_superuser,
            permissions=permissions,
            group_ids=[g.id for g in (getattr(user, "groups", None) or [])],
        )

    def _extract_permissions_from_oidc_claims(self, claims: Dict[str, Any]) -> List[str]:
        extracted: set[str] = set()

        scope_raw = claims.get("scope")
        if isinstance(scope_raw, str):
            extracted.update(part.strip() for part in scope_raw.split(" ") if part.strip())

        scp = claims.get("scp")
        if isinstance(scp, list):
            extracted.update(str(item).strip() for item in scp if str(item).strip())

        direct_permissions = claims.get("permissions")
        if isinstance(direct_permissions, list):
            extracted.update(str(item).strip() for item in direct_permissions if str(item).strip())

        return [value for value in extracted if ":" in value]

    def _sync_user_from_oidc_claims(self, claims: Dict[str, Any]) -> Optional[User]:
        email = (claims.get("email") or "").strip().lower()
        subject = (claims.get("sub") or "").strip()
        if not email:
            self.logger.warning("OIDC token missing email claim")
            return None

        preferred_username = (claims.get("preferred_username") or email.split("@", 1)[0] or "").strip().lower()
        full_name = (claims.get("name") or "").strip() or None

        with get_db_session() as db:
            user = None
            if subject:
                user = db.query(User).filter(User.external_subject == subject).first()
            if not user:
                user = db.query(User).filter(func.lower(User.email) == email).first()

            if not user and not config.OIDC_AUTO_PROVISION_USERS:
                return None

            if not user:
                default_tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
                if not default_tenant:
                    default_tenant = Tenant(
                        name=config.DEFAULT_ADMIN_TENANT,
                        display_name="Default Organization",
                        is_active=True,
                    )
                    db.add(default_tenant)
                    db.flush()

                base_username = preferred_username or email.split("@", 1)[0]
                candidate_username = base_username
                suffix = 1
                while db.query(User).filter(func.lower(User.username) == candidate_username.lower()).first():
                    candidate_username = f"{base_username}{suffix}"
                    suffix += 1

                user = User(
                    tenant_id=default_tenant.id,
                    username=candidate_username,
                    email=email,
                    full_name=full_name,
                    org_id=config.DEFAULT_ORG_ID,
                    role=Role.USER,
                    is_active=True,
                    is_superuser=False,
                    hashed_password=self.hash_password(secrets.token_urlsafe(24)),
                    needs_password_change=False,
                    auth_provider=config.AUTH_PROVIDER,
                    external_subject=subject or None,
                )
                db.add(user)
                db.flush()
                self._ensure_default_api_key(db, user)
            else:
                user.auth_provider = config.AUTH_PROVIDER
                if subject:
                    user.external_subject = subject
                if email and user.email.lower() != email:
                    conflicting = db.query(User).filter(
                        and_(func.lower(User.email) == email, User.id != user.id)
                    ).first()
                    if not conflicting:
                        user.email = email
                if full_name and user.full_name != full_name:
                    user.full_name = full_name

            user.last_login = datetime.now(timezone.utc)
            db.commit()
            db.refresh(user)
            return user

    def login(self, username: str, password: str, mfa_code: Optional[str] = None) -> Optional[Token | dict]:
        """Authenticate using configured provider and return access token.

        If the user has MFA enabled and no `mfa_code` is provided, return a
        challenge dict {"mfa_required": True}. If `mfa_code` is provided it
        will be validated before issuing the local token.
        """
        if self.is_external_auth_enabled():
            if not self.is_password_auth_enabled():
                return None
            try:
                oidc_token = self.oidc_service.exchange_password(username, password)
            except Exception as exc:
                self.logger.error("OIDC password login failed: %s", exc)
                return None

            access_token = oidc_token.get("access_token")
            if not access_token:
                return None
            claims = self.oidc_service.verify_access_token(access_token)
            if not claims:
                return None
            user = self._sync_user_from_oidc_claims(claims)
            if not user or not user.is_active:
                return None
            return Token(
                access_token=access_token,
                token_type=oidc_token.get("token_type", "bearer"),
                expires_in=int(oidc_token.get("expires_in", config.JWT_EXPIRATION_MINUTES * 60)),
            )

        user = self.authenticate_user(username, password)
        if not user:
            return None

        # If user must setup MFA before using the app, return a short-lived
        # setup token so they can enroll/verify TOTP without a full session.
        if getattr(user, 'must_setup_mfa', False) and not getattr(user, 'mfa_enabled', False):
            setup_token = create_mfa_setup_token_op(self, user)
            return {"mfa_setup_required": True, "setup_token": setup_token.access_token}

        # If user has MFA enabled require second factor
        if getattr(user, 'mfa_enabled', False):
            if not mfa_code:
                return {"mfa_required": True}
            ok = self.verify_totp_code(user, mfa_code)
            if not ok:
                return None

        return self.create_access_token(user)

    def exchange_oidc_authorization_code(self, code: str, redirect_uri: str) -> Optional[Token]:
        if not self.is_external_auth_enabled():
            return None
        try:
            oidc_token = self.oidc_service.exchange_authorization_code(code, redirect_uri)
            access_token = oidc_token.get("access_token")
            if not access_token:
                return None
            claims = self.oidc_service.verify_access_token(access_token)
            if not claims:
                return None
            user = self._sync_user_from_oidc_claims(claims)
            if not user or not user.is_active:
                return None
            # Enforce must-setup-mfa for externally-provisioned users as well.
            if getattr(user, 'must_setup_mfa', False) and not getattr(user, 'mfa_enabled', False):
                setup_token = create_mfa_setup_token_op(self, user)
                return {"mfa_setup_required": True, "setup_token": setup_token.access_token}
            return Token(
                access_token=access_token,
                token_type=oidc_token.get("token_type", "bearer"),
                expires_in=int(oidc_token.get("expires_in", config.JWT_EXPIRATION_MINUTES * 60)),
            )
        except Exception as exc:
            self.logger.error("OIDC code exchange failed: %s", exc)
            return None

    def get_oidc_authorization_url(self, redirect_uri: str, state: str, nonce: str) -> str:
        return self.oidc_service.build_authorization_url(redirect_uri, state, nonce)

    def provision_external_user(self, *, email: str, username: str, full_name: Optional[str]) -> Optional[str]:
        if not self.is_external_auth_enabled():
            return None
        try:
            return self.oidc_service.create_keycloak_user(email=email, username=username, full_name=full_name)
        except Exception as exc:
            self.logger.error("External user provisioning failed: %s", exc)
            return None
    
    def decode_token(self, token: str) -> Optional[TokenData]:
        """Decode and validate local JWT or OIDC access token."""
        local_token = decode_token_op(self, token)
        if local_token:
            return local_token

        if not self.is_external_auth_enabled():
            return None

        claims = self.oidc_service.verify_access_token(token)
        if not claims:
            return None

        user = self._sync_user_from_oidc_claims(claims)
        if not user or not user.is_active:
            return None
        token_data = self._build_token_data_for_user(user)
        token_data.permissions = list(set(token_data.permissions).union(self._extract_permissions_from_oidc_claims(claims)))
        return token_data
    
    def get_user_permissions(self, user: User) -> List[str]:
        """Get all permissions for a user (role + direct + group permissions)."""
        user_id = getattr(user, "id", None)
        if not user_id:
            return []

        with get_db_session() as db:
            db_user = db.query(User).options(
                joinedload(User.groups).joinedload(Group.permissions),
                joinedload(User.permissions)
            ).filter_by(id=user_id).first()
            if not db_user:
                return []
            return self._collect_permissions(db_user)

    def get_user_direct_permissions(self, user: User) -> List[str]:
        """Get direct permissions explicitly assigned to a user."""
        user_id = getattr(user, "id", None)
        if not user_id:
            return []

        with get_db_session() as db:
            db_user = db.query(User).options(joinedload(User.permissions)).filter_by(id=user_id).first()
            if not db_user:
                return []
            return [p.name for p in (db_user.permissions or [])]

    def _collect_permissions(self, user: User) -> List[str]:
        """Collect permissions with priority: User direct > Group > Role."""
        user_direct_perms = set()
        group_perms = set()

        
        user_direct_perms.update([p.name for p in user.permissions])

        
        for group in user.groups:
            if group.is_active:
                group_perms.update([p.name for p in group.permissions])

        
        role_perms = ROLE_PERMISSIONS.get(Role(user.role), [])
        role_perm_names = {p.value for p in role_perms}

        
        permissions = role_perm_names.union(group_perms).union(user_direct_perms)

        return list(permissions)

    def _to_user_schema(self, user: User) -> UserSchema:
        api_keys = [self._to_api_key_schema(key) for key in (getattr(user, "api_keys", []) or [])]
        schema_kwargs = dict(
            id=user.id,
            tenant_id=user.tenant_id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            org_id=user.org_id,
            role=Role(user.role),
            group_ids=[g.id for g in (user.groups or [])],
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login=user.last_login,
            needs_password_change=getattr(user, 'needs_password_change', False),
            api_keys=api_keys,
            mfa_enabled=getattr(user, 'mfa_enabled', False),
            must_setup_mfa=getattr(user, 'must_setup_mfa', False),
        )
        grafana_uid = getattr(user, "grafana_user_id", None)
        if grafana_uid is not None:
            schema_kwargs["grafana_user_id"] = grafana_uid
        return UserSchema(**schema_kwargs)

    def build_user_response(
        self,
        user: UserSchema,
        fallback_permissions: Optional[List[str]] = None,
    ) -> UserResponse:
        permissions = self.get_user_permissions(user)
        if not permissions and fallback_permissions is not None:
            permissions = fallback_permissions
        return UserResponse(
            **user.model_dump(exclude={"hashed_password"}),
            permissions=permissions,
            direct_permissions=self.get_user_direct_permissions(user),
        )

    def _to_api_key_schema(self, key: UserApiKey) -> ApiKey:
        return ApiKey(
            id=key.id,
            name=key.name,
            key=key.key,
            otlp_token=getattr(key, 'otlp_token', None),
            is_default=key.is_default,
            is_enabled=key.is_enabled,
            created_at=key.created_at,
            updated_at=key.updated_at
        )

    def _to_group_schema(self, group: Group) -> GroupSchema:
        permissions = [
            PermissionInfo(
                id=p.id,
                name=p.name,
                display_name=p.display_name,
                description=p.description,
                resource_type=p.resource_type,
                action=p.action
            )
            for p in (group.permissions or [])
        ]
        return GroupSchema(
            id=group.id,
            tenant_id=group.tenant_id,
            name=group.name,
            description=group.description,
            created_at=group.created_at,
            updated_at=group.updated_at,
            permissions=permissions
        )
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username and password."""
        if self.is_external_auth_enabled() and not self.is_password_auth_enabled():
            return None
        return authenticate_user_op(self, username, password)
    
    def get_user_by_id(self, user_id: str) -> Optional[UserSchema]:
        """Get user by ID with relationships."""
        return get_user_by_id_op(self, user_id)
    
    def get_user_by_username(self, username: str) -> Optional[UserSchema]:
        """Get user by username."""
        return get_user_by_username_op(self, username)
    
    def create_user(self, user_create: UserCreate, tenant_id: str, creator_id: str = None) -> UserSchema:
        """Create a new user."""
        return create_user_op(self, user_create, tenant_id, creator_id)
    
    def list_users(self, tenant_id: str) -> List[UserSchema]:
        """List all users in a tenant."""
        return list_users_op(self, tenant_id)
    
    def update_user(self, user_id: str, user_update: UserUpdate, tenant_id: str, updater_id: str = None) -> Optional[UserSchema]:
        """Update user information."""
        return update_user_op(self, user_id, user_update, tenant_id, updater_id)

    def set_grafana_user_id(self, user_id: str, grafana_user_id: int, tenant_id: str) -> bool:
        """Store the Grafana user ID on the local user record."""
        return set_grafana_user_id_op(self, user_id, grafana_user_id, tenant_id)
    
    def delete_user(self, user_id: str, tenant_id: str, deleter_id: str = None) -> bool:
        """Delete a user."""
        return delete_user_op(self, user_id, tenant_id, deleter_id)

    def list_api_keys(self, user_id: str) -> List[ApiKey]:
        return list_api_keys_op(self, user_id)

    def create_api_key(self, user_id: str, tenant_id: str, key_create: ApiKeyCreate) -> ApiKey:
        return create_api_key_op(self, user_id, tenant_id, key_create)

    def update_api_key(self, user_id: str, key_id: str, key_update: ApiKeyUpdate) -> ApiKey:
        return update_api_key_op(self, user_id, key_id, key_update)

    def delete_api_key(self, user_id: str, key_id: str) -> bool:
        return delete_api_key_op(self, user_id, key_id)
    
    def create_group(self, group_create: GroupCreate, tenant_id: str, creator_id: str = None) -> GroupSchema:
        """Create a new group."""
        return create_group_op(self, group_create, tenant_id, creator_id)
    
    def list_groups(self, tenant_id: str) -> List[GroupSchema]:
        """List all groups in a tenant."""
        return list_groups_op(self, tenant_id)
    
    def get_group(self, group_id: str, tenant_id: str) -> Optional[GroupSchema]:
        """Get a specific group."""
        return get_group_op(self, group_id, tenant_id)
    
    def delete_group(self, group_id: str, tenant_id: str, deleter_id: str = None) -> bool:
        """Delete a group."""
        return delete_group_op(self, group_id, tenant_id, deleter_id)

    def update_group(self, group_id: str, group_update: GroupUpdate, tenant_id: str, updater_id: str = None) -> Optional[GroupSchema]:
        """Update group information."""
        return update_group_op(self, group_id, group_update, tenant_id, updater_id)
    
    def update_user_permissions(self, user_id: str, permission_names: List[str], tenant_id: str) -> bool:
        """Update user's direct permissions."""
        return update_user_permissions_op(self, user_id, permission_names, tenant_id)
    
    def update_group_permissions(self, group_id: str, permission_names: List[str], tenant_id: str) -> bool:
        """Update group's permissions."""
        return update_group_permissions_op(self, group_id, permission_names, tenant_id)

    def update_group_members(self, group_id: str, user_ids: List[str], tenant_id: str) -> bool:
        """Update group's member users."""
        return update_group_members_op(self, group_id, user_ids, tenant_id)
    
    def list_all_permissions(self) -> List[Dict[str, Any]]:
        """List all available permissions."""
        with get_db_session() as db:
            permissions = db.query(Permission).order_by(Permission.resource_type, Permission.action).all()
            return [
                {
                    "id": p.id,
                    "name": p.name,
                    "display_name": p.display_name,
                    "description": p.description,
                    "resource_type": p.resource_type,
                    "action": p.action
                }
                for p in permissions
            ]
    
    def update_password(self, user_id: str, password_update: UserPasswordUpdate, tenant_id: str) -> bool:
        """Update user password."""
        if self.is_external_auth_enabled():
            raise ValueError("Password updates are managed by the external identity provider")
        return update_password_op(self, user_id, password_update, tenant_id)
    
    def validate_otlp_token(self, token: str) -> Optional[str]:
        """Validate an OTLP ingest token and return the mapped org_id (key)."""
        return validate_otlp_token_op(self, token)

    def backfill_otlp_tokens(self):
        """Generate otlp_token for any existing API keys that lack one."""
        backfill_otlp_tokens_op(self)

    def _log_audit(self, db: Session, tenant_id: str, user_id: str, action: str, 
                   resource_type: str, resource_id: str, details: Dict[str, Any]):
        """Log an audit entry."""
        log = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details
        )
        db.add(log)
