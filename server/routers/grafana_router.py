"""Grafana API router with multi-tenancy, hide/show, team filtering, and UID search."""
from fastapi import APIRouter, HTTPException, Query, Body, Depends, Request
from fastapi.responses import Response
from typing import Optional, List, Dict
import logging
import re

from models.grafana_models import (
    DashboardCreate, DashboardUpdate, DashboardSearchResult,
    Datasource, DatasourceCreate, DatasourceUpdate, Folder
)
from services.grafana_proxy_service import GrafanaProxyService
from services.grafana_service import GrafanaService
from models.auth_models import Permission, TokenData, Role
from database import get_db
from sqlalchemy.orm import Session, joinedload
from db_models import GrafanaDashboard, GrafanaDatasource

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


def _is_admin_user(token_data: TokenData) -> bool:
    return token_data.role == Role.ADMIN or token_data.is_superuser


def _is_resource_accessible(resource, token_data: TokenData) -> bool:
    if not resource:
        return False

    if resource.tenant_id != token_data.tenant_id:
        return False

    hidden_by = getattr(resource, "hidden_by", None) or []
    if token_data.user_id in hidden_by:
        return False

    if _is_admin_user(token_data):
        return True

    if resource.created_by == token_data.user_id:
        return True

    visibility = getattr(resource, "visibility", "private") or "private"
    if visibility == "tenant":
        return True

    if visibility == "group":
        user_group_ids = set(token_data.group_ids or [])
        resource_group_ids = {g.id for g in (resource.shared_groups or [])}
        return bool(user_group_ids.intersection(resource_group_ids))

    return False


def _extract_dashboard_uid(path: str) -> Optional[str]:
    patterns = [
        r"^/grafana/d/([^/]+)",
        r"^/grafana/d-solo/([^/]+)",
        r"^/grafana/api/dashboards/uid/([^/?]+)",
    ]
    for pattern in patterns:
        match = re.match(pattern, path)
        if match:
            return match.group(1)
    return None


def _extract_datasource_uid(path: str) -> Optional[str]:
    patterns = [
        r"^/grafana/api/datasources/uid/([^/?]+)",
        r"^/grafana/connections/datasources/edit/([^/?]+)",
    ]
    for pattern in patterns:
        match = re.match(pattern, path)
        if match:
            return match.group(1)
    return None


# ==================================================================
# Dashboard endpoints
# ==================================================================


@router.get(
    "/auth",
    summary="Auth hook for Grafana reverse proxy",
    description=(
        "Used by the NGINX grafana-proxy via auth_request. "
        "Validates a JWT (Authorization: Bearer ..., auth cookie, or legacy token params) "
        "and returns X-WEBAUTH-* headers for Grafana auth.proxy."
    ),
)
async def grafana_auth(
    request: Request,
    token: Optional[str] = Query(None, description="Optional legacy JWT token"),
    orig: Optional[str] = Query(None, description="Original proxied URI"),
    db: Session = Depends(get_db),
):
    token_to_verify: Optional[str] = None

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token_to_verify = auth_header.split(" ", 1)[1]

    if not token_to_verify:
        token_to_verify = request.cookies.get("beobservant_token")

    if not token_to_verify:
        token_to_verify = request.cookies.get("access_token")

    if not token_to_verify:
        token_to_verify = request.headers.get("X-Auth-Token") or token

    if not token_to_verify:
        raise HTTPException(status_code=401, detail="Authentication required")

    token_data = auth_service.decode_token(token_to_verify)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    # NGINX will call this endpoint for every /grafana/ request.
    # Keep it lightweight: trust token claims (expiry/signature enforced in decode_token).
    if Permission.READ_DASHBOARDS.value not in (token_data.permissions or []) and not token_data.is_superuser:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    is_admin = _is_admin_user(token_data)

    original_uri = orig or request.headers.get("X-Original-URI", "")
    original_path = original_uri.split("?", 1)[0] if original_uri else ""

    # For proxy UI access, be more permissive than management API:
    # - Admin users can access everything
    # - Non-admin users can access resources they own, shared with them, or tenant-wide
    # - For resources not in our DB, allow access (let Grafana enforce its own permissions)
    # - This supports dashboards created outside BeObservant or Grafana's built-in resources
    
    if not is_admin:
        # Only enforce scope checks for resources that exist in our database
        dashboard_uid = _extract_dashboard_uid(original_path)
        if dashboard_uid:
            dashboard = db.query(GrafanaDashboard).options(joinedload(GrafanaDashboard.shared_groups)).filter(GrafanaDashboard.grafana_uid == dashboard_uid).first()
            # If dashboard exists in our DB, enforce scope; otherwise allow access
            if dashboard and not _is_resource_accessible(dashboard, token_data):
                raise HTTPException(status_code=403, detail="Dashboard access denied")

        datasource_uid = _extract_datasource_uid(original_path)
        if datasource_uid:
            datasource = db.query(GrafanaDatasource).options(joinedload(GrafanaDatasource.shared_groups)).filter(GrafanaDatasource.grafana_uid == datasource_uid).first()
            # If datasource exists in our DB, enforce scope; otherwise allow access
            if datasource and not _is_resource_accessible(datasource, token_data):
                raise HTTPException(status_code=403, detail="Datasource access denied")

        # Allow Grafana UI listing endpoints; scoped filtering is enforced
        # by routing /grafana/api/search through BeObservant in the proxy.

    grafana_role = "Viewer"
    if is_admin:
        grafana_role = "Admin"
    elif Permission.WRITE_DASHBOARDS.value in (token_data.permissions or []):
        grafana_role = "Editor"

    headers = {
        "X-WEBAUTH-USER": token_data.username,
        "X-WEBAUTH-TENANT": token_data.tenant_id,
        "X-WEBAUTH-ROLE": grafana_role,
    }

    # Optional: try to enrich with email/full name if it is cheap to fetch.
    # NOTE: Avoid hitting the DB here; this endpoint may be called frequently.
    return Response(status_code=204, headers=headers)

@router.get(
    "/dashboards/search",
    response_model=List[DashboardSearchResult],
    summary="Search dashboards",
    description="Search Grafana dashboards with multi-tenant access control, UID search, and team filtering",
)
async def search_dashboards(
    query: Optional[str] = Query(None, description="Search query"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    starred: Optional[bool] = Query(None, description="Filter starred dashboards"),
    uid: Optional[str] = Query(None, description="Search by exact dashboard UID"),
    team_id: Optional[str] = Query(None, description="Filter by team/group ID"),
    show_hidden: bool = Query(False, description="Include hidden dashboards"),
    current_user: TokenData = Depends(require_permission(Permission.READ_DASHBOARDS)),
    db: Session = Depends(get_db),
) -> List[DashboardSearchResult]:
    _rate_limit(current_user)
    is_admin = _is_admin_user(current_user)
    return await grafana_proxy_service.search_dashboards(
        db=db,
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=_user_group_ids(current_user),
        query=query,
        tag=tag,
        starred=starred,
        uid=uid,
        team_id=team_id,
        show_hidden=show_hidden,
        is_admin=is_admin,
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
    current_user: TokenData = Depends(require_permission(Permission.WRITE_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Create a new dashboard with visibility and groups."""
    _rate_limit(current_user)
    if visibility not in ("private", "group", "tenant"):
        raise HTTPException(status_code=400, detail="Invalid visibility value")

    # Check if user is admin
    from models.auth_models import Role
    is_admin = current_user.role == Role.ADMIN or current_user.is_superuser

    result = await grafana_proxy_service.create_dashboard(
        db=db, dashboard_create=dashboard, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=_user_group_ids(current_user),
        visibility=visibility, shared_group_ids=shared_group_ids or [],
        is_admin=is_admin,
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
    current_user: TokenData = Depends(require_permission(Permission.WRITE_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Update an existing dashboard with access control."""
    _rate_limit(current_user)
    if visibility and visibility not in ("private", "group", "tenant"):
        raise HTTPException(status_code=400, detail="Invalid visibility value")

    result = await grafana_proxy_service.update_dashboard(
        db=db, uid=uid, dashboard_update=dashboard, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=_user_group_ids(current_user),
        visibility=visibility, shared_group_ids=shared_group_ids,
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


# ==================================================================
# Datasource endpoints
# ==================================================================

@router.get("/datasources", response_model=List[Datasource])
async def get_datasources(
    uid: Optional[str] = Query(None, description="Search by exact datasource UID"),
    team_id: Optional[str] = Query(None),
    show_hidden: bool = Query(False),
    current_user: TokenData = Depends(require_permission(Permission.READ_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Get all datasources with multi-tenant access control and filtering."""
    _rate_limit(current_user)
    is_admin = _is_admin_user(current_user)
    return await grafana_proxy_service.get_datasources(
        db=db, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=_user_group_ids(current_user),
        uid=uid, team_id=team_id, show_hidden=show_hidden, is_admin=is_admin,
    )

@router.get("/datasources/{uid}", response_model=Datasource)
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
    current_user: TokenData = Depends(require_permission(Permission.WRITE_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Create a new datasource with visibility control."""
    _rate_limit(current_user)
    if visibility not in ("private", "group", "tenant"):
        raise HTTPException(status_code=400, detail="Invalid visibility value")
    
    # Check if user is admin
    from models.auth_models import Role
    is_admin = current_user.role == Role.ADMIN or current_user.is_superuser
    
    result = await grafana_proxy_service.create_datasource(
        db=db, datasource_create=datasource, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=_user_group_ids(current_user),
        visibility=visibility, shared_group_ids=shared_group_ids or [],
        is_admin=is_admin,
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
    current_user: TokenData = Depends(require_permission(Permission.WRITE_DASHBOARDS)),
    db: Session = Depends(get_db),
):
    """Update an existing datasource with access control."""
    _rate_limit(current_user)
    if visibility and visibility not in ("private", "group", "tenant"):
        raise HTTPException(status_code=400, detail="Invalid visibility value")
    result = await grafana_proxy_service.update_datasource(
        db=db, uid=uid, datasource_update=datasource, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=_user_group_ids(current_user),
        visibility=visibility, shared_group_ids=shared_group_ids,
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
