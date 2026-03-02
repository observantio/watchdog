"""
Service layer for internal API endpoints.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
see the LICENSE file distributed with this work or
https://www.apache.org/licenses/LICENSE-2.0 for details.
"""

from __future__ import annotations

import logging
import secrets
from fastapi import HTTPException, Header, status

from sqlalchemy.exc import SQLAlchemyError

from config import config
from services.database_auth_service import DatabaseAuthService

logger = logging.getLogger(__name__)

class InternalService:
    def __init__(self, auth_service: DatabaseAuthService | None = None):
        self._auth_service = auth_service or DatabaseAuthService()

    def _get_internal_token(self) -> str:
        return config.get_secret("GATEWAY_INTERNAL_SERVICE_TOKEN") or ""

    def verify_service_token(self, x_internal_token: str = Header(...)) -> None:
        token = self._get_internal_token()
        if not token:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal service token not configured")
        if not secrets.compare_digest(x_internal_token, token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")

    def validate_token_or_404(self, token: str):
        try:
            org_id = self._auth_service.validate_otlp_token(token, suppress_errors=False)
        except SQLAlchemyError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Auth database unavailable")
        except Exception:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Auth database unavailable")

        if not org_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND)

        return {"org_id": org_id}
