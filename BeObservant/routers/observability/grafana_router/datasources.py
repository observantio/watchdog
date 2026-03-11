"""
Data source management endpoints for Be Observant Grafana proxy router.

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
from middleware.dependencies import require_any_permission_with_scope, require_permission_with_scope
from middleware.error_handlers import handle_route_errors
from models.access.auth_models import Permission, TokenData
from models.grafana.grafana_datasource_models import Datasource, DatasourceCreate, DatasourceUpdate
from models.observability.grafana_request_models import GrafanaDatasourceQueryRequest, GrafanaHiddenToggleRequest
from services.grafana.route_payloads import validate_visibility

from .shared import hidden_toggle_context, proxy, router, rtp, scope_context
from custom_types.json import JSONDict


@router.post("/ds/query")
@handle_route_errors()
async def datasource_query(
    payload: GrafanaDatasourceQueryRequest,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.QUERY_DATASOURCES, "grafana")),
    db: Session = Depends(get_db),
) -> object:
    user_id, tenant_id, group_ids, _ = scope_context(current_user)
    await proxy.enforce_datasource_query_access(
        db=db,
        payload=payload.model_dump(exclude_none=True),
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
    )
    return await proxy.query_datasource(payload.model_dump(exclude_none=True))


@router.get("/datasources/meta/filters")
async def get_datasource_filter_metadata(
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DATASOURCES, "grafana")),
    db: Session = Depends(get_db),
) -> JSONDict:
    return await rtp(proxy.get_datasource_metadata, db=db, tenant_id=current_user.tenant_id)


@router.get("/datasources/name/{name}", response_model=Datasource)
async def get_datasource_by_name(
    name: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DATASOURCES, "grafana")),
    db: Session = Depends(get_db),
) -> Datasource:
    user_id, tenant_id, group_ids, _ = scope_context(current_user)
    datasource = await proxy.get_datasource_by_name(
        db=db,
        name=name,
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
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
) -> List[Datasource]:
    user_id, tenant_id, group_ids, _ = scope_context(current_user)
    datasource_context = await rtp(proxy.build_datasource_list_context, db, tenant_id=tenant_id, uid=uid)
    return await proxy.get_datasources(
        db=db,
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
        uid=uid,
        team_id=team_id,
        show_hidden=show_hidden,
        limit=limit,
        offset=offset,
        datasource_context=datasource_context,
    )


@router.get("/datasources/{uid}", response_model=Datasource)
async def get_datasource_by_uid(
    uid: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_DATASOURCES, "grafana")),
    db: Session = Depends(get_db),
) -> Datasource:
    user_id, tenant_id, group_ids, _ = scope_context(current_user)
    datasource = await proxy.get_datasource(
        db=db,
        uid=uid,
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
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
) -> Datasource:
    validate_visibility(visibility)
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    result = await proxy.create_datasource(
        db=db,
        datasource_create=datasource,
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
        visibility=visibility,
        shared_group_ids=shared_group_ids or [],
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
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_DATASOURCES, "grafana")),
    db: Session = Depends(get_db),
) -> Datasource:
    validate_visibility(visibility)
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    result = await proxy.update_datasource(
        db=db,
        uid=uid,
        datasource_update=datasource,
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
        visibility=visibility,
        shared_group_ids=shared_group_ids,
        is_admin=is_admin,
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
) -> JSONDict:
    user_id, tenant_id, group_ids, _ = scope_context(current_user)
    ok = await proxy.delete_datasource(
        db=db,
        uid=uid,
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
    )
    if not ok:
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
) -> JSONDict:
    user_id, tenant_id = hidden_toggle_context(current_user)
    ok = await rtp(
        proxy.toggle_datasource_hidden,
        db=db,
        uid=uid,
        user_id=user_id,
        tenant_id=tenant_id,
        hidden=payload.hidden,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"Datasource {uid} not found")
    return {"status": "success", "hidden": payload.hidden}
