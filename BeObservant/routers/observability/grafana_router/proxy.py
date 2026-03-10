"""
Grafana proxy endpoints for Be Observant observability router.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import Optional

from fastapi import Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response

from config import config
from middleware.dependencies import enforce_public_endpoint_security, require_authenticated_with_scope
from models.access.auth_models import TokenData
from models.observability.grafana_request_models import GrafanaBootstrapSessionRequest
from services.common.cookies import cookie_secure
from services.grafana.normalize import normalize_grafana_next_path

from .shared import auth_service, proxy, router


@router.get("/auth")
async def grafana_auth(
    request: Request,
    token: Optional[str] = Query(None),
    orig: Optional[str] = Query(None),
) -> Response:
    enforce_public_endpoint_security(
        request,
        scope="grafana_proxy_auth",
        limit=config.RATE_LIMIT_GRAFANA_PROXY_PER_MINUTE,
        window_seconds=60,
        allowlist=config.GRAFANA_PROXY_IP_ALLOWLIST,
        fallback_mode="deny",
    )
    headers = await proxy.authorize_proxy_request(request=request, auth_service=auth_service, token=token, orig=orig)
    return Response(status_code=204, headers=headers)


@router.post("/bootstrap-session")
async def bootstrap_grafana_session(
    request: Request,
    payload: GrafanaBootstrapSessionRequest = Body(default_factory=GrafanaBootstrapSessionRequest),
    _current_user: TokenData = Depends(require_authenticated_with_scope("grafana")),
) -> JSONResponse:
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
