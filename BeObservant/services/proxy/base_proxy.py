"""
Shared base class for internal service proxy clients.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx
import jwt

from database import get_db_session
from db_models import AuditLog
from models.access.auth_models import TokenData


class BaseProxyService:
    _resource_type: str = "proxy"

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float,
        tls_enabled: bool,
        ca_cert_path: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        verify: str | bool = True
        if not tls_enabled:
            verify = False
        elif ca_cert_path:
            verify = ca_cert_path
        self._client = httpx.AsyncClient(timeout=self.timeout, verify=verify)

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
                    resource_type=self._resource_type,
                    resource_id=resource_id,
                    details=details,
                )
            )

    @staticmethod
    def _build_base_jwt_claims(
        *,
        current_user: TokenData,
        tenant_id: str,
        issuer: str,
        audience: str,
        ttl_seconds: int,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "iss": issuer,
            "aud": audience,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
            "jti": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "org_id": getattr(current_user, "org_id", tenant_id),
            "user_id": current_user.user_id,
            "username": current_user.username,
            "role": getattr(
                getattr(current_user, "role", "user"),
                "value",
                getattr(current_user, "role", "user"),
            ),
            "group_ids": list(getattr(current_user, "group_ids", []) or []),
            "permissions": list(getattr(current_user, "permissions", []) or []),
            "is_superuser": bool(getattr(current_user, "is_superuser", False)),
        }

    @staticmethod
    def _encode_jwt(payload: Dict[str, Any], key: str, algorithm: str) -> str:
        return jwt.encode(payload, key, algorithm=algorithm)

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