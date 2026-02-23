"""Proxy client for forwarding BeCertain API calls through BeObservant."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx
import jwt
from fastapi import HTTPException, status

from config import config
from database import get_db_session
from db_models import AuditLog
from models.access.auth_models import TokenData

logger = logging.getLogger(__name__)


class BeCertainProxyService:
    def __init__(self) -> None:
        self.base_url = config.BECERTAIN_URL.rstrip("/")
        self.timeout = float(config.BECERTAIN_TIMEOUT_SECONDS)
        verify: str | bool = True
        if not bool(config.BECERTAIN_TLS_ENABLED):
            verify = False
        elif config.BECERTAIN_CA_CERT_PATH:
            verify = config.BECERTAIN_CA_CERT_PATH
        self._client = httpx.AsyncClient(timeout=self.timeout, verify=verify)

    def _sign_context_token(self, *, current_user: TokenData, tenant_id: str) -> str:
        key = config.get_secret("BECERTAIN_CONTEXT_SIGNING_KEY")
        if not key:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Missing BeCertain signing key")

        now = datetime.now(timezone.utc)
        payload = {
            "iss": config.BECERTAIN_CONTEXT_ISSUER,
            "aud": config.BECERTAIN_CONTEXT_AUDIENCE,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=int(config.BECERTAIN_CONTEXT_TTL_SECONDS))).timestamp()),
            "jti": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "org_id": getattr(current_user, "org_id", tenant_id),
            "user_id": current_user.user_id,
            "username": current_user.username,
            "role": getattr(getattr(current_user, "role", "user"), "value", getattr(current_user, "role", "user")),
            "group_ids": list(getattr(current_user, "group_ids", []) or []),
            "permissions": list(getattr(current_user, "permissions", []) or []),
            "is_superuser": bool(getattr(current_user, "is_superuser", False)),
        }
        algo = str(config.BECERTAIN_CONTEXT_ALGORITHM or "HS256").strip()
        return jwt.encode(payload, key, algorithm=algo)

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            text = (response.text or "").strip()
            return text or response.reason_phrase
        if isinstance(body, dict):
            detail = body.get("detail")
            if isinstance(detail, str) and detail:
                return detail
            message = body.get("message")
            if isinstance(message, str) and message:
                return message
        return json.dumps(body)[:500]

    def write_audit(
        self,
        *,
        current_user: Optional[TokenData],
        action: str,
        resource_id: str,
        details: Dict[str, Any],
    ) -> None:
        with get_db_session() as db:
            db.add(
                AuditLog(
                    tenant_id=getattr(current_user, "tenant_id", None),
                    user_id=getattr(current_user, "user_id", None),
                    action=action,
                    resource_type="becertain_proxy",
                    resource_id=resource_id,
                    details=details,
                )
            )

    async def request_json(
        self,
        *,
        method: str,
        upstream_path: str,
        current_user: TokenData,
        tenant_id: str,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        audit_action: str = "becertain.proxy",
        correlation_id: Optional[str] = None,
    ) -> Any:
        service_token = config.get_secret("BECERTAIN_SERVICE_TOKEN")
        if not service_token:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="BeCertain service token not configured")

        context_token = self._sign_context_token(current_user=current_user, tenant_id=tenant_id)
        corr = correlation_id or str(uuid.uuid4())
        target = f"{self.base_url}{upstream_path}"
        headers = {
            "X-Service-Token": service_token,
            "Authorization": f"Bearer {context_token}",
            "X-Correlation-ID": corr,
            "Content-Type": "application/json",
        }

        started = time.time()
        try:
            response = await self._client.request(
                method=method.upper(),
                url=target,
                headers=headers,
                params=params or None,
                json=payload if payload is not None else None,
            )
        except httpx.TimeoutException as exc:
            self.write_audit(
                current_user=current_user,
                action=f"{audit_action}.timeout",
                resource_id=upstream_path,
                details={"correlation_id": corr, "timeout": self.timeout, "method": method.upper()},
            )
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="BeCertain request timed out") from exc
        except Exception as exc:
            self.write_audit(
                current_user=current_user,
                action=f"{audit_action}.error",
                resource_id=upstream_path,
                details={"correlation_id": corr, "error": type(exc).__name__, "method": method.upper()},
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to contact BeCertain") from exc

        elapsed_ms = int((time.time() - started) * 1000)
        self.write_audit(
            current_user=current_user,
            action=f"{audit_action}.complete",
            resource_id=upstream_path,
            details={
                "correlation_id": corr,
                "status_code": response.status_code,
                "latency_ms": elapsed_ms,
                "method": method.upper(),
            },
        )

        if response.status_code >= 400:
            detail = self._extract_error_detail(response)
            raise HTTPException(status_code=response.status_code, detail=detail)

        try:
            return response.json()
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="BeCertain returned invalid JSON") from exc


becertain_proxy_service = BeCertainProxyService()
