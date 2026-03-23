"""
Api key management endpoints for Watchdog authentication router.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import List

from fastapi import Depends, HTTPException, Query, status
from pydantic import BaseModel

from middleware.dependencies import auth_service, require_permission_with_scope
from middleware.error_handlers import handle_route_errors
from models.access.api_key_models import ApiKey, ApiKeyCreate, ApiKeyShareUpdateRequest, ApiKeyShareUser, ApiKeyUpdate
from models.access.auth_models import Permission, TokenData

from .shared import router, rtp


class HideTogglePayload(BaseModel):
    hidden: bool = True


@router.get("/api-keys", response_model=List[ApiKey])
async def list_api_keys(
    show_hidden: bool = Query(False),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_API_KEYS, "auth")),
) -> List[ApiKey]:
    return await rtp(auth_service.list_api_keys, current_user.user_id, show_hidden)


@router.post("/api-keys", response_model=ApiKey)
@handle_route_errors()
async def create_api_key(
    key_create: ApiKeyCreate,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.CREATE_API_KEYS, "auth")),
) -> ApiKey:
    return await rtp(auth_service.create_api_key, current_user.user_id, current_user.tenant_id, key_create)


@router.patch("/api-keys/{key_id}", response_model=ApiKey)
@handle_route_errors()
async def update_api_key(
    key_id: str,
    key_update: ApiKeyUpdate,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_API_KEYS, "auth")),
) -> ApiKey:
    return await rtp(auth_service.update_api_key, current_user.user_id, key_id, key_update)


@router.post("/api-keys/{key_id}/otlp-token/regenerate", response_model=ApiKey)
@handle_route_errors()
async def regenerate_api_key_otlp_token(
    key_id: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_API_KEYS, "auth")),
) -> ApiKey:
    return await rtp(auth_service.regenerate_api_key_otlp_token, current_user.user_id, key_id)


@router.delete("/api-keys/{key_id}")
@handle_route_errors()
async def delete_api_key(
    key_id: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.DELETE_API_KEYS, "auth")),
) -> dict[str, str]:
    if not await rtp(auth_service.delete_api_key, current_user.user_id, key_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")
    return {"message": "API key deleted"}


@router.post("/api-keys/{key_id}/hide")
@handle_route_errors()
async def hide_api_key(
    key_id: str,
    payload: HideTogglePayload,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_API_KEYS, "auth")),
) -> dict[str, object]:
    await rtp(auth_service.set_api_key_hidden, current_user.user_id, key_id, bool(payload.hidden))
    return {"status": "success", "hidden": bool(payload.hidden)}


@router.get("/api-keys/{key_id}/shares", response_model=List[ApiKeyShareUser])
@handle_route_errors()
async def get_api_key_shares(
    key_id: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_API_KEYS, "auth")),
) -> List[ApiKeyShareUser]:
    result = await rtp(auth_service.list_api_key_shares, current_user.user_id, current_user.tenant_id, key_id)
    return [ApiKeyShareUser.model_validate(item) if isinstance(item, dict) else item for item in result]


@router.put("/api-keys/{key_id}/shares", response_model=List[ApiKeyShareUser])
@handle_route_errors()
async def put_api_key_shares(
    key_id: str,
    payload: ApiKeyShareUpdateRequest,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_API_KEYS, "auth")),
) -> List[ApiKeyShareUser]:
    result = await rtp(
        auth_service.replace_api_key_shares,
        current_user.user_id,
        current_user.tenant_id,
        key_id,
        payload.user_ids,
        payload.group_ids,
    )
    return [ApiKeyShareUser.model_validate(item) if isinstance(item, dict) else item for item in result]


@router.delete("/api-keys/{key_id}/shares/{shared_user_id}")
@handle_route_errors()
async def remove_api_key_share(
    key_id: str,
    shared_user_id: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_API_KEYS, "auth")),
) -> dict[str, str]:
    if not await rtp(
        auth_service.delete_api_key_share,
        current_user.user_id,
        current_user.tenant_id,
        key_id,
        shared_user_id,
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share not found")
    return {"message": "API key share removed"}
