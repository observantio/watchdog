"""Core business logic for the standalone gateway auth service.

- rate limiting
- IP allowlist enforcement
- OTLP token extraction and DB-backed validation
- small health check

This mirrors the behaviour that previously lived in `main.py` but groups
related responsibilities into a testable service class.
"""
from __future__ import annotations

import os
import time
from threading import Lock
from typing import Optional, List
from ipaddress import ip_network, ip_address

from fastapi import Request, HTTPException, status
from sqlalchemy import select, and_, func
from sqlalchemy.exc import SQLAlchemyError

import db_models

RATE_LIMIT_PER_MINUTE = int(os.getenv("GATEWAY_RATE_LIMIT_PER_MINUTE", "300"))
IP_ALLOWLIST = (os.getenv("GATEWAY_IP_ALLOWLIST") or "").strip()


class TokenRateLimiter:
    def __init__(self, limit_per_minute: int):
        self.limit = max(1, int(limit_per_minute))
        self.window_seconds = 60
        self._hits: dict[str, list[float]] = {}
        self._lock = Lock()

    def enforce(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            bucket = self._hits.setdefault(key, [])
            while bucket and bucket[0] < cutoff:
                bucket.pop(0)

            if len(bucket) >= self.limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                )

            bucket.append(now)


def _parse_ip_allowlist(allowlist: str) -> List:
    if not allowlist:
        return []

    networks = []
    for raw in allowlist.split(","):
        entry = raw.strip()
        if not entry:
            continue
        if "/" in entry:
            networks.append(ip_network(entry, strict=False))
        else:
            ip = ip_address(entry)
            suffix = 32 if ip.version == 4 else 128
            networks.append(ip_network(f"{entry}/{suffix}", strict=False))
    return networks


class GatewayAuthService:
    """Service providing the gateway auth checks."""

    def __init__(self, rate_limit_per_minute: int = RATE_LIMIT_PER_MINUTE, ip_allowlist: str = IP_ALLOWLIST):
        self.rate_limiter = TokenRateLimiter(rate_limit_per_minute)
        self._networks = _parse_ip_allowlist(ip_allowlist)

    @staticmethod
    def extract_otlp_token(header_value: Optional[str]) -> str:
        return (header_value or "").strip()

    @staticmethod
    def _client_ip(request: Request) -> str:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            first = forwarded_for.split(",", 1)[0].strip()
            if first:
                return first

        if request.client and request.client.host:
            return request.client.host

        return "unknown"

    def enforce_ip_allowlist(self, request: Request) -> None:
        if not self._networks:
            return

        client = self._client_ip(request)
        try:
            addr = ip_address(client)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid client IP") from exc

        if any(addr in net for net in self._networks):
            return

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Source IP not allowed")

    def enforce_rate_limit(self, request: Request) -> None:
        self.rate_limiter.enforce(self._client_ip(request))

    def validate_otlp_token(self, token: str) -> Optional[str]:
        if not token:
            return None

        stmt = (
            select(db_models.UserApiKey.key)
            .join(db_models.User, db_models.User.id == db_models.UserApiKey.user_id)
            .join(db_models.Tenant, db_models.Tenant.id == db_models.User.tenant_id)
            .where(
                and_(
                    db_models.UserApiKey.otlp_token == token,
                    db_models.UserApiKey.is_enabled.is_(True),
                    db_models.User.is_active.is_(True),
                    db_models.Tenant.is_active.is_(True),
                )
            )
            .limit(1)
        )

        try:
            with db_models.SessionLocal() as db:
                return db.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError:
            raise

    def health(self) -> dict:
        try:
            with db_models.SessionLocal() as db:
                db.execute(select(func.count()).select_from(db_models.UserApiKey).limit(1))
        except Exception:
            return {"status": "unhealthy", "service": "gateway-auth-service"}
        return {"status": "healthy", "service": "gateway-auth-service"}
