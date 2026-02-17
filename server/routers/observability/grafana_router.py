"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

Grafana API router with multi-tenancy, hide/show, team filtering, and UID search.
"""
from fastapi import APIRouter, HTTPException, Query, Body, Depends, Request, status
from fastapi.responses import Response, JSONResponse
from typing import Optional, List, Dict
import logging

from models.grafana.grafana_dashboard_models import DashboardCreate, DashboardUpdate, DashboardSearchResult
from models.grafana.grafana_datasource_models import Datasource, DatasourceCreate, DatasourceUpdate
from models.grafana.grafana_folder_models import Folder
from services.grafana.route_payloads import (
    parse_dashboard_create_payload,
    parse_dashboard_update_payload,
    validate_visibility,
    is_admin_user,
    user_group_ids,
)
from services.grafana_proxy_service import GrafanaProxyService
from services.grafana_service import GrafanaService
from models.access.auth_models import Permission, TokenData
from config import config
from database import get_db
from sqlalchemy.orm import Session

from middleware.dependencies import (
    require_permission_with_scope,
    require_any_permission_with_scope,
    enforce_public_endpoint_security,
    require_authenticated_with_scope,
)
from middleware.error_handlers import handle_route_errors
from services.database_auth_service import DatabaseAuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/grafana", tags=["grafana"])

grafana_proxy_service = GrafanaProxyService()
grafana_service = GrafanaService()
auth_service = DatabaseAuthService()


def _cookie_secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https"


def _normalize_grafana_next_path(path: Optional[str]) -> str:
    candidate = (path or "/dashboards").strip() or "/dashboards"
    if candidate.startswith("http://") or candidate.startswith("https://"):
        candidate = "/dashboards"
    if not candidate.startswith("/"):
        candidate = f"/{candidate}"
    if candidate.startswith("/grafana"):
        candidate = candidate[len("/grafana"):] or "/dashboards"
    return candidate


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
    enforce_public_endpoint_security(
        request,
        scope="grafana_proxy_auth",
        limit=config.RATE_LIMIT_GRAFANA_PROXY_PER_MINUTE,
        window_seconds=60,
        allowlist=config.GRAFANA_PROXY_IP_ALLOWLIST,
        fallback_mode="deny",
    )

    headers = await grafana_proxy_service.authorize_proxy_request(
        request=request,
        db=db,
        auth_service=auth_service,
        token=token,
        orig=orig,
    )

    return Response(status_code=204, headers=headers)


@router.post(
    "/bootstrap-session",
    summary="Create secure Grafana bootstrap session",
    description="Sets a short-lived HttpOnly auth cookie for Grafana proxy usage and returns a safe launch URL.",
)
async def bootstrap_grafana_session(
    request: Request,
    payload: Dict = Body(default={}),
    _current_user: TokenData = Depends(require_authenticated_with_scope("grafana")),
):
    next_path = _normalize_grafana_next_path(payload.get("next") if isinstance(payload, dict) else None)
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if not token:
        token = request.cookies.get("beobservant_token")

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication token unavailable")

    response = JSONResponse({"launch_url": f"/grafana{next_path}"})
    response.set_cookie(
        key="beobservant_token",
        value=token,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="lax",
        max_age=config.JWT_EXPIRATION_MINUTES * 60,
        path="/",
    )
    return response


@router.post("/ds/query")
@handle_route_errors()
async def datasource_query(
    payload: Dict = Body(..., description="Grafana datasource query payload"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.QUERY_DATASOURCES, "grafana")),
    db: Session = Depends(get_db),
):
    """Proxy Grafana datasource queries after datasource access validation."""
    is_admin = is_admin_user(current_user)
    await grafana_proxy_service.enforce_datasource_query_access(
        db=db,
        payload=payload,
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=user_group_ids(current_user),
        is_admin=is_admin,
    )
    return await grafana_service.query_datasource(payload)

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
    limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DASHBOARDS, "grafana")),
    db: Session = Depends(get_db),
) -> List[DashboardSearchResult]:
    is_admin = is_admin_user(current_user)
    return await grafana_proxy_service.search_dashboards(
        db=db,
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=user_group_ids(current_user),
        query=query,
        tag=tag,
        starred=starred,
        uid=uid,
        team_id=team_id,
        show_hidden=show_hidden,
        is_admin=is_admin,
        limit=limit,
        offset=offset,
    )


@router.get("/dashboards/{uid}")
async def get_dashboard(
    uid: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DASHBOARDS, "grafana")),
    db: Session = Depends(get_db),
):
    """Get a dashboard by UID with access control."""
    dashboard = await grafana_proxy_service.get_dashboard(
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=user_group_ids(current_user),
    )
    if not dashboard:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found or access denied")
    return dashboard


@router.post("/dashboards")
@handle_route_errors()
async def create_dashboard(
    payload: Dict = Body(..., description="Dashboard JSON — either a DashboardCreate wrapper or a raw dashboard object"),
    visibility: str = Query("private"),
    shared_group_ids: Optional[List[str]] = Query(None),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.CREATE_DASHBOARDS, Permission.WRITE_DASHBOARDS], "grafana")
    ),
    db: Session = Depends(get_db),
):
    """Create a new dashboard with visibility and groups.

    Accepts either the existing DashboardCreate wrapper (contains `dashboard`) or
    a raw Grafana dashboard object (we will wrap it into DashboardCreate).
    """
    validate_visibility(visibility)
    dashboard_create = parse_dashboard_create_payload(payload)

    is_admin = is_admin_user(current_user)

    result = await grafana_proxy_service.create_dashboard(
        db=db, dashboard_create=dashboard_create, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=user_group_ids(current_user),
        visibility=visibility, shared_group_ids=shared_group_ids or [],
        is_admin=is_admin,
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create dashboard")
    return result


@router.put("/dashboards/{uid}")
@handle_route_errors()
async def update_dashboard(
    uid: str,
    payload: Dict = Body(..., description="Either a DashboardUpdate wrapper or a raw dashboard object"),
    visibility: Optional[str] = Query(None),
    shared_group_ids: Optional[List[str]] = Query(None),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_DASHBOARDS, Permission.WRITE_DASHBOARDS], "grafana")
    ),
    db: Session = Depends(get_db),
):
    """Update an existing dashboard with access control.

    Accepts either DashboardUpdate (with `dashboard`) or a raw dashboard object
    which will be wrapped into DashboardUpdate.dashboard.
    """
    validate_visibility(visibility)
    dashboard_update = parse_dashboard_update_payload(payload)

    is_admin = is_admin_user(current_user)
    result = await grafana_proxy_service.update_dashboard(
        db=db, uid=uid, dashboard_update=dashboard_update, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=user_group_ids(current_user),
        visibility=visibility, shared_group_ids=shared_group_ids, is_admin=is_admin,
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found, access denied, or update failed")
    return result


@router.delete("/dashboards/{uid}")
async def delete_dashboard(
    uid: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.DELETE_DASHBOARDS, "grafana")),
    db: Session = Depends(get_db),
):
    """Delete a dashboard with access control."""
    success = await grafana_proxy_service.delete_dashboard(
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=user_group_ids(current_user),
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"You have no permission to delete dashboard {uid} or it does not exist")
    return {"status": "success", "message": f"Dashboard {uid} deleted"}


@router.post("/dashboards/{uid}/hide")
async def hide_dashboard(
    uid: str,
    hidden: bool = Body(True, embed=True),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DASHBOARDS, "grafana")),
    db: Session = Depends(get_db),
):
    """Hide or unhide a dashboard for the current user."""
    success = grafana_proxy_service.toggle_dashboard_hidden(
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, hidden=hidden,
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found")
    return {"status": "success", "hidden": hidden}


@router.get("/datasources", response_model=List[Datasource])
async def get_datasources(
    uid: Optional[str] = Query(None, description="Search by exact datasource UID"),
    team_id: Optional[str] = Query(None),
    show_hidden: bool = Query(False),
    limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: TokenData = Depends(
        require_permission_with_scope(Permission.READ_DATASOURCES, "grafana")
    ),
    db: Session = Depends(get_db),
):
    """Get all datasources with multi-tenant access control and filtering."""
    is_admin = is_admin_user(current_user)
    return await grafana_proxy_service.get_datasources(
        db=db, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=user_group_ids(current_user),
        uid=uid, team_id=team_id, show_hidden=show_hidden, is_admin=is_admin,
        limit=limit, offset=offset,
    )

@router.get("/datasources/{uid}", response_model=Datasource)
async def get_datasource_by_uid(
    uid: str,
    current_user: TokenData = Depends(
        require_permission_with_scope(Permission.READ_DATASOURCES, "grafana")
    ),
    db: Session = Depends(get_db),
):
    """Get a datasource by UID with access control."""
    datasource = await grafana_proxy_service.get_datasource(
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=user_group_ids(current_user),
    )
    if not datasource:
        raise HTTPException(status_code=404, detail=f"Datasource {uid} not found or access denied")
    return datasource


@router.get("/datasources/name/{name}", response_model=Datasource)
async def get_datasource_by_name(
    name: str,
    current_user: TokenData = Depends(
        require_permission_with_scope(Permission.READ_DATASOURCES, "grafana")
    ),
    db: Session = Depends(get_db),
):
    """Get a datasource by name with access control."""
    datasource = await grafana_service.get_datasource_by_name(name)
    if not datasource:
        raise HTTPException(status_code=404, detail=f"Datasource {name} not found")
    accessible = await grafana_proxy_service.get_datasource(
        db=db, uid=datasource.uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=user_group_ids(current_user),
    )
    if not accessible:
        raise HTTPException(status_code=404, detail=f"Datasource {name} not found or access denied")
    return datasource


@router.post("/datasources", response_model=Datasource)
@handle_route_errors()
async def create_datasource(
    datasource: DatasourceCreate = Body(...),
    visibility: str = Query("private"),
    shared_group_ids: Optional[List[str]] = Query(None),
    current_user: TokenData = Depends(
        require_permission_with_scope(Permission.CREATE_DATASOURCES, "grafana")
    ),
    db: Session = Depends(get_db),
):
    """Create a new datasource with visibility control."""
    validate_visibility(visibility)
    
    is_admin = is_admin_user(current_user)
    
    result = await grafana_proxy_service.create_datasource(
        db=db, datasource_create=datasource, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=user_group_ids(current_user),
        visibility=visibility, shared_group_ids=shared_group_ids or [],
        is_admin=is_admin,
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create datasource")
    return result


@router.put("/datasources/{uid}", response_model=Datasource)
@handle_route_errors()
async def update_datasource(
    uid: str,
    datasource: DatasourceUpdate = Body(...),
    visibility: Optional[str] = Query(None),
    shared_group_ids: Optional[List[str]] = Query(None),
    current_user: TokenData = Depends(
        require_permission_with_scope(Permission.UPDATE_DATASOURCES, "grafana")
    ),
    db: Session = Depends(get_db),
):
    """Update an existing datasource with access control."""
    validate_visibility(visibility)
    is_admin = is_admin_user(current_user)
    result = await grafana_proxy_service.update_datasource(
        db=db, uid=uid, datasource_update=datasource, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=user_group_ids(current_user),
        visibility=visibility, shared_group_ids=shared_group_ids, is_admin=is_admin,
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Datasource {uid} not found, access denied, or update failed")
    return result


@router.delete("/datasources/{uid}")
async def delete_datasource(
    uid: str,
    current_user: TokenData = Depends(
        require_permission_with_scope(Permission.DELETE_DATASOURCES, "grafana")
    ),
    db: Session = Depends(get_db),
):
    """Delete a datasource with access control."""
    success = await grafana_proxy_service.delete_datasource(
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=user_group_ids(current_user),
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"You have no permission to delete datasource {uid} or it does not exist")
    return {"status": "success", "message": f"Datasource {uid} deleted"}


@router.post("/datasources/{uid}/hide")
async def hide_datasource(
    uid: str,
    hidden: bool = Body(True, embed=True),
    current_user: TokenData = Depends(
        require_permission_with_scope(Permission.READ_DATASOURCES, "grafana")
    ),
    db: Session = Depends(get_db),
):
    """Hide or unhide a datasource for the current user."""
    success = grafana_proxy_service.toggle_datasource_hidden(
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, hidden=hidden,
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Datasource {uid} not found")
    return {"status": "success", "hidden": hidden}


@router.get("/dashboards/meta/filters")
async def get_dashboard_filter_metadata(
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DASHBOARDS, "grafana")),
    db: Session = Depends(get_db),
):
    """Get label keys/values and team IDs used across dashboards for building filter UI."""
    return grafana_proxy_service.get_dashboard_metadata(db=db, tenant_id=current_user.tenant_id)


@router.get("/datasources/meta/filters")
async def get_datasource_filter_metadata(
    current_user: TokenData = Depends(
        require_permission_with_scope(Permission.READ_DATASOURCES, "grafana")
    ),
    db: Session = Depends(get_db),
):
    """Get label keys/values and team IDs used across datasources for building filter UI."""
    return grafana_proxy_service.get_datasource_metadata(db=db, tenant_id=current_user.tenant_id)


@router.get("/folders", response_model=List[Folder])
async def get_folders(
    current_user: TokenData = Depends(
        require_permission_with_scope(Permission.READ_FOLDERS, "grafana")
    )
):
    return await grafana_service.get_folders()


@router.post("/folders", response_model=Folder)
async def create_folder(
    title: str = Body(..., embed=True),
    current_user: TokenData = Depends(
        require_permission_with_scope(Permission.CREATE_FOLDERS, "grafana")
    ),
):
    result = await grafana_service.create_folder(title)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create folder")
    return result


@router.delete("/folders/{uid}")
async def delete_folder(
    uid: str,
    current_user: TokenData = Depends(
        require_permission_with_scope(Permission.DELETE_FOLDERS, "grafana")
    ),
):
    success = await grafana_service.delete_folder(uid)
    if not success:
        raise HTTPException(status_code=404, detail=f"Folder {uid} not found or delete failed")
    return {"status": "success", "message": f"Folder {uid} deleted"}
