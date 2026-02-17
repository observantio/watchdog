"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


"""OTLP Gateway authentication router.

Provides the token validation endpoint consumed by the nginx OTLP gateway
via ``auth_request``.  The gateway sends each inbound OTLP request's
``x-otlp-token`` header here; this endpoint validates it and returns the
mapped ``X-Org-Id`` (org_id / X-Scope-OrgID) so that nginx can set the
correct tenant header before proxying to Loki, Tempo, or Mimir.
"""
import logging

from fastapi import APIRouter, Request, Response, HTTPException, status

from config import config
from middleware.dependencies import enforce_public_endpoint_security
from services.gateway_service import GatewayService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gateway", tags=["gateway"])

gateway_service = GatewayService()


@router.get("/validate")
async def validate_otlp_token(request: Request):
    """Validate an OTLP ingest token and return the mapped org_id.

    Called by the nginx ``auth_request`` subrequest.  On success, returns
    HTTP 200 with the ``X-Org-Id`` response header set to the org_id that
    nginx will forward as ``X-Scope-OrgID`` to the backend.
    """
    enforce_public_endpoint_security(
        request,
        scope="gateway_validate",
        limit=config.RATE_LIMIT_PUBLIC_PER_MINUTE,
        window_seconds=60,
        allowlist=config.GATEWAY_IP_ALLOWLIST,
    )

    token = gateway_service.extract_otlp_token(request.headers.get("x-otlp-token"))

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing x-otlp-token header",
        )

    org_id = gateway_service.validate_otlp_token(token)

    if org_id is None:
        logger.warning(
            "OTLP token validation failed – token_prefix=%s",
            token[:3] + "..." if len(token) > 3 else token,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or disabled OTLP token",
        )

    response = Response(status_code=200)
    response.headers["X-Org-Id"] = org_id
    return response
