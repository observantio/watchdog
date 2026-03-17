"""
Folder management endpoints for Watchdog Grafana proxy router.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from middleware.dependencies import require_any_permission_with_scope, require_authenticated_with_scope, require_permission_with_scope
from middleware.error_handlers import handle_route_errors
from models.access.auth_models import Permission, TokenData
from models.grafana.grafana_folder_models import Folder
from models.observability.grafana_request_models import (
    GrafanaCreateFolderRequest,
    GrafanaHiddenToggleRequest,
    GrafanaUpdateFolderRequest,
)
from services.grafana.route_payloads import validate_visibility

from .shared import hidden_toggle_context, proxy, router, rtp, scope_context
from custom_types.json import JSONDict


@router.get("/folders", response_model=List[Folder])
async def get_folders(
    show_hidden: bool = Query(False),
    current_user: TokenData = Depends(require_authenticated_with_scope("grafana")),
    db: Session = Depends(get_db),
) -> List[Folder]:
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    return await proxy.get_folders(
        db=db,
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
        show_hidden=show_hidden,
        is_admin=is_admin,
    )


@router.get("/folders/{uid}", response_model=Folder)
async def get_folder_by_uid(
    uid: str,
    current_user: TokenData = Depends(require_authenticated_with_scope("grafana")),
    db: Session = Depends(get_db),
) -> Folder:
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    folder = await proxy.get_folder(
        db=db,
        uid=uid,
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
        is_admin=is_admin,
    )
    if not folder:
        raise HTTPException(status_code=404, detail=f"Folder {uid} not found or access denied")
    return folder


@router.post("/folders", response_model=Folder)
@handle_route_errors()
async def create_folder(
    payload: GrafanaCreateFolderRequest,
    visibility: str = Query("private"),
    shared_group_ids: Optional[List[str]] = Query(None),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.CREATE_FOLDERS, "grafana")),
    db: Session = Depends(get_db),
) -> Folder:
    validate_visibility(visibility)
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    result = await proxy.create_folder(
        db=db,
        title=payload.title,
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
        visibility=visibility,
        shared_group_ids=shared_group_ids or [],
        allow_dashboard_writes=payload.allow_dashboard_writes,
        is_admin=is_admin,
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create folder")
    return result


@router.delete("/folders/{uid}")
@handle_route_errors()
async def delete_folder(
    uid: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.DELETE_FOLDERS, "grafana")),
    db: Session = Depends(get_db),
) -> JSONDict:
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    ok = await proxy.delete_folder(
        db=db,
        uid=uid,
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
        is_admin=is_admin,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"Folder {uid} not found or delete failed")
    return {"status": "success", "message": f"Folder {uid} deleted"}


@router.put("/folders/{uid}", response_model=Folder)
@handle_route_errors()
async def update_folder(
    uid: str,
    payload: GrafanaUpdateFolderRequest,
    visibility: Optional[str] = Query(None),
    shared_group_ids: Optional[List[str]] = Query(None),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.CREATE_FOLDERS, "grafana")),
    db: Session = Depends(get_db),
) -> Folder:
    validate_visibility(visibility)
    user_id, tenant_id, group_ids, is_admin = scope_context(current_user)
    result = await proxy.update_folder(
        db=db,
        uid=uid,
        user_id=user_id,
        tenant_id=tenant_id,
        group_ids=group_ids,
        title=payload.title,
        visibility=visibility,
        shared_group_ids=shared_group_ids,
        allow_dashboard_writes=payload.allow_dashboard_writes,
        is_admin=is_admin,
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Folder {uid} not found or update failed")
    return result


@router.post("/folders/{uid}/hide")
async def hide_folder(
    uid: str,
    payload: GrafanaHiddenToggleRequest = Body(default_factory=GrafanaHiddenToggleRequest),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.CREATE_FOLDERS, Permission.DELETE_FOLDERS], "grafana")
    ),
    db: Session = Depends(get_db),
) -> JSONDict:
    user_id, tenant_id = hidden_toggle_context(current_user)
    ok = await rtp(
        proxy.toggle_folder_hidden,
        db=db,
        uid=uid,
        user_id=user_id,
        tenant_id=tenant_id,
        hidden=payload.hidden,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"Folder {uid} not found")
    return {"status": "success", "hidden": payload.hidden}
