"""Authentication/token/password operations for DatabaseAuthService."""

from datetime import datetime, timezone, timedelta
from typing import Optional, List

from jose import JWTError, jwt
from sqlalchemy.orm import joinedload
from sqlalchemy import func

from config import config
from database import get_db_session
from db_models import User, Group, UserApiKey
from models.access.auth_models import Role, Token, TokenData

# expose a reference to the create_mfa_setup_token operation for service layer
create_mfa_setup_token_op = create_mfa_setup_token if 'create_mfa_setup_token' in globals() else None


def create_access_token(service, user: User) -> Token:
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

        permissions = service._collect_permissions(db_user)
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


def create_mfa_setup_token(service, user: User, minutes: int = 10) -> Token:
    """Create a short-lived token usable only for MFA setup endpoints.

    The token includes the claim `mfa_setup: True` so the middleware can
    allow MFA enroll/verify calls without granting full app permissions.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    to_encode = {
        "sub": user.id,
        "username": user.username,
        "tenant_id": user.tenant_id,
        "mfa_setup": True,
        "exp": expire,
    }
    encoded_jwt = jwt.encode(to_encode, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)
    return Token(access_token=encoded_jwt, token_type="bearer", expires_in=minutes * 60)


def decode_token(service, token: str) -> Optional[TokenData]:
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
        is_mfa_setup: bool = payload.get("mfa_setup", False)

        if user_id is None or username is None:
            return None

        td = TokenData(
            user_id=user_id,
            username=username,
            tenant_id=tenant_id,
            org_id=org_id,
            role=Role(role) if role is not None else Role.USER,
            is_superuser=is_superuser,
            permissions=permissions,
            group_ids=group_ids
        )
        # Attach mfa_setup marker when present in JWT payload so callers may
        # treat it specially (limited setup token).
        setattr(td, 'is_mfa_setup', is_mfa_setup)
        return td
    except JWTError as e:
        service.logger.error(f"JWT decode error: {e}")
        return None


def authenticate_user(service, username: str, password: str) -> Optional[User]:
    service._lazy_init()
    username = (username or '').strip().lower()
    with get_db_session() as db:
        user = db.query(User).filter(func.lower(User.username) == username).first()

        if not user:
            return None

        if not service.verify_password(password, user.hashed_password):
            return None

        if not user.is_active:
            return None

        if user.username == config.DEFAULT_ADMIN_USERNAME and service.verify_password(config.DEFAULT_ADMIN_PASSWORD, user.hashed_password):
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


def update_password(service, user_id: str, password_update, tenant_id: str) -> bool:
    with get_db_session() as db:
        user = db.query(User).filter_by(id=user_id, tenant_id=tenant_id).first()

        if not user:
            return False

        if not service.verify_password(password_update.current_password, user.hashed_password):
            return False

        if service.verify_password(password_update.new_password, user.hashed_password):
            raise ValueError("New password must be different from current password")

        if len(password_update.new_password) < 8:
            raise ValueError("Password must be at least 8 characters long")

        user.hashed_password = service.hash_password(password_update.new_password)
        user.needs_password_change = False
        db.commit()
        return True


def validate_otlp_token(service, token: str) -> Optional[str]:
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
