"""
Proxy client for forwarding alertmanager API calls to BeNotified.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import jwt
from fastapi import HTTPException, Request, Response, status

from config import config
from database import get_db_session
from db_models import AuditLog
from middleware.dependencies import auth_service
from models.access.auth_models import TokenData

logger = logging.getLogger(__name__)


class BeNotifiedProxyService:
    def __init__(self) -> None:
        self.base_url = (config.BENOTIFIED_URL).rstrip("/")
        self.timeout = float(config.BENOTIFIED_TIMEOUT_SECONDS)
        verify: str | bool = True
        if not bool(config.BENOTIFIED_TLS_ENABLED):
            verify = False
        elif config.BENOTIFIED_CA_CERT_PATH:
            verify = config.BENOTIFIED_CA_CERT_PATH
        self._client = httpx.AsyncClient(timeout=self.timeout, verify=verify)

    def _resolve_actor_api_key_id(self, current_user: TokenData) -> Optional[str]:
        try:
            keys = auth_service.list_api_keys(current_user.user_id)
        except Exception:
            return None
        enabled = [k for k in (keys or []) if getattr(k, "is_enabled", True)]
        if not enabled:
            return None
        default = next((k for k in enabled if getattr(k, "is_default", False)), enabled[0])
        return str(getattr(default, "id", "") or "") or None

    def _sign_context_token(
        self,
        *,
        current_user: TokenData,
        api_key_id: Optional[str],
    ) -> str:
        key = config.get_secret("BENOTIFIED_CONTEXT_SIGNING_KEY")
        if not key:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Missing BeNotified signing key")

        algo = str(config.BENOTIFIED_CONTEXT_ALGORITHM or "HS256").strip()
        now = datetime.now(timezone.utc)
        payload = {
            "iss": config.BENOTIFIED_CONTEXT_ISSUER,
            "aud": config.BENOTIFIED_CONTEXT_AUDIENCE,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=int(config.BENOTIFIED_CONTEXT_TTL_SECONDS))).timestamp()),
            "jti": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.user_id,
            "username": current_user.username,
            "org_id": getattr(current_user, "org_id", current_user.tenant_id),
            "role": getattr(getattr(current_user, "role", "user"), "value", getattr(current_user, "role", "user")),
            "group_ids": list(getattr(current_user, "group_ids", []) or []),
            "permissions": list(getattr(current_user, "permissions", []) or []),
            "is_superuser": bool(getattr(current_user, "is_superuser", False)),
            "api_key_id": api_key_id,
        }
        return jwt.encode(payload, key, algorithm=algo)

    @staticmethod
    def _forwardable_response_headers(headers: httpx.Headers) -> dict[str, str]:
        passthrough = {}
        for key, value in headers.items():
            lk = key.lower()
            if lk in {"content-type", "cache-control", "etag", "x-request-id"}:
                passthrough[key] = value
        return passthrough

    def _write_audit(
        self,
        *,
        current_user: Optional[TokenData],
        action: str,
        resource_id: str,
        details: dict,
    ) -> None:
        with get_db_session() as db:
            db.add(
                AuditLog(
                    tenant_id=getattr(current_user, "tenant_id", None),
                    user_id=getattr(current_user, "user_id", None),
                    action=action,
                    resource_type="alertmanager_proxy",
                    resource_id=resource_id,
                    details=details,
                )
            )

    async def forward(
        self,
        *,
        request: Request,
        upstream_path: str,
        current_user: Optional[TokenData],
        require_api_key: bool,
        audit_action: str,
        correlation_id: Optional[str] = None,
    ) -> Response:
        service_token = config.get_secret("BENOTIFIED_SERVICE_TOKEN")
        if not service_token:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="BeNotified service token not configured")

        api_key_id: Optional[str] = None
        context_token: Optional[str] = None
        if current_user:
            api_key_id = self._resolve_actor_api_key_id(current_user)
            if require_api_key and not api_key_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No active API key available for this operation",
                )
            context_token = self._sign_context_token(current_user=current_user, api_key_id=api_key_id)

        target = f"{self.base_url}{upstream_path}"
        body = await request.body()
        start = time.time()
        corr = correlation_id or request.headers.get("X-Request-ID") or str(uuid.uuid4())

        headers = {
            "X-Service-Token": service_token,
            "X-Correlation-ID": corr,
            "X-Forwarded-For": request.client.host if request.client else "unknown",
        }
        for passthrough in ("x-beobservant-webhook-token", "x-scope-orgid", "X-Scope-OrgID"):
            value = request.headers.get(passthrough)
            if value:
                headers[passthrough] = value
        if context_token:
            headers["Authorization"] = f"Bearer {context_token}"

        try:
            upstream = await self._client.request(
                method=request.method,
                url=target,
                params=request.query_params,
                content=body,
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            self._write_audit(
                current_user=current_user,
                action=f"{audit_action}.timeout",
                resource_id=upstream_path,
                details={"correlation_id": corr, "timeout": self.timeout},
            )
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="BeNotified request timed out") from exc
        except Exception as exc:
            self._write_audit(
                current_user=current_user,
                action=f"{audit_action}.error",
                resource_id=upstream_path,
                details={"correlation_id": corr, "error": type(exc).__name__},
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to contact BeNotified") from exc

        elapsed_ms = int((time.time() - start) * 1000)
        self._write_audit(
            current_user=current_user,
            action=f"{audit_action}.complete",
            resource_id=upstream_path,
            details={
                "correlation_id": corr,
                "status_code": upstream.status_code,
                "latency_ms": elapsed_ms,
                "api_key_id": api_key_id,
                "method": request.method,
            },
        )

        content = upstream.content
        return Response(
            content=content,
            status_code=upstream.status_code,
            headers=self._forwardable_response_headers(upstream.headers),
        )


benotified_proxy_service = BeNotifiedProxyService()
