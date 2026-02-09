import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import config
from models.auth_models import (
    LoginRequest, RegisterRequest, Token, UserResponse,
    UserCreate, UserUpdate, UserPasswordUpdate,
    Group, GroupCreate, GroupUpdate, TokenData, Permission, ROLE_PERMISSIONS,
    ApiKey, ApiKeyCreate, ApiKeyUpdate
)
try:
    from services.database_auth_service import DatabaseAuthService
    auth_service = DatabaseAuthService()
except Exception:
    from services.auth_service import AuthService
    auth_service = AuthService()

logger = logging.getLogger(__name__)

USER_NOT_FOUND = "User not found"
GROUP_NOT_FOUND = "Group not found"

router = APIRouter(prefix="/api/auth", tags=["authentication"])
security = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenData:
    token = credentials.credentials
    token_data = auth_service.decode_token(token)
    
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Normalize token payload to TokenData model so callers can rely on attribute access
    if isinstance(token_data, dict):
        try:
            token_data = TokenData(**token_data)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )

    user = auth_service.get_user_by_id(token_data.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    try:
        token_data.org_id = getattr(user, "org_id", token_data.org_id)
    except Exception:
        pass
    
    return token_data


def require_permission(permission):
    """Dependency that requires a specific permission.

    Accepts either a `Permission` enum or a string.
    """
    perm_value = permission.value if hasattr(permission, "value") else str(permission)

    def permission_checker(current_user: TokenData = Depends(get_current_user)):
        user = auth_service.get_user_by_id(current_user.user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
                headers={"WWW-Authenticate": "Bearer"}
            )

        user_perms = (
            auth_service.get_user_permissions(user)
            if hasattr(auth_service, "get_user_permissions")
            else (getattr(current_user, "permissions", []) or [])
        )
        try:
            current_user.permissions = user_perms
        except Exception:
            pass

        if perm_value not in user_perms and not getattr(current_user, "is_superuser", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You don't have the permission to {perm_value.upper()}, please contact your administrator if you think this is a mistake."
            )
        return current_user

    return permission_checker


@router.post("/login", response_model=Token)
async def login(login_request: LoginRequest):
    user = auth_service.authenticate_user(login_request.username, login_request.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = auth_service.create_access_token(user)
    return token


@router.post("/register", response_model=UserResponse)
async def register(register_request: RegisterRequest):
    try:
        user_create = UserCreate(
            username=register_request.username,
            email=register_request.email,
            password=register_request.password,
            full_name=register_request.full_name
        )
        
        user = auth_service.create_user(user_create, tenant_id=config.DEFAULT_ORG_ID)
        
        permissions = ROLE_PERMISSIONS.get(user.role, [])
        
        return UserResponse(
            **user.model_dump(),
            permissions=permissions,
            direct_permissions=(
                auth_service.get_user_direct_permissions(user)
                if hasattr(auth_service, "get_user_direct_permissions")
                else []
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: TokenData = Depends(get_current_user)):
    user = auth_service.get_user_by_id(current_user.user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=USER_NOT_FOUND
        )
    
    permissions = (
        auth_service.get_user_permissions(user)
        if hasattr(auth_service, "get_user_permissions")
        else current_user.permissions
    )
    return UserResponse(
        **user.model_dump(exclude={"hashed_password"}),
        permissions=permissions,
        direct_permissions=(
            auth_service.get_user_direct_permissions(user)
            if hasattr(auth_service, "get_user_direct_permissions")
            else []
        )
    )


@router.put("/me", response_model=UserResponse)
async def update_current_user_info(
    user_update: UserUpdate,
    current_user: TokenData = Depends(get_current_user)
):
    update_data = user_update.model_dump(exclude_unset=True)
    for field in ("role", "group_ids", "is_active"):
        update_data.pop(field, None)
    user_update = UserUpdate(**update_data)
    try:
        updated_user = auth_service.update_user(
            current_user.user_id,
            user_update,
            current_user.tenant_id,
            updater_id=current_user.user_id
        ) if hasattr(auth_service, "update_user") else None
    except TypeError:
        updated_user = auth_service.update_user(
            current_user.user_id,
            user_update,
            current_user.tenant_id
        )

    if not updated_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)

    permissions = (
        auth_service.get_user_permissions(updated_user)
        if hasattr(auth_service, "get_user_permissions")
        else current_user.permissions
    )
    return UserResponse(
        **updated_user.model_dump(exclude={"hashed_password"}),
        permissions=permissions,
        direct_permissions=(
            auth_service.get_user_direct_permissions(updated_user)
            if hasattr(auth_service, "get_user_direct_permissions")
            else []
        )
    )


@router.get("/api-keys", response_model=List[ApiKey])
async def list_api_keys(current_user: TokenData = Depends(get_current_user)):
    return auth_service.list_api_keys(current_user.user_id)


@router.post("/api-keys", response_model=ApiKey)
async def create_api_key(
    key_create: ApiKeyCreate,
    current_user: TokenData = Depends(get_current_user)
):
    try:
        try:
            return auth_service.create_api_key(current_user.user_id, current_user.tenant_id, key_create)
        except TypeError:
            return auth_service.create_api_key(current_user.user_id, key_create)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/api-keys/{key_id}", response_model=ApiKey)
async def update_api_key(
    key_id: str,
    key_update: ApiKeyUpdate,
    current_user: TokenData = Depends(get_current_user)
):
    try:
        return auth_service.update_api_key(current_user.user_id, key_id, key_update)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    try:
        success = auth_service.delete_api_key(current_user.user_id, key_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return {"message": "API key deleted"}


@router.get("/users", response_model=List[UserResponse])
async def list_users(current_user: TokenData = Depends(require_permission(Permission.MANAGE_USERS))):
    users = auth_service.list_users(current_user.tenant_id)
    return [
        UserResponse(
            **user.model_dump(),
            permissions=(
                auth_service.get_user_permissions(user)
                if hasattr(auth_service, "get_user_permissions")
                else ROLE_PERMISSIONS.get(user.role, [])
            ),
            direct_permissions=(
                auth_service.get_user_direct_permissions(user)
                if hasattr(auth_service, "get_user_direct_permissions")
                else []
            )
        )
        for user in users
    ]


@router.post("/users", response_model=UserResponse)
async def create_user(
    user_create: UserCreate,
    current_user: TokenData = Depends(require_permission(Permission.MANAGE_USERS))
):
    try:
        user = auth_service.create_user(user_create, current_user.tenant_id)
        
        permissions = (
            auth_service.get_user_permissions(user)
            if hasattr(auth_service, "get_user_permissions")
            else ROLE_PERMISSIONS.get(user.role, [])
        )
        return UserResponse(
            **user.model_dump(),
            permissions=permissions,
            direct_permissions=(
                auth_service.get_user_direct_permissions(user)
                if hasattr(auth_service, "get_user_direct_permissions")
                else []
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_update: UserUpdate,
    current_user: TokenData = Depends(require_permission(Permission.MANAGE_USERS))
):
    user = auth_service.update_user(user_id, user_update, current_user.tenant_id)
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)
    
    permissions = (
        auth_service.get_user_permissions(user)
        if hasattr(auth_service, "get_user_permissions")
        else ROLE_PERMISSIONS.get(user.role, [])
    )
    return UserResponse(
        **user.model_dump(),
        permissions=permissions,
        direct_permissions=(
            auth_service.get_user_direct_permissions(user)
            if hasattr(auth_service, "get_user_direct_permissions")
            else []
        )
    )


@router.put("/users/{user_id}/password")
async def update_user_password(
    user_id: str,
    password_update: UserPasswordUpdate,
    current_user: TokenData = Depends(get_current_user)
):
    if current_user.user_id != user_id:
        user_obj = auth_service.get_user_by_id(current_user.user_id)
        user_perms = (
            auth_service.get_user_permissions(user_obj)
            if hasattr(auth_service, "get_user_permissions")
            else (getattr(current_user, "permissions", []) or [])
        )
        if Permission.MANAGE_USERS.value not in user_perms and not getattr(current_user, "is_superuser", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot update another user's password"
            )
    
    success = auth_service.update_password(user_id, password_update, current_user.tenant_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    return {"message": "Password updated successfully"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: TokenData = Depends(require_permission(Permission.MANAGE_USERS))
):
    if current_user.user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    success = auth_service.delete_user(user_id, current_user.tenant_id)
    
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)
    
    return {"message": "User deleted successfully"}


@router.get("/groups", response_model=List[Group])
async def list_groups(current_user: TokenData = Depends(require_permission(Permission.READ_GROUPS))):
    return auth_service.list_groups(current_user.tenant_id)


@router.post("/groups", response_model=Group)
async def create_group(
    group_create: GroupCreate,
    current_user: TokenData = Depends(require_permission(Permission.MANAGE_GROUPS))
):
    return auth_service.create_group(group_create, current_user.tenant_id)


@router.get("/groups/{group_id}", response_model=Group)
async def get_group(
    group_id: str,
    current_user: TokenData = Depends(require_permission(Permission.MANAGE_GROUPS))
):
    group = auth_service.get_group(group_id, current_user.tenant_id)
    
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GROUP_NOT_FOUND)
    
    return group


@router.put("/groups/{group_id}", response_model=Group)
async def update_group(
    group_id: str,
    group_update: GroupUpdate,
    current_user: TokenData = Depends(require_permission(Permission.MANAGE_GROUPS))
):
    group = auth_service.update_group(group_id, group_update, current_user.tenant_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GROUP_NOT_FOUND)
    return group


@router.put("/groups/{group_id}", response_model=Group)
async def update_group(
    group_id: str,
    group_update: GroupUpdate,
    current_user: TokenData = Depends(require_permission(Permission.MANAGE_GROUPS))
):
    group = auth_service.update_group(group_id, group_update, current_user.tenant_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return group


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: str,
    current_user: TokenData = Depends(require_permission(Permission.MANAGE_GROUPS))
):
    success = auth_service.delete_group(group_id, current_user.tenant_id)
    
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GROUP_NOT_FOUND)
    
    return {"message": "Group deleted successfully"}


@router.put("/users/{user_id}/permissions")
async def update_user_permissions(
    user_id: str,
    permission_names: List[str],
    current_user: TokenData = Depends(require_permission(Permission.MANAGE_USERS))
):
    """Update user's direct permissions."""
    success = auth_service.update_user_permissions(user_id, permission_names, current_user.tenant_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)
    return {"success": True, "permissions": permission_names}


@router.put("/groups/{group_id}/permissions")
async def update_group_permissions(
    group_id: str,
    permission_names: List[str],
    current_user: TokenData = Depends(require_permission(Permission.MANAGE_GROUPS))
):
    """Update group's permissions."""
    success = auth_service.update_group_permissions(group_id, permission_names, current_user.tenant_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GROUP_NOT_FOUND)
    return {"success": True, "permissions": permission_names}


@router.get("/permissions")
async def list_all_permissions(current_user: TokenData = Depends(get_current_user)):
    """List all available permissions."""
    return auth_service.list_all_permissions()


@router.get("/role-defaults")
async def list_role_defaults(current_user: TokenData = Depends(get_current_user)):
    """List role default permissions."""
    return {
        role.value: [perm.value for perm in perms]
        for role, perms in ROLE_PERMISSIONS.items()
    }
