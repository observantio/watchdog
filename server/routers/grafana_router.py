"""Grafana API router with multi-tenancy, labels, hide/show, team filtering, and UID search."""
from fastapi import APIRouter, HTTPException, Query, Body, Depends, status, Request
from fastapi.responses import StreamingResponse, Response
from typing import Optional, List, Dict
import httpx
import logging

from models.grafana_models import (
    DashboardCreate, DashboardUpdate, DashboardSearchResult,
    Datasource, DatasourceCreate, DatasourceUpdate, Folder
)
from services.grafana_proxy_service import GrafanaProxyService
from services.grafana_service import GrafanaService
from models.auth_models import Permission, TokenData, Role
from database import get_db
from sqlalchemy.orm import Session

from routers.auth_router import require_permission
from services.database_auth_service import DatabaseAuthService
from middleware.rate_limit import enforce_rate_limit
from config import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/grafana", tags=["grafana"])

grafana_proxy_service = GrafanaProxyService()
grafana_service = GrafanaService()
auth_service = DatabaseAuthService()


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def _user_group_ids(current_user: TokenData) -> List[str]:
    return getattr(current_user, "group_ids", []) or []


def _rate_limit(current_user: TokenData):
    enforce_rate_limit(
        key=f"user:{current_user.user_id}:grafana",
        limit=config.RATE_LIMIT_USER_PER_MINUTE,
        window_seconds=60,
    )


# ==================================================================
# Dashboard endpoints
# ==================================================================

@router.get(
    "/dashboards/search",
    response_model=List[DashboardSearchResult],
    summary="Search dashboards",
    description="Search Grafana dashboards with multi-tenant access control, UID search, label and team filtering",
)
async def search_dashboards(
    query: Optional[str] = Query(None, description="Search query"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    starred: Optional[bool] = Query(None, description="Filter starred dashboards"),
    uid: Optional[str] = Query(None, description="Search by exact dashboard UID"),
    label_key: Optional[str] = Query(None, description="Filter by label key"),
    label_value: Optional[str] = Query(None, description="Filter by label value (requires label_key)"),
    team_id: Optional[str] = Query(None, description="Filter by team/group ID"),
    show_hidden: bool = Query(False, description="Include hidden dashboards"),
    current_user: TokenData = Depends(require_permission(Permission.READ_DASHBOARDS)),
    db: Session = Depends(get_db),
) -> List[DashboardSearchResult]:
    _rate_limit(current_user)
    return await grafana_proxy_service.search_dashboards(
        db=db,
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=_user_group_ids(current_user),
        query=query,
        tag=tag,
        starred=starred,
        uid=uid,
        label_key=label_key,
        label_value=label_value,
        team_id=team_id,
        show_hidden=show_hidden,
    )


@router.get("/dashboards/{uid}")
async def get_dashboard(
    uid: str,
    current_user: TokenData = Depends(require_permission(Permission.READ_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Get a dashboard by UID with access control."""
    _rate_limit(current_user)
    dashboard = await grafana_proxy_service.get_dashboard(
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=_user_group_ids(current_user),
    )
    if not dashboard:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found or access denied")
    return dashboard


@router.post("/dashboards")
async def create_dashboard(
    dashboard: DashboardCreate = Body(...),
    visibility: str = Query("private"),
    shared_group_ids: Optional[List[str]] = Query(None),
    labels: Optional[str] = Query(None, description="JSON string of key-value labels"),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Create a new dashboard with visibility, groups, and labels."""
    _rate_limit(current_user)
    if visibility not in ("private", "group", "tenant"):
        raise HTTPException(status_code=400, detail="Invalid visibility value")

    # Check if user is admin
    from models.auth_models import Role
    is_admin = current_user.role == Role.ADMIN or current_user.is_superuser

    parsed_labels = _parse_labels(labels)
    result = await grafana_proxy_service.create_dashboard(
        db=db, dashboard_create=dashboard, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=_user_group_ids(current_user),
        visibility=visibility, shared_group_ids=shared_group_ids or [],
        labels=parsed_labels, is_admin=is_admin,
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create dashboard")
    return result


@router.put("/dashboards/{uid}")
async def update_dashboard(
    uid: str,
    dashboard: DashboardUpdate = Body(...),
    visibility: Optional[str] = Query(None),
    shared_group_ids: Optional[List[str]] = Query(None),
    labels: Optional[str] = Query(None, description="JSON string of key-value labels"),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Update an existing dashboard with access control."""
    _rate_limit(current_user)
    if visibility and visibility not in ("private", "group", "tenant"):
        raise HTTPException(status_code=400, detail="Invalid visibility value")

    parsed_labels = _parse_labels(labels)
    result = await grafana_proxy_service.update_dashboard(
        db=db, uid=uid, dashboard_update=dashboard, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=_user_group_ids(current_user),
        visibility=visibility, shared_group_ids=shared_group_ids,
        labels=parsed_labels,
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found, access denied, or update failed")
    return result


@router.delete("/dashboards/{uid}")
async def delete_dashboard(
    uid: str,
    current_user: TokenData = Depends(require_permission(Permission.DELETE_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Delete a dashboard with access control."""
    _rate_limit(current_user)
    success = await grafana_proxy_service.delete_dashboard(
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=_user_group_ids(current_user),
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found, access denied, or delete failed")
    return {"status": "success", "message": f"Dashboard {uid} deleted"}


# ------------------------------------------------------------------
# Dashboard hide/show
# ------------------------------------------------------------------

@router.post("/dashboards/{uid}/hide")
async def hide_dashboard(
    uid: str,
    hidden: bool = Body(True, embed=True),
    current_user: TokenData = Depends(require_permission(Permission.READ_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Hide or unhide a dashboard for the current user."""
    _rate_limit(current_user)
    success = grafana_proxy_service.toggle_dashboard_hidden(
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, hidden=hidden,
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found")
    return {"status": "success", "hidden": hidden}


# ------------------------------------------------------------------
# Dashboard labels
# ------------------------------------------------------------------

@router.put("/dashboards/{uid}/labels")
async def update_dashboard_labels(
    uid: str,
    labels: Dict[str, str] = Body(...),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Update labels on a dashboard (owner only)."""
    _rate_limit(current_user)
    success = grafana_proxy_service.update_dashboard_labels(
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=_user_group_ids(current_user),
        labels=labels,
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found or access denied")
    return {"status": "success", "labels": labels}


# ==================================================================
# Datasource endpoints
# ==================================================================

@router.get("/datasources", response_model=List[Datasource])
async def get_datasources(
    uid: Optional[str] = Query(None, description="Search by exact datasource UID"),
    label_key: Optional[str] = Query(None),
    label_value: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    show_hidden: bool = Query(False),
    current_user: TokenData = Depends(require_permission(Permission.READ_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Get all datasources with multi-tenant access control and filtering."""
    _rate_limit(current_user)
    return await grafana_proxy_service.get_datasources(
        db=db, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=_user_group_ids(current_user),
        uid=uid, label_key=label_key, label_value=label_value,
        team_id=team_id, show_hidden=show_hidden,
    )


@router.get("/datasources/uid/{uid}", response_model=Datasource)
async def get_datasource_by_uid(
    uid: str,
    current_user: TokenData = Depends(require_permission(Permission.READ_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Get a datasource by UID with access control."""
    _rate_limit(current_user)
    datasource = await grafana_proxy_service.get_datasource(
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=_user_group_ids(current_user),
    )
    if not datasource:
        raise HTTPException(status_code=404, detail=f"Datasource {uid} not found or access denied")
    return datasource


@router.get("/datasources/name/{name}", response_model=Datasource)
async def get_datasource_by_name(
    name: str,
    current_user: TokenData = Depends(require_permission(Permission.READ_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Get a datasource by name with access control."""
    _rate_limit(current_user)
    datasource = await grafana_service.get_datasource_by_name(name)
    if not datasource:
        raise HTTPException(status_code=404, detail=f"Datasource {name} not found")
    accessible = await grafana_proxy_service.get_datasource(
        db=db, uid=datasource.uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=_user_group_ids(current_user),
    )
    if not accessible:
        raise HTTPException(status_code=404, detail=f"Datasource {name} not found or access denied")
    return datasource


@router.post("/datasources", response_model=Datasource)
async def create_datasource(
    datasource: DatasourceCreate = Body(...),
    visibility: str = Query("private"),
    shared_group_ids: Optional[List[str]] = Query(None),
    labels: Optional[str] = Query(None, description="JSON string of key-value labels"),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Create a new datasource with visibility control and labels."""
    _rate_limit(current_user)
    if visibility not in ("private", "group", "tenant"):
        raise HTTPException(status_code=400, detail="Invalid visibility value")
    
    # Check if user is admin
    from models.auth_models import Role
    is_admin = current_user.role == Role.ADMIN or current_user.is_superuser
    
    parsed_labels = _parse_labels(labels)
    result = await grafana_proxy_service.create_datasource(
        db=db, datasource_create=datasource, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=_user_group_ids(current_user),
        visibility=visibility, shared_group_ids=shared_group_ids or [],
        labels=parsed_labels, is_admin=is_admin,
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create datasource")
    return result


@router.put("/datasources/{uid}", response_model=Datasource)
async def update_datasource(
    uid: str,
    datasource: DatasourceUpdate = Body(...),
    visibility: Optional[str] = Query(None),
    shared_group_ids: Optional[List[str]] = Query(None),
    labels: Optional[str] = Query(None),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Update an existing datasource with access control."""
    _rate_limit(current_user)
    if visibility and visibility not in ("private", "group", "tenant"):
        raise HTTPException(status_code=400, detail="Invalid visibility value")
    parsed_labels = _parse_labels(labels)
    result = await grafana_proxy_service.update_datasource(
        db=db, uid=uid, datasource_update=datasource, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=_user_group_ids(current_user),
        visibility=visibility, shared_group_ids=shared_group_ids,
        labels=parsed_labels,
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Datasource {uid} not found, access denied, or update failed")
    return result


@router.delete("/datasources/{uid}")
async def delete_datasource(
    uid: str,
    current_user: TokenData = Depends(require_permission(Permission.DELETE_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Delete a datasource with access control."""
    _rate_limit(current_user)
    success = await grafana_proxy_service.delete_datasource(
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=_user_group_ids(current_user),
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Datasource {uid} not found, access denied, or delete failed")
    return {"status": "success", "message": f"Datasource {uid} deleted"}


# ------------------------------------------------------------------
# Datasource hide/show
# ------------------------------------------------------------------

@router.post("/datasources/{uid}/hide")
async def hide_datasource(
    uid: str,
    hidden: bool = Body(True, embed=True),
    current_user: TokenData = Depends(require_permission(Permission.READ_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Hide or unhide a datasource for the current user."""
    _rate_limit(current_user)
    success = grafana_proxy_service.toggle_datasource_hidden(
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, hidden=hidden,
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Datasource {uid} not found")
    return {"status": "success", "hidden": hidden}


# ------------------------------------------------------------------
# Datasource labels
# ------------------------------------------------------------------

@router.put("/datasources/{uid}/labels")
async def update_datasource_labels(
    uid: str,
    labels: Dict[str, str] = Body(...),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Update labels on a datasource (owner only)."""
    _rate_limit(current_user)
    success = grafana_proxy_service.update_datasource_labels(
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=_user_group_ids(current_user),
        labels=labels,
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Datasource {uid} not found or access denied")
    return {"status": "success", "labels": labels}


# ==================================================================
# Metadata endpoints (for filter dropdowns in UI)
# ==================================================================

@router.get("/dashboards/meta/filters")
async def get_dashboard_filter_metadata(
    current_user: TokenData = Depends(require_permission(Permission.READ_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Get label keys/values and team IDs used across dashboards for building filter UI."""
    _rate_limit(current_user)
    return grafana_proxy_service.get_dashboard_metadata(db=db, tenant_id=current_user.tenant_id)


@router.get("/datasources/meta/filters")
async def get_datasource_filter_metadata(
    current_user: TokenData = Depends(require_permission(Permission.READ_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Get label keys/values and team IDs used across datasources for building filter UI."""
    _rate_limit(current_user)
    return grafana_proxy_service.get_datasource_metadata(db=db, tenant_id=current_user.tenant_id)


# ==================================================================
# Folder endpoints (not multi-tenant yet)
# ==================================================================

@router.get("/view/d/{uid}/{slug}")
@router.get("/view/d/{uid}")
async def grafana_dashboard_view(
    uid: str,
    slug: str = "",
    request: Request = None,
    token: Optional[str] = Query(None, description="Optional JWT token for browser direct access"),
    db: Session = Depends(get_db),
):
    """Return HTML page with embedded Grafana dashboard iframe."""
    
    # Verify token and check access control
    current_user: Optional[TokenData] = None
    token_to_verify = None
    
    if request:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token_to_verify = auth_header.split(" ", 1)[1]
    if not token_to_verify and token:
        token_to_verify = token
    
    if not token_to_verify:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        from jose import jwt, JWTError
        payload = jwt.decode(token_to_verify, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
        permissions = payload.get("permissions", [])
        
        if Permission.READ_DASHBOARDS.value not in permissions:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        current_user = TokenData(
            user_id=payload.get("sub"),
            username=payload.get("username"),
            tenant_id=payload.get("tenant_id"),
            org_id=payload.get("org_id", ""),
            role=Role(payload.get("role", "user")),
            is_superuser=payload.get("is_superuser", False),
            permissions=permissions,
            group_ids=payload.get("group_ids", []),
        )
    except (JWTError, Exception) as e:
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    
    # Check dashboard access control (same as proxy endpoint)
    from db_models import GrafanaDashboard
    dashboard = db.query(GrafanaDashboard).filter(GrafanaDashboard.grafana_uid == uid).first()
    
    if dashboard:
        # Check tenant isolation
        if dashboard.tenant_id != current_user.tenant_id:
            logger.warning(f"Tenant mismatch for dashboard {uid}")
            raise HTTPException(status_code=404, detail="Dashboard not found")
        
        # Check if hidden
        if dashboard.hidden_by and current_user.user_id in dashboard.hidden_by:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        
        # Check visibility
        is_admin = current_user.role == Role.ADMIN or current_user.is_superuser
        is_owner = dashboard.created_by == current_user.user_id
        
        if not is_admin and not is_owner:
            if dashboard.visibility == "private":
                raise HTTPException(status_code=403, detail="Access denied: Dashboard is private")
            elif dashboard.visibility == "group":
                user_group_ids = set(current_user.group_ids)
                dashboard_group_ids = {g.id for g in dashboard.shared_groups}
                if not user_group_ids.intersection(dashboard_group_ids):
                    raise HTTPException(status_code=403, detail="Access denied: Dashboard is group-restricted")
    
    # Build iframe URL - use localhost:3000 with anonymous Editor access
    # No kiosk mode - full interactive Grafana UI
    dashboard_url = f"http://localhost:3000/d/{uid}/{slug}"
    
    # Return HTML with iframe
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - {slug or uid}</title>
    <style>
        body {{ margin: 0; padding: 0; overflow: hidden; background: #1f1f1f; }}
        iframe {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: none; }}
        .loading {{ 
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
            color: #fff; font-family: sans-serif; font-size: 18px;
        }}
    </style>
</head>
<body>
    <div class="loading">Loading dashboard...</div>
    <iframe src="{dashboard_url}" allow="fullscreen"></iframe>
    <script>
        // Hide loading message once iframe loads
        document.querySelector('iframe').addEventListener('load', function() {{
            document.querySelector('.loading').style.display = 'none';
        }});
    </script>
</body>
</html>
    """
    
    return Response(content=html_content, media_type="text/html")


@router.api_route("/proxy/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def grafana_auth_proxy(
    path: str,
    request: Request,
    token: Optional[str] = Query(None, description="Optional JWT token for browser direct access"),
    db: Session = Depends(get_db),
):
    """Proxy Grafana API calls with auth-proxy headers. NOT for serving dashboards in browser (use /view endpoint)."""
    
    # Get authentication from either Authorization header or token query param
    current_user: Optional[TokenData] = None
    token_to_verify = None
    
    # Check Authorization header first
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token_to_verify = auth_header.split(" ", 1)[1]
    # Fallback to query parameter for browser links
    elif token:
        token_to_verify = token
    
    if not token_to_verify:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Verify JWT token
    try:
        from jose import jwt, JWTError
        payload = jwt.decode(token_to_verify, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
        
        # Extract user data
        permissions = payload.get("permissions", [])
        user_role = payload.get("role", "user")
        
        # Verify READ_DASHBOARDS permission
        if Permission.READ_DASHBOARDS.value not in permissions:
            logger.warning(f"User {payload.get('username')} lacks READ_DASHBOARDS permission")
            raise HTTPException(status_code=403, detail="Insufficient permissions to access Grafana")
        
        current_user = TokenData(
            user_id=payload.get("sub"),
            username=payload.get("username"),
            tenant_id=payload.get("tenant_id"),
            org_id=payload.get("org_id", ""),
            role=Role(user_role),
            is_superuser=payload.get("is_superuser", False),
            permissions=permissions,
            group_ids=payload.get("group_ids", []),
        )
        
        logger.info(f"Proxy auth successful for user: {current_user.username} (tenant: {current_user.tenant_id})")
        
    except JWTError as e:
        logger.error(f"JWT decode failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token")
    except Exception as e:
        logger.error(f"Token verification failed: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail="Authentication failed")
    
    _rate_limit(current_user)

    # Extract dashboard UID from path for access control
    # Paths like: /d/<uid>/<slug> or /api/dashboards/uid/<uid>
    dashboard_uid = None
    datasource_uid = None
    
    if "/d/" in path:
        parts = path.split("/d/")
        if len(parts) > 1:
            dashboard_uid = parts[1].split("/")[0].split("?")[0]
    elif "/api/dashboards/uid/" in path:
        parts = path.split("/api/dashboards/uid/")
        if len(parts) > 1:
            dashboard_uid = parts[1].split("/")[0].split("?")[0]
    elif "/api/datasources/uid/" in path or "/connections/datasources/edit/" in path:
        # Extract datasource UID from paths like /api/datasources/uid/<uid> or /connections/datasources/edit/<uid>
        if "/api/datasources/uid/" in path:
            parts = path.split("/api/datasources/uid/")
        else:
            parts = path.split("/connections/datasources/edit/")
        if len(parts) > 1:
            datasource_uid = parts[1].split("/")[0].split("?")[0]
    
    # Enforce multi-tenant dashboard access control
    if dashboard_uid:
        from db_models import GrafanaDashboard
        dashboard = db.query(GrafanaDashboard).filter(
            GrafanaDashboard.grafana_uid == dashboard_uid
        ).first()
        
        if dashboard:
            # Check tenant isolation
            if dashboard.tenant_id != current_user.tenant_id:
                logger.warning(
                    f"Tenant mismatch: User {current_user.username} (tenant {current_user.tenant_id}) "
                    f"attempted to access dashboard {dashboard_uid} (tenant {dashboard.tenant_id})"
                )
                raise HTTPException(status_code=404, detail="Dashboard not found")
            
            # Check if dashboard is hidden for this user
            if dashboard.hidden_by and current_user.user_id in dashboard.hidden_by:
                logger.warning(f"User {current_user.username} attempted to access hidden dashboard {dashboard_uid}")
                raise HTTPException(status_code=404, detail="Dashboard not found")
            
            # Check visibility and group access
            is_admin = current_user.role == Role.ADMIN or current_user.is_superuser
            is_owner = dashboard.created_by == current_user.user_id
            
            if not is_admin and not is_owner:
                if dashboard.visibility == "private":
                    logger.warning(
                        f"User {current_user.username} attempted to access private dashboard {dashboard_uid} "
                        f"(owner: {dashboard.created_by})"
                    )
                    raise HTTPException(status_code=403, detail="Access denied: Dashboard is private")
                
                elif dashboard.visibility == "group":
                    # Check if user is in any of the shared groups
                    user_group_ids = set(current_user.group_ids)
                    dashboard_group_ids = {g.id for g in dashboard.shared_groups}
                    
                    if not user_group_ids.intersection(dashboard_group_ids):
                        logger.warning(
                            f"User {current_user.username} (groups: {user_group_ids}) "
                            f"attempted to access group dashboard {dashboard_uid} (groups: {dashboard_group_ids})"
                        )
                        raise HTTPException(
                            status_code=403, 
                            detail="Access denied: Dashboard is only accessible to specific groups"
                        )
            
            logger.info(
                f"Dashboard access granted: {dashboard_uid} for user {current_user.username} "
                f"(visibility: {dashboard.visibility}, is_owner: {is_owner}, is_admin: {is_admin})"
            )
    
    # Enforce multi-tenant datasource access control
    if datasource_uid:
        from db_models import GrafanaDatasource
        datasource = db.query(GrafanaDatasource).filter(
            GrafanaDatasource.grafana_uid == datasource_uid
        ).first()
        
        if datasource:
            # Check tenant isolation
            if datasource.tenant_id != current_user.tenant_id:
                logger.warning(
                    f"Tenant mismatch: User {current_user.username} (tenant {current_user.tenant_id}) "
                    f"attempted to access datasource {datasource_uid} (tenant {datasource.tenant_id})"
                )
                raise HTTPException(status_code=404, detail="Datasource not found")
            
            # Check if datasource is hidden for this user
            if datasource.hidden_by and current_user.user_id in datasource.hidden_by:
                logger.warning(f"User {current_user.username} attempted to access hidden datasource {datasource_uid}")
                raise HTTPException(status_code=404, detail="Datasource not found")
            
            # Check visibility and group access
            is_admin = current_user.role == Role.ADMIN or current_user.is_superuser
            is_owner = datasource.created_by == current_user.user_id
            
            if not is_admin and not is_owner:
                if datasource.visibility == "private":
                    logger.warning(
                        f"User {current_user.username} attempted to access private datasource {datasource_uid} "
                        f"(owner: {datasource.created_by})"
                    )
                    raise HTTPException(status_code=403, detail="Access denied: Datasource is private")
                
                elif datasource.visibility == "group":
                    # Check if user is in any of the shared groups
                    user_group_ids = set(current_user.group_ids)
                    datasource_group_ids = {g.id for g in datasource.shared_groups}
                    
                    if not user_group_ids.intersection(datasource_group_ids):
                        logger.warning(
                            f"User {current_user.username} (groups: {user_group_ids}) "
                            f"attempted to access group datasource {datasource_uid} (groups: {datasource_group_ids})"
                        )
                        raise HTTPException(
                            status_code=403, 
                            detail="Access denied: Datasource is only accessible to specific groups"
                        )
            
            logger.info(
                f"Datasource access granted: {datasource_uid} for user {current_user.username} "
                f"(visibility: {datasource.visibility}, is_owner: {is_owner}, is_admin: {is_admin})"
            )

    # Build target Grafana URL
    grafana_base = config.GRAFANA_URL.rstrip("/")
    target_url = f"{grafana_base}/{path}" if path else grafana_base
    
    # Remove token from query params before forwarding to Grafana
    if request.url.query:
        query_params = str(request.url.query)
        if token and "token=" in query_params:
            # Remove token parameter
            import re
            query_params = re.sub(r'[&]?token=[^&]*', '', query_params)
            query_params = query_params.lstrip('&')
        if query_params:
            target_url = f"{target_url}?{query_params}"

    # Get user details for Grafana auth proxy headers
    user = auth_service.get_user_by_id(current_user.user_id)

    # Headers to exclude (hop-by-hop headers)
    hop_by_hop = {
        "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
        "te", "trailers", "transfer-encoding", "upgrade", "host",
        "content-length", "authorization",
    }
    
    # Forward headers (excluding hop-by-hop)
    headers = {k: v for k, v in request.headers.items() if k.lower() not in hop_by_hop}
    
    # Add Grafana auth proxy headers for SSO
    headers["X-WEBAUTH-USER"] = current_user.username
    headers["X-WEBAUTH-TENANT"] = current_user.tenant_id
    headers["X-WEBAUTH-ROLE"] = current_user.role.value
    if user and getattr(user, "email", None):
        headers["X-WEBAUTH-EMAIL"] = user.email
    if user and getattr(user, "full_name", None):
        headers["X-WEBAUTH-NAME"] = user.full_name

    # Proxy the request to Grafana
    body = await request.body()
    timeout = httpx.Timeout(config.DEFAULT_TIMEOUT)
    
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            resp = await client.request(
                request.method,
                target_url,
                headers=headers,
                content=body if body else None,
            )
            
            # Forward response headers (excluding hop-by-hop)
            resp_headers = {
                k: v for k, v in resp.headers.items() 
                if k.lower() not in hop_by_hop
            }
            
            # Read response content
            content = resp.content
            
            # Filter JSON responses for list endpoints (dashboards, datasources, search)
            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type and content:
                try:
                    import json
                    data = json.loads(content.decode('utf-8'))
                    
                    # Detect list endpoints that need filtering
                    needs_filtering = False
                    is_search = "/api/search" in path
                    is_dashboards_list = path.startswith("api/dashboards") and not "/uid/" in path
                    is_datasources_list = path.startswith("api/datasources") and not "/uid/" in path
                    
                    if (is_search or is_dashboards_list or is_datasources_list) and isinstance(data, list):
                        needs_filtering = True
                    
                    if needs_filtering:
                        # Get accessible UIDs for the user
                        accessible_dashboard_uids, _ = grafana_proxy_service._get_accessible_dashboard_uids(
                            db=db,
                            user_id=current_user.user_id,
                            tenant_id=current_user.tenant_id,
                            group_ids=_user_group_ids(current_user)
                        )
                        accessible_datasource_uids, _ = grafana_proxy_service._get_accessible_datasource_uids(
                            db=db,
                            user_id=current_user.user_id,
                            tenant_id=current_user.tenant_id,
                            group_ids=_user_group_ids(current_user)
                        )
                        
                        # Get all registered UIDs to allow system dashboards
                        from db_models import GrafanaDashboard, GrafanaDatasource
                        all_registered_dashboard_uids = {d.grafana_uid for d in db.query(GrafanaDashboard).all()}
                        all_registered_datasource_uids = {ds.grafana_uid for ds in db.query(GrafanaDatasource).all()}
                        
                        # Filter the response list
                        filtered_data = []
                        for item in data:
                            item_uid = item.get("uid")
                            if not item_uid:
                                continue
                            
                            # For search endpoint, check type
                            if is_search:
                                item_type = item.get("type", "")
                                if "dash" in item_type:
                                    # Dashboard item
                                    if item_uid in accessible_dashboard_uids or item_uid not in all_registered_dashboard_uids:
                                        filtered_data.append(item)
                                else:
                                    # Include other types (folders, etc.)
                                    filtered_data.append(item)
                            elif is_dashboards_list:
                                # Dashboard list
                                if item_uid in accessible_dashboard_uids or item_uid not in all_registered_dashboard_uids:
                                    filtered_data.append(item)
                            elif is_datasources_list:
                                # Datasource list
                                if item_uid in accessible_datasource_uids or item_uid not in all_registered_datasource_uids:
                                    filtered_data.append(item)
                        
                        # Replace content with filtered data
                        content = json.dumps(filtered_data).encode('utf-8')
                        resp_headers["content-length"] = str(len(content))
                        
                        logger.info(
                            f"Filtered {len(data)} -> {len(filtered_data)} items for user {current_user.username} "
                            f"(endpoint: {path})"
                        )
                except Exception as e:
                    logger.warning(f"Failed to filter JSON response: {e}", exc_info=True)
                    # Continue with original content if filtering fails
            
            # Rewrite HTML content to fix asset paths
            elif "text/html" in content_type and content:
                try:
                    html_content = content.decode('utf-8')
                    
                    # Inject base tag to make all relative URLs go through proxy
                    base_url = f"{request.url.scheme}://{request.url.netloc}/api/grafana/proxy/"
                    if "<head>" in html_content:
                        base_tag = f'<base href="{base_url}">'
                        html_content = html_content.replace("<head>", f"<head>{base_tag}", 1)
                        content = html_content.encode('utf-8')
                        resp_headers["content-length"] = str(len(content))
                except Exception as e:
                    logger.warning(f"Failed to rewrite HTML: {e}")
                    # Continue with original content if rewrite fails
            
            return Response(
                content=content,
                status_code=resp.status_code,
                headers=resp_headers,
                media_type=resp.headers.get("content-type"),
            )
    except httpx.HTTPError as e:
        logger.error(f"Proxy request failed: {e}")
        raise HTTPException(status_code=502, detail="Failed to proxy request to Grafana")

@router.get("/folders", response_model=List[Folder])
async def get_folders(current_user: TokenData = Depends(require_permission(Permission.READ_DASHBOARDS))):
    _rate_limit(current_user)
    return await grafana_service.get_folders()


@router.post("/folders", response_model=Folder)
async def create_folder(
    title: str = Body(..., embed=True),
    current_user: TokenData = Depends(require_permission(Permission.WRITE_DASHBOARDS)),
):
    _rate_limit(current_user)
    result = await grafana_service.create_folder(title)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create folder")
    return result


@router.delete("/folders/{uid}")
async def delete_folder(
    uid: str,
    current_user: TokenData = Depends(require_permission(Permission.DELETE_DASHBOARDS)),
):
    _rate_limit(current_user)
    success = await grafana_service.delete_folder(uid)
    if not success:
        raise HTTPException(status_code=404, detail=f"Folder {uid} not found or delete failed")
    return {"status": "success", "message": f"Folder {uid} deleted"}


# ==================================================================
# Helpers
# ==================================================================

def _parse_labels(labels_str: Optional[str]) -> Optional[Dict[str, str]]:
    """Parse JSON labels string from query parameter."""
    if not labels_str:
        return None
    import json

    try:
        parsed = json.loads(labels_str)
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items()}
    except (json.JSONDecodeError, ValueError):
        pass
    return None
