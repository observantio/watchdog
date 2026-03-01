"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from config import config
from database import get_db
from middleware.dependencies import (
    enforce_public_endpoint_security,
    require_any_permission_with_scope,
    require_authenticated_with_scope,
    require_permission_with_scope,
)
from middleware.error_handlers import handle_route_errors
from models.access.auth_models import Permission, TokenData
from models.grafana.grafana_dashboard_models import DashboardSearchResult
from models.grafana.grafana_datasource_models import Datasource, DatasourceCreate, DatasourceUpdate
from models.grafana.grafana_folder_models import Folder
from models.observability.grafana_request_models import (
    GrafanaBootstrapSessionRequest,
    GrafanaCreateFolderRequest,
    GrafanaDashboardPayloadRequest,
    GrafanaDatasourceQueryRequest,
    GrafanaHiddenToggleRequest,
)
from services.common.cookies import cookie_secure
from services.database_auth_service import DatabaseAuthService
from services.grafana_proxy_service import GrafanaProxyService
from services.grafana.route_payloads import (
    is_admin_user,
    parse_dashboard_create_payload,
    parse_dashboard_update_payload,
    user_group_ids,
    validate_visibility,
)
from services.grafana.normalize import normalize_grafana_next_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/grafana", tags=["grafana"])
rtp = run_in_threadpool
proxy = GrafanaProxyService()
auth_service = DatabaseAuthService()


@router.get("/auth")
async def grafana_auth(
    request: Request,
    token: Optional[str] = Query(None),
    orig: Optional[str] = Query(None),
):
    enforce_public_endpoint_security(
        request,
        scope="grafana_proxy_auth",
        limit=config.RATE_LIMIT_GRAFANA_PROXY_PER_MINUTE,
        window_seconds=60,
        allowlist=config.GRAFANA_PROXY_IP_ALLOWLIST,
        fallback_mode="deny",
    )
    headers = await proxy.authorize_proxy_request(
        request=request, auth_service=auth_service, token=token, orig=orig,
    )
    return Response(status_code=204, headers=headers)


@router.post("/bootstrap-session")
async def bootstrap_grafana_session(
    request: Request,
    payload: GrafanaBootstrapSessionRequest = Body(default_factory=GrafanaBootstrapSessionRequest),
    _current_user: TokenData = Depends(require_authenticated_with_scope("grafana")),
):
    enforce_public_endpoint_security(
        request,
        scope="grafana_bootstrap_session",
        limit=config.RATE_LIMIT_GRAFANA_PROXY_PER_MINUTE,
        window_seconds=60,
        allowlist=None,
        fallback_mode="allow",
    )
    next_path = normalize_grafana_next_path(payload.next)
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.split(" ", 1)[1].strip() if auth_header.startswith("Bearer ") else None
    if not token:
        token = request.cookies.get("beobservant_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication token unavailable")
    response = JSONResponse({"launch_url": f"/grafana{next_path}"})
    response.set_cookie(
        key="beobservant_token",
        value=token,
        httponly=True,
        secure=bool(config.FORCE_SECURE_COOKIES) or cookie_secure(request),
        samesite="lax",
        max_age=config.JWT_EXPIRATION_MINUTES * 60,
        path="/",
    )
    return response


@router.post("/ds/query")
@handle_route_errors()
async def datasource_query(
    payload: GrafanaDatasourceQueryRequest,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.QUERY_DATASOURCES, "grafana")),
    db: Session = Depends(get_db),
):
    await proxy.enforce_datasource_query_access(
        db=db,
        payload=payload.model_dump(exclude_none=True),
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=user_group_ids(current_user),
    )
    return await proxy.query_datasource(payload.model_dump(exclude_none=True))


@router.get("/dashboards/meta/filters")
async def get_dashboard_filter_metadata(
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DASHBOARDS, "grafana")),
    db: Session = Depends(get_db),
):
    return await rtp(proxy.get_dashboard_metadata, db=db, tenant_id=current_user.tenant_id)


@router.get("/dashboards/search")
async def search_dashboards(
    query: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    starred: Optional[bool] = Query(None),
    uid: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    show_hidden: bool = Query(False),
    limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DASHBOARDS, "grafana")),
    db: Session = Depends(get_db),
) -> List[DashboardSearchResult]:
    search_context = await rtp(
        proxy.build_dashboard_search_context, db, tenant_id=current_user.tenant_id, uid=uid,
    )
    return await proxy.search_dashboards(
        db=db,
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=user_group_ids(current_user),
        query=query, tag=tag, starred=starred, uid=uid,
        team_id=team_id, show_hidden=show_hidden,
        limit=limit, offset=offset, search_context=search_context,
    )


@router.get("/dashboards/{uid}")
async def get_dashboard(
    uid: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DASHBOARDS, "grafana")),
    db: Session = Depends(get_db),
):
    dashboard = await proxy.get_dashboard(
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=user_group_ids(current_user),
    )
    if not dashboard:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found or access denied")
    return dashboard


@router.post("/dashboards")
@handle_route_errors()
async def create_dashboard(
    payload: GrafanaDashboardPayloadRequest,
    visibility: str = Query("private"),
    shared_group_ids: Optional[List[str]] = Query(None),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.CREATE_DASHBOARDS, Permission.WRITE_DASHBOARDS], "grafana")
    ),
    db: Session = Depends(get_db),
):
    validate_visibility(visibility)
    result = await proxy.create_dashboard(
        db=db,
        dashboard_create=parse_dashboard_create_payload(payload.model_dump(exclude_none=True)),
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=user_group_ids(current_user),
        visibility=visibility,
        shared_group_ids=shared_group_ids or [],
        is_admin=is_admin_user(current_user),
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create dashboard")
    return result


@router.put("/dashboards/{uid}")
@handle_route_errors()
async def update_dashboard(
    uid: str,
    payload: GrafanaDashboardPayloadRequest,
    visibility: Optional[str] = Query(None),
    shared_group_ids: Optional[List[str]] = Query(None),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_DASHBOARDS, Permission.WRITE_DASHBOARDS], "grafana")
    ),
    db: Session = Depends(get_db),
):
    validate_visibility(visibility)
    result = await proxy.update_dashboard(
        db=db, uid=uid,
        dashboard_update=parse_dashboard_update_payload(payload.model_dump(exclude_none=True)),
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        group_ids=user_group_ids(current_user),
        visibility=visibility,
        shared_group_ids=shared_group_ids,
        is_admin=is_admin_user(current_user),
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found, access denied, or update failed")
    return result


@router.delete("/dashboards/{uid}")
@handle_route_errors()
async def delete_dashboard(
    uid: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.DELETE_DASHBOARDS, "grafana")),
    db: Session = Depends(get_db),
):
    if not await proxy.delete_dashboard(
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=user_group_ids(current_user),
    ):
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found or access denied")
    return {"status": "success", "message": f"Dashboard {uid} deleted"}


@router.post("/dashboards/{uid}/hide")
@handle_route_errors()
async def hide_dashboard(
    uid: str,
    payload: GrafanaHiddenToggleRequest = Body(default_factory=GrafanaHiddenToggleRequest),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_DASHBOARDS, Permission.WRITE_DASHBOARDS], "grafana")
    ),
    db: Session = Depends(get_db),
):
    if not await rtp(
        proxy.toggle_dashboard_hidden,
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, hidden=payload.hidden,
    ):
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found")
    return {"status": "success", "hidden": payload.hidden}


@router.get("/datasources/meta/filters")
async def get_datasource_filter_metadata(
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DATASOURCES, "grafana")),
    db: Session = Depends(get_db),
):
    return await rtp(proxy.get_datasource_metadata, db=db, tenant_id=current_user.tenant_id)


@router.get("/datasources/name/{name}", response_model=Datasource)
async def get_datasource_by_name(
    name: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DATASOURCES, "grafana")),
    db: Session = Depends(get_db),
):
    datasource = await proxy.get_datasource_by_name(
        db=db, name=name, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=user_group_ids(current_user),
    )
    if not datasource:
        raise HTTPException(status_code=404, detail=f"Datasource {name} not found or access denied")
    return datasource


@router.get("/datasources", response_model=List[Datasource])
async def get_datasources(
    uid: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    show_hidden: bool = Query(False),
    limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DATASOURCES, "grafana")),
    db: Session = Depends(get_db),
):
    datasource_context = await rtp(
        proxy.build_datasource_list_context, db, tenant_id=current_user.tenant_id, uid=uid,
    )
    return await proxy.get_datasources(
        db=db, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=user_group_ids(current_user),
        uid=uid, team_id=team_id, show_hidden=show_hidden,
        limit=limit, offset=offset, datasource_context=datasource_context,
    )


@router.get("/datasources/{uid}", response_model=Datasource)
async def get_datasource_by_uid(
    uid: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DATASOURCES, "grafana")),
    db: Session = Depends(get_db),
):
    datasource = await proxy.get_datasource(
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=user_group_ids(current_user),
    )
    if not datasource:
        raise HTTPException(status_code=404, detail=f"Datasource {uid} not found or access denied")
    return datasource


@router.post("/datasources", response_model=Datasource)
@handle_route_errors()
async def create_datasource(
    datasource: DatasourceCreate = Body(...),
    visibility: str = Query("private"),
    shared_group_ids: Optional[List[str]] = Query(None),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.CREATE_DATASOURCES, "grafana")),
    db: Session = Depends(get_db),
):
    validate_visibility(visibility)
    result = await proxy.create_datasource(
        db=db, datasource_create=datasource, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=user_group_ids(current_user),
        visibility=visibility, shared_group_ids=shared_group_ids or [],
        is_admin=is_admin_user(current_user),
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
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_DATASOURCES, "grafana")),
    db: Session = Depends(get_db),
):
    validate_visibility(visibility)
    result = await proxy.update_datasource(
        db=db, uid=uid, datasource_update=datasource, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=user_group_ids(current_user),
        visibility=visibility, shared_group_ids=shared_group_ids,
        is_admin=is_admin_user(current_user),
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Datasource {uid} not found, access denied, or update failed")
    return result


@router.delete("/datasources/{uid}")
@handle_route_errors()
async def delete_datasource(
    uid: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.DELETE_DATASOURCES, "grafana")),
    db: Session = Depends(get_db),
):
    if not await proxy.delete_datasource(
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, group_ids=user_group_ids(current_user),
    ):
        raise HTTPException(status_code=404, detail=f"Datasource {uid} not found or access denied")
    return {"status": "success", "message": f"Datasource {uid} deleted"}


@router.post("/datasources/{uid}/hide")
@handle_route_errors()
async def hide_datasource(
    uid: str,
    payload: GrafanaHiddenToggleRequest = Body(default_factory=GrafanaHiddenToggleRequest),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_DATASOURCES, Permission.CREATE_DATASOURCES], "grafana")
    ),
    db: Session = Depends(get_db),
):
    if not await rtp(
        proxy.toggle_datasource_hidden,
        db=db, uid=uid, user_id=current_user.user_id,
        tenant_id=current_user.tenant_id, hidden=payload.hidden,
    ):
        raise HTTPException(status_code=404, detail=f"Datasource {uid} not found")
    return {"status": "success", "hidden": payload.hidden}


@router.get("/folders", response_model=List[Folder])
async def get_folders(
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_FOLDERS, "grafana")),
):
    return await rtp(proxy.get_folders)


@router.post("/folders", response_model=Folder)
@handle_route_errors()
async def create_folder(
    payload: GrafanaCreateFolderRequest,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.CREATE_FOLDERS, "grafana")),
):
    result = await rtp(proxy.create_folder, payload.title)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create folder")
    return result


@router.delete("/folders/{uid}")
@handle_route_errors()
async def delete_folder(
    uid: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.DELETE_FOLDERS, "grafana")),
):
    if not await rtp(proxy.delete_folder, uid):
        raise HTTPException(status_code=404, detail=f"Folder {uid} not found or delete failed")
    return {"status": "success", "message": f"Folder {uid} deleted"}