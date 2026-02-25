"""
Internal token validation route — consumed only by the gateway auth service.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from config import config
from services.database_auth_service import DatabaseAuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal", tags=["internal"])
_auth_service = DatabaseAuthService()


class OtlpValidateRequest(BaseModel):
    token: str | None = None


def _get_internal_token() -> str:
    return config.get_secret("GATEWAY_INTERNAL_SERVICE_TOKEN") or ""


def _verify_service_token(x_internal_token: str = Header(...)) -> None:
    token = _get_internal_token()
    if not token:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal service token not configured")
    if not secrets.compare_digest(x_internal_token, token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")


def _validate_token_or_404(token: str):
    try:
        org_id = _auth_service.validate_otlp_token(token)
    except SQLAlchemyError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Auth database unavailable")

    if not org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    return {"org_id": org_id}


@router.get("/otlp/validate", dependencies=[Depends(_verify_service_token)])
async def validate_otlp_token_query(token: str = Query(..., min_length=1)):
    # Deprecated compatibility path: token query parameter.
    return _validate_token_or_404(token)


@router.post("/otlp/validate", dependencies=[Depends(_verify_service_token)])
async def validate_otlp_token_post(
    payload: OtlpValidateRequest,
    x_otlp_token: str | None = Header(None),
):
    token = (payload.token or x_otlp_token or "").strip()
    if not token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing token")
    return _validate_token_or_404(token)
