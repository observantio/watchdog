"""
Dashboard management endpoints for Watchdog Grafana proxy router.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from config import config
from database import get_db
from middleware.dependencies import (
    require_any_permission_with_scope,
    require_authenticated_with_scope,
    require_permission_with_scope,
)
from middleware.error_handlers import handle_route_errors
from models.access.auth_models import Permission, TokenData
from models.grafana.grafana_dashboard_models import DashboardSearchResult
from models.observability.grafana_request_models import GrafanaDashboardPayloadRequest, GrafanaHiddenToggleRequest
from services.grafana.route_payloads import (
    parse_dashboard_create_payload,
    parse_dashboard_update_payload,
    validate_visibility,
)

from .shared import dashboard_payload, dashboard_uid, hidden_toggle_context, proxy, router, rtp, scope_context
from custom_types.json import JSONDict


@router.get("/dashboards/meta/filters")
async def get_dashboard_filter_metadata(
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DASHBOARDS, "grafana")),
    db: Session = Depends(get_db),
) -> JSONDict:
    return await rtp(proxy.get_dashboard_metadata, db=db, tenant_id=current_user.tenant_id)


@router.get("/dashboards/search")
async def search_dashboards(
    query: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    starred: Optional[bool] = Query(None),
    folder_ids: Optional[List[int]] = Query(None, alias="folderIds"),
    folder_uids: Optional[List[str]] = Query(None, alias="folderUIDs"),
    dashboard_uids: Optional[List[str]] = Query(None, alias="dashboardUID"),
    search_type: Optional[str] = Query(None, alias="type"),
    uid: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    show_hidden: bool = Query(False),
    limit: int = Query(config.DEFAULT_QUERY_LIMIT, ge=1, le=config.MAX_QUERY_LIMIT),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DASHBOARDS, "grafana")),
    db: Session = Depends(get_db),
) -> List[DashboardSearchResult]:
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    search_context = await rtp(proxy.build_dashboard_search_context, db, tenant_id=current_user.tenant_id, uid=uid)
    return await proxy.search_dashboards(
        db=db,
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
        query=query,
        tag=tag,
        starred=starred,
        folder_ids=folder_ids,
        folder_uids=folder_uids,
        dashboard_uids=dashboard_uids,
        uid=uid,
        team_id=team_id,
        show_hidden=show_hidden,
        limit=limit,
        offset=offset,
        search_context=search_context,
        is_admin=is_admin,
        exclude_foldered_dashboards=bool(
            search_type is not None and not folder_ids and not folder_uids and not dashboard_uids
        ),
    )


@router.get("/dashboards/{uid}")
async def get_dashboard(
    uid: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DASHBOARDS, "grafana")),
    db: Session = Depends(get_db),
) -> JSONDict:
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    dashboard = await proxy.get_dashboard(
        db=db,
        uid=uid,
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
        is_admin=is_admin,
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
    current_user: TokenData = Depends(require_authenticated_with_scope("grafana")),
    db: Session = Depends(get_db),
) -> JSONDict:
    validate_visibility(visibility)
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    raw = dashboard_payload(payload)
    result = await proxy.create_dashboard(
        db=db,
        dashboard_create=parse_dashboard_create_payload(raw),
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
        visibility=visibility,
        shared_group_ids=shared_group_ids or [],
        is_admin=is_admin,
        actor_permissions=current_user.permissions or [],
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create dashboard")
    return result


@router.post("/dashboards/db")
@router.post("/dashboards/db/")
@handle_route_errors()
async def save_dashboard_from_grafana_ui(
    payload: GrafanaDashboardPayloadRequest,
    current_user: TokenData = Depends(require_authenticated_with_scope("grafana")),
    db: Session = Depends(get_db),
) -> JSONDict:
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    raw = dashboard_payload(payload)
    uid = dashboard_uid(raw)

    if uid:
        existing = await rtp(proxy.build_dashboard_search_context, db, tenant_id=tenant_id, uid=uid)
        if existing.get("uid_db_dashboard") is not None:
            result = await proxy.update_dashboard(
                db=db,
                uid=uid,
                dashboard_update=parse_dashboard_update_payload(raw),
                user_id=user_id,
                tenant_id=tenant_id,
                group_ids=group_ids,
                visibility=None,
                shared_group_ids=None,
                is_admin=is_admin,
                actor_permissions=current_user.permissions or [],
            )
            if result:
                return result

    result = await proxy.create_dashboard(
        db=db,
        dashboard_create=parse_dashboard_create_payload(raw),
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
        visibility="private",
        shared_group_ids=[],
        is_admin=is_admin,
        actor_permissions=current_user.permissions or [],
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to save dashboard")
    return result


@router.put("/dashboards/{uid}")
@handle_route_errors()
async def update_dashboard(
    uid: str,
    payload: GrafanaDashboardPayloadRequest,
    visibility: Optional[str] = Query(None),
    shared_group_ids: Optional[List[str]] = Query(None),
    current_user: TokenData = Depends(require_authenticated_with_scope("grafana")),
    db: Session = Depends(get_db),
) -> JSONDict:
    validate_visibility(visibility)
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    raw = dashboard_payload(payload)
    result = await proxy.update_dashboard(
        db=db,
        uid=uid,
        dashboard_update=parse_dashboard_update_payload(raw),
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
        visibility=visibility,
        shared_group_ids=shared_group_ids,
        is_admin=is_admin,
        actor_permissions=current_user.permissions or [],
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
) -> JSONDict:
    user_id, tenant_id, group_ids, _ = scope_context(current_user)
    ok = await proxy.delete_dashboard(
        db=db,
        uid=uid,
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
    )
    if not ok:
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
) -> JSONDict:
    user_id, tenant_id = hidden_toggle_context(current_user)
    ok = await rtp(
        proxy.toggle_dashboard_hidden,
        db=db,
        uid=uid,
        user_id=user_id,
        tenant_id=tenant_id,
        hidden=payload.hidden,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"Dashboard {uid} not found")
    return {"status": "success", "hidden": payload.hidden}
