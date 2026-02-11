"""Database-backed authentication service with enterprise IAM."""
import logging
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_
from fastapi import HTTPException

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
from models.auth_models import (
    User as UserSchema, UserCreate, UserUpdate, UserPasswordUpdate, Role,
    Group as GroupSchema, GroupCreate, GroupUpdate, Token, TokenData, ROLE_PERMISSIONS,
    PermissionInfo, ApiKey, ApiKeyCreate, ApiKeyUpdate
)
from config import config
from database import get_db_session

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class DatabaseAuthService:
    """Enterprise authentication service using PostgreSQL."""
    
    def __init__(self):
        self._initialized = False
    
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
                if not default_tenant:
                    default_tenant = Tenant(
                        name=config.DEFAULT_ADMIN_TENANT,
                        display_name="Default Organization",
                        is_active=True
                    )
                    db.add(default_tenant)
                    db.flush()
                    logger.info("Created default tenant")
                
                
                self._ensure_permissions(db)
                
                
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
                        hashed_password=self.hash_password(config.DEFAULT_ADMIN_PASSWORD)
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
        permission_defs = [
            ("read:alerts", "Read Alerts", "View alert rules and active alerts", "alerts", "read"),
            ("write:alerts", "Write Alerts", "Create and update alert rules", "alerts", "write"),
            ("delete:alerts", "Delete Alerts", "Delete alert rules", "alerts", "delete"),
            
            
            ("read:channels", "Read Channels", "View notification channels", "channels", "read"),
            ("write:channels", "Write Channels", "Create and update notification channels", "channels", "write"),
            ("delete:channels", "Delete Channels", "Delete notification channels", "channels", "delete"),
            
            
            ("read:logs", "Read Logs", "Query and view logs", "logs", "read"),
            
            
            ("read:traces", "Read Traces", "Query and view traces", "traces", "read"),
            
            
            ("read:dashboards", "Read Dashboards", "View Grafana dashboards", "dashboards", "read"),
            ("write:dashboards", "Write Dashboards", "Create and update dashboards", "dashboards", "write"),
            ("delete:dashboards", "Delete Dashboards", "Delete dashboards", "dashboards", "delete"),
            
            ("read:agents", "Read Agents", "View OTEL agents and system metrics", "agents", "read"),
            
            
            ("manage:users", "Manage Users", "Create, update, and delete users", "users", "manage"),
            ("read:users", "Read Users", "View user information", "users", "read"),
            
            
            ("manage:groups", "Manage Groups", "Create, update, and delete groups", "groups", "manage"),
            ("read:groups", "Read Groups", "View group information", "groups", "read"),
            
            
            ("manage:tenants", "Manage Tenants", "Manage tenant settings", "tenants", "manage"),
        ]
        
        for name, display_name, description, resource_type, action in permission_defs:
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
    
    def create_access_token(self, user: User) -> Token:
        """Create JWT access token for user."""
        expires_delta = timedelta(minutes=config.JWT_EXPIRATION_MINUTES)
        expire = datetime.now(timezone.utc) + expires_delta

        user_id = getattr(user, "id", None)
        if not user_id:
            raise ValueError("User ID is required to create access token")

        with get_db_session() as db:
            db_user = db.query(User).options(
                joinedload(User.groups).joinedload(Group.permissions),
                joinedload(User.permissions)
            ).filter_by(id=user_id).first()

            if not db_user:
                raise ValueError("User not found")

            permissions = self._collect_permissions(db_user)
            group_ids = [g.id for g in db_user.groups] if db_user.groups else []

            to_encode = {
                "sub": db_user.id,
                "username": db_user.username,
                "tenant_id": db_user.tenant_id,
                "org_id": db_user.org_id,
                "role": db_user.role,
                "is_superuser": db_user.is_superuser,
                "permissions": list(permissions),
                "group_ids": group_ids,
                "exp": expire
            }
        
        encoded_jwt = jwt.encode(to_encode, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)
        
        return Token(
            access_token=encoded_jwt,
            token_type="bearer",
            expires_in=config.JWT_EXPIRATION_MINUTES * 60
        )
    
    def decode_token(self, token: str) -> Optional[TokenData]:
        """Decode and validate JWT token."""
        try:
            payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
            user_id: str = payload.get("sub")
            username: str = payload.get("username")
            tenant_id: str = payload.get("tenant_id")
            org_id: str = payload.get("org_id", config.DEFAULT_ORG_ID)
            role: str = payload.get("role")
            is_superuser: bool = payload.get("is_superuser", False)
            permissions: List[str] = payload.get("permissions", [])
            group_ids: List[str] = payload.get("group_ids", [])
            
            if user_id is None or username is None:
                return None
            
            return TokenData(
                user_id=user_id,
                username=username,
                tenant_id=tenant_id,
                org_id=org_id,
                role=Role(role),
                is_superuser=is_superuser,
                permissions=permissions,
                group_ids=group_ids
            )
        except JWTError as e:
            logger.error(f"JWT decode error: {e}")
            return None
    
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
        )
        # Include grafana_user_id if the schema supports it
        grafana_uid = getattr(user, "grafana_user_id", None)
        if grafana_uid is not None:
            schema_kwargs["grafana_user_id"] = grafana_uid
        return UserSchema(**schema_kwargs)

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
        self._lazy_init()
        username = (username or '').strip().lower()
        from sqlalchemy import func
        with get_db_session() as db:
            user = db.query(User).filter(func.lower(User.username) == username).first()
            
            if not user:
                return None
            
            if not self.verify_password(password, user.hashed_password):
                return None
            
            if not user.is_active:
                return None
            
            
            if user.username == config.DEFAULT_ADMIN_USERNAME and self.verify_password(config.DEFAULT_ADMIN_PASSWORD, user.hashed_password):
                user.needs_password_change = True
            
            
            user.last_login = datetime.now(timezone.utc)
            db.commit()
            
            
            user = db.query(User).options(
                joinedload(User.tenant),
                joinedload(User.groups).joinedload(Group.permissions),
                joinedload(User.permissions)
            ).filter_by(id=user.id).first()
            
            
            if user:
                db.expunge(user)
            
            return user
    
    def get_user_by_id(self, user_id: str) -> Optional[UserSchema]:
        """Get user by ID with relationships."""
        self._lazy_init()
        with get_db_session() as db:
            user = db.query(User).options(
                joinedload(User.groups),
                joinedload(User.permissions),
                joinedload(User.api_keys)
            ).filter_by(id=user_id).first()
            if not user:
                return None
            return self._to_user_schema(user)
    
    def get_user_by_username(self, username: str) -> Optional[UserSchema]:
        """Get user by username."""
        username = (username or '').strip().lower()
        from sqlalchemy import func
        with get_db_session() as db:
            user = db.query(User).options(joinedload(User.api_keys)).filter(func.lower(User.username) == username).first()
            if not user:
                return None
            return self._to_user_schema(user)
    
    def create_user(self, user_create: UserCreate, tenant_id: str, creator_id: str = None) -> UserSchema:
        """Create a new user."""
        with get_db_session() as db:
            normalized_username = (user_create.username or '').strip().lower()
            from sqlalchemy import func
            if db.query(User).filter(func.lower(User.username) == normalized_username).first():
                raise ValueError("Username already exists")
            
            if db.query(User).filter_by(email=user_create.email).first():
                raise ValueError("Email already exists")
            
            user = User(
                tenant_id=tenant_id,
                username=normalized_username,
                email=user_create.email,
                full_name=user_create.full_name,
                org_id=getattr(user_create, 'org_id', None) or config.DEFAULT_ORG_ID,
                role=user_create.role,
                is_active=user_create.is_active,
                hashed_password=self.hash_password(user_create.password),
                needs_password_change=True  
            )
            
            
            if user_create.group_ids:
                groups = db.query(Group).filter(
                    and_(
                        Group.id.in_(user_create.group_ids),
                        Group.tenant_id == tenant_id
                    )
                ).all()
                user.groups.extend(groups)
            
            db.add(user)
            db.flush()

            self._ensure_default_api_key(db, user)
            
            
            if creator_id:
                self._log_audit(db, tenant_id, creator_id, "create_user", "users", user.id, {
                    "username": user.username,
                    "role": user.role
                })
            
            db.commit()
            return self._to_user_schema(user)
    
    def list_users(self, tenant_id: str) -> List[UserSchema]:
        """List all users in a tenant."""
        with get_db_session() as db:
            users = db.query(User).options(joinedload(User.groups), joinedload(User.api_keys)).filter_by(tenant_id=tenant_id).all()
            return [self._to_user_schema(user) for user in users]
    
    def update_user(self, user_id: str, user_update: UserUpdate, tenant_id: str, updater_id: str = None) -> Optional[UserSchema]:
        """Update user information."""
        with get_db_session() as db:
            user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
            
            if not user:
                return None
            
            update_data = user_update.model_dump(exclude_unset=True)
            
            # Prevent users from disabling themselves
            if updater_id and user_id == updater_id and 'is_active' in update_data and update_data['is_active'] == False:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You cannot disable your own account"
                )
            
            # Prevent non-admins from modifying admin accounts
            updater_user = None
            if updater_id:
                updater_user = db.query(User).filter_by(id=updater_id, tenant_id=tenant_id).first()
            
            if user.role == Role.ADMIN and updater_user and updater_user.role != Role.ADMIN and not updater_user.is_superuser:
                # Non-admins cannot modify admin accounts
                modifiable_fields = {'group_ids'}  # Only allow modifying groups
                for field in update_data:
                    if field not in modifiable_fields:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only administrators can modify admin accounts"
                        )
            
            for field, value in update_data.items():
                if field == 'group_ids' and value is not None:
                    
                    groups = db.query(Group).filter(
                        and_(
                            Group.id.in_(value),
                            Group.tenant_id == tenant_id
                        )
                    ).all()
                    user.groups = groups
                else:
                    setattr(user, field, value)
            
            user.updated_at = datetime.now(timezone.utc)

            if 'org_id' in update_data:
                self._ensure_default_api_key(db, user)
            
            if updater_id:
                self._log_audit(db, tenant_id, updater_id, "update_user", "users", user_id, update_data)
            
            db.commit()
            return self._to_user_schema(user)

    def set_grafana_user_id(self, user_id: str, grafana_user_id: int, tenant_id: str) -> bool:
        """Store the Grafana user ID on the local user record."""
        with get_db_session() as db:
            user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
            if not user:
                return False
            user.grafana_user_id = grafana_user_id
            db.commit()
            return True
    
    def delete_user(self, user_id: str, tenant_id: str, deleter_id: str = None) -> bool:
        """Delete a user."""
        with get_db_session() as db:
            user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
            
            if not user:
                return False
            
            if deleter_id:
                self._log_audit(db, tenant_id, deleter_id, "delete_user", "users", user_id, {
                    "username": user.username
                })
            
            db.delete(user)
            db.commit()
            return True

    def list_api_keys(self, user_id: str) -> List[ApiKey]:
        self._lazy_init()
        with get_db_session() as db:
            keys = db.query(UserApiKey).filter_by(user_id=user_id).order_by(UserApiKey.created_at.asc()).all()
            return [self._to_api_key_schema(k) for k in keys]

    def create_api_key(self, user_id: str, tenant_id: str, key_create: ApiKeyCreate) -> ApiKey:
        self._lazy_init()
        with get_db_session() as db:
            user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
            if not user:
                raise ValueError("User not found")

            key_value = key_create.key or str(uuid.uuid4())
            db.query(UserApiKey).filter(
                UserApiKey.user_id == user_id,
                UserApiKey.is_enabled.is_(True)
            ).update({"is_enabled": False, "updated_at": datetime.now(timezone.utc)})

            api_key = UserApiKey(
                tenant_id=tenant_id,
                user_id=user_id,
                name=key_create.name,
                key=key_value,
                otlp_token=self._generate_otlp_token(),
                is_default=False,
                is_enabled=True
            )
            db.add(api_key)
            db.commit()
            db.refresh(api_key)
            return self._to_api_key_schema(api_key)

    def update_api_key(self, user_id: str, key_id: str, key_update: ApiKeyUpdate) -> ApiKey:
        self._lazy_init()
        with get_db_session() as db:
            api_key = db.query(UserApiKey).filter_by(id=key_id, user_id=user_id).first()
            if not api_key:
                raise ValueError("API key not found")

            if key_update.name is not None:
                api_key.name = key_update.name

            if key_update.is_default is not None and key_update.is_default:
                db.query(UserApiKey).filter(
                    UserApiKey.user_id == user_id,
                    UserApiKey.id != key_id,
                    UserApiKey.is_default.is_(True)
                ).update({"is_default": False, "updated_at": datetime.now(timezone.utc)})

                api_key.is_default = True
                api_key.is_enabled = True

                db.query(UserApiKey).filter(
                    UserApiKey.user_id == user_id,
                    UserApiKey.id != key_id,
                    UserApiKey.is_enabled.is_(True)
                ).update({"is_enabled": False, "updated_at": datetime.now(timezone.utc)})

                user = db.query(User).filter_by(id=user_id).first()
                if user:
                    user.org_id = api_key.key
                    user.updated_at = datetime.now(timezone.utc)
                db.flush()

            if key_update.is_enabled is not None:
                if api_key.is_default and not key_update.is_enabled:
                    raise ValueError("Default key cannot be disabled")
                if not key_update.is_enabled:
                    raise ValueError("At least one API key must be enabled")
                api_key.is_enabled = True
                db.flush()
                db.query(UserApiKey).filter(
                    UserApiKey.user_id == user_id,
                    UserApiKey.id != key_id,
                    UserApiKey.is_enabled.is_(True)
                ).update({"is_enabled": False, "updated_at": datetime.now(timezone.utc)})

            api_key.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(api_key)
            return self._to_api_key_schema(api_key)

    def delete_api_key(self, user_id: str, key_id: str) -> bool:
        self._lazy_init()
        with get_db_session() as db:
            api_key = db.query(UserApiKey).filter_by(id=key_id, user_id=user_id).first()
            if not api_key:
                return False
            if api_key.is_default:
                raise ValueError("Default key cannot be deleted")

            db.delete(api_key)
            db.flush()

            enabled_count = db.query(UserApiKey).filter_by(user_id=user_id, is_enabled=True).count()
            if enabled_count == 0:
                default_key = db.query(UserApiKey).filter_by(user_id=user_id, is_default=True).first()
                if default_key:
                    default_key.is_enabled = True
            db.commit()
            return True
    
    def create_group(self, group_create: GroupCreate, tenant_id: str, creator_id: str = None) -> GroupSchema:
        """Create a new group."""
        with get_db_session() as db:
            group = Group(
                tenant_id=tenant_id,
                name=group_create.name,
                description=group_create.description,
                is_active=True
            )
            
            db.add(group)
            db.flush()
            
            if creator_id:
                self._log_audit(db, tenant_id, creator_id, "create_group", "groups", group.id, {
                    "name": group.name
                })
            
            db.commit()
            group = db.query(Group).options(
                joinedload(Group.permissions)
            ).filter_by(id=group.id).first()
            return self._to_group_schema(group)
    
    def list_groups(self, tenant_id: str) -> List[GroupSchema]:
        """List all groups in a tenant."""
        with get_db_session() as db:
            groups = db.query(Group).options(joinedload(Group.permissions)).filter_by(tenant_id=tenant_id).all()
            return [self._to_group_schema(group) for group in groups]
    
    def get_group(self, group_id: str, tenant_id: str) -> Optional[GroupSchema]:
        """Get a specific group."""
        with get_db_session() as db:
            group = db.query(Group).options(joinedload(Group.permissions)).filter_by(id=group_id, tenant_id=tenant_id).first()
            if not group:
                return None
            return self._to_group_schema(group)
    
    def delete_group(self, group_id: str, tenant_id: str, deleter_id: str = None) -> bool:
        """Delete a group."""
        with get_db_session() as db:
            group = db.query(Group).filter_by(id=group_id, tenant_id=tenant_id).first()
            
            if not group:
                return False
            
            if deleter_id:
                self._log_audit(db, tenant_id, deleter_id, "delete_group", "groups", group_id, {
                    "name": group.name
                })
            
            db.delete(group)
            db.commit()
            return True

    def update_group(self, group_id: str, group_update: GroupUpdate, tenant_id: str, updater_id: str = None) -> Optional[GroupSchema]:
        """Update group information."""
        with get_db_session() as db:
            group = db.query(Group).filter_by(id=group_id, tenant_id=tenant_id).first()
            if not group:
                return None

            update_data = group_update.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                setattr(group, field, value)

            group.updated_at = datetime.now(timezone.utc)

            if updater_id:
                self._log_audit(db, tenant_id, updater_id, "update_group", "groups", group_id, update_data)

            db.commit()
            group = db.query(Group).options(
                joinedload(Group.permissions)
            ).filter_by(id=group_id).first()
            return self._to_group_schema(group)
    
    def update_user_permissions(self, user_id: str, permission_names: List[str], tenant_id: str) -> bool:
        """Update user's direct permissions."""
        with get_db_session() as db:
            user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
            if not user:
                return False
            
            
            permissions = db.query(Permission).filter(Permission.name.in_(permission_names)).all()
            user.permissions = permissions
            
            db.commit()
            return True
    
    def update_group_permissions(self, group_id: str, permission_names: List[str], tenant_id: str) -> bool:
        """Update group's permissions."""
        with get_db_session() as db:
            group = db.query(Group).filter_by(id=group_id, tenant_id=tenant_id).first()
            if not group:
                return False
            
            
            permissions = db.query(Permission).filter(Permission.name.in_(permission_names)).all()
            group.permissions = permissions
            
            db.commit()
            return True

    def update_group_members(self, group_id: str, user_ids: List[str], tenant_id: str) -> bool:
        """Update group's member users."""
        with get_db_session() as db:
            group = db.query(Group).filter_by(id=group_id, tenant_id=tenant_id).first()
            if not group:
                return False

            members = []
            if user_ids:
                members = db.query(User).filter(
                    and_(
                        User.id.in_(user_ids),
                        User.tenant_id == tenant_id
                    )
                ).all()

            group.members = members
            db.commit()
            return True
    
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
        with get_db_session() as db:
            user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()
            
            if not user:
                return False
            
            if not self.verify_password(password_update.current_password, user.hashed_password):
                return False
            
            
            if len(password_update.new_password) < 8:
                raise ValueError("Password must be at least 8 characters long")
            
            user.hashed_password = self.hash_password(password_update.new_password)
            user.needs_password_change = False  
            db.commit()
            return True
    
    def validate_otlp_token(self, token: str) -> Optional[str]:
        """Validate an OTLP ingest token and return the mapped org_id (key).

        Used by the OTLP gateway to authenticate incoming telemetry and
        resolve the X-Scope-OrgID to set on the upstream request.

        A token is valid when:
        - it matches an existing ``UserApiKey.otlp_token``
        - the owning user account is active

        Note: ``is_enabled`` is intentionally **not** checked here.  That
        flag controls which key is the user's *active session key* in the
        UI and should not invalidate OTLP ingest tokens.  To revoke a
        token, delete the API key instead.

        Returns the API key value (org_id) if valid, None otherwise.
        """
        if not token:
            return None
        with get_db_session() as db:
            api_key = (
                db.query(UserApiKey)
                .join(User, User.id == UserApiKey.user_id)
                .filter(
                    UserApiKey.otlp_token == token,
                    User.is_active.is_(True),
                )
                .first()
            )
            if not api_key:
                return None
            return api_key.key

    def backfill_otlp_tokens(self):
        """Generate otlp_token for any existing API keys that lack one.

        Called once at startup after the column migration.
        """
        with get_db_session() as db:
            keys_without_token = db.query(UserApiKey).filter(
                UserApiKey.otlp_token.is_(None)
            ).all()
            for key in keys_without_token:
                key.otlp_token = self._generate_otlp_token()
                key.updated_at = datetime.now(timezone.utc)
            if keys_without_token:
                db.commit()
                logger.info("Backfilled otlp_token for %d API keys", len(keys_without_token))

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
