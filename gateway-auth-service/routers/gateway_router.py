"""FastAPI router for the gateway auth endpoints.

Only contains HTTP routing and thin request validation; business logic and
DB access live in `services.gateway_service.GatewayAuthService`.
"""
import logging

from fastapi import APIRouter, Request, Response, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from services.gateway_service import GatewayAuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gateway", tags=["gateway"])

_service = GatewayAuthService()


@router.get("/validate")
async def validate_otlp_token(request: Request):
    _service.enforce_ip_allowlist(request)
    _service.enforce_rate_limit(request)

    token = _service.extract_otlp_token(request.headers.get("x-otlp-token"))
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing x-otlp-token header")

    token_prefix = token[:3] + "..." if len(token) > 3 else token

    try:
        org_id = _service.validate_otlp_token(token)
    except SQLAlchemyError:
        logger.exception("Database error while validating OTLP token")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth database unavailable")

    if not org_id:
        logger.warning("OTLP token validation failed – token_prefix=%s", token_prefix)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or disabled OTLP token")

    response = Response(status_code=200)
    response.headers["X-Org-Id"] = org_id
    return response


@router.get("/health")
async def health():
    return _service.health()
