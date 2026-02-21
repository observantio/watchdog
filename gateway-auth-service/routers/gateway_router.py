"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
import logging

from fastapi import APIRouter, Request, Response, HTTPException, status

from services.gateway_service import GatewayAuthService, DatabaseUnavailable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gateway", tags=["gateway"])

_service = GatewayAuthService()


@router.api_route("/validate", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@router.api_route("/validate/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def validate_otlp_token(request: Request, path: str = ""):
    _service.enforce_ip_allowlist(request)
    _service.enforce_rate_limit(request)

    token = _service.extract_otlp_token(request.headers.get("x-otlp-token"))
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing x-otlp-token header")

    token_prefix = token[:3] + "..." if len(token) > 3 else token

    try:
        org_id = _service.validate_otlp_token(token)
    except DatabaseUnavailable:
        logger.warning("Auth backend unavailable")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth backend unavailable")

    if not org_id:
        logger.warning("OTLP token validation failed – token_prefix=%s", token_prefix)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or disabled OTLP token")

    response = Response(status_code=200)
    response.headers["X-Scope-OrgID"] = org_id
    return response


@router.get("/health")
async def health():
    return _service.health()