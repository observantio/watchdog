"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
from __future__ import annotations

import os
import time
import logging
from threading import Lock
from typing import Optional, List
from ipaddress import ip_network, ip_address

from fastapi import Request, HTTPException, status
from sqlalchemy import select, and_, func, or_
from sqlalchemy.exc import SQLAlchemyError

import db_models

try:
    import redis
except Exception:
    redis = None

RATE_LIMIT_PER_MINUTE = int(os.getenv("GATEWAY_RATE_LIMIT_PER_MINUTE", "300"))
IP_ALLOWLIST = (os.getenv("GATEWAY_IP_ALLOWLIST") or "").strip()
GATEWAY_ALLOWLIST_FAIL_OPEN = str(os.getenv("GATEWAY_ALLOWLIST_FAIL_OPEN", "false")).strip().lower() in ("1","true","yes","on")
RATE_LIMIT_BACKEND = (os.getenv("GATEWAY_RATE_LIMIT_BACKEND", "auto") or "auto").strip().lower()
RATE_LIMIT_REDIS_URL = (os.getenv("GATEWAY_RATE_LIMIT_REDIS_URL", "") or "").strip()

logger = logging.getLogger(__name__)


class DatabaseUnavailable(Exception):
    """Raised when the auth database is unavailable or returns an internal error."""


class TokenRateLimiter:
    def __init__(self, limit_per_minute: int):
        self.limit = max(1, int(limit_per_minute))
        self.window_seconds = 60
        self._hits: dict[str, tuple[float, int]] = {}
        self._lock = Lock()
        self._ops = 0

    def _cleanup(self, now: float) -> None:
        self._ops += 1
        if self._ops % 1024 != 0:
            return
        threshold = now - (self.window_seconds * 2)
        stale = [key for key, (window_start, _count) in self._hits.items() if window_start < threshold]
        for key in stale:
            self._hits.pop(key, None)

    def enforce(self, key: str) -> None:
        now = time.time()

        with self._lock:
            self._cleanup(now)
            window_start, count = self._hits.get(key, (now, 0))
            if (now - window_start) >= self.window_seconds:
                window_start, count = now, 0

            count += 1
            self._hits[key] = (window_start, count)

            if count > self.limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                )


class RedisTokenRateLimiter:
    def __init__(self, limit_per_minute: int, redis_url: str, *, key_prefix: str = "beobs:gateway:rl"):
        if redis is None:
            raise RuntimeError("redis package is not installed")
        self.limit = max(1, int(limit_per_minute))
        self.window_seconds = 60
        self.key_prefix = key_prefix
        self.client = redis.from_url(
            redis_url,
            socket_timeout=0.25,
            socket_connect_timeout=0.25,
            decode_responses=True,
        )

    def enforce(self, key: str) -> None:
        now = int(time.time())
        window_id = now // self.window_seconds
        bucket_key = f"{self.key_prefix}:{key}:{window_id}"

        pipe = self.client.pipeline(transaction=True)
        pipe.incr(bucket_key)
        pipe.expire(bucket_key, self.window_seconds + 1)
        count, _ = pipe.execute()

        if int(count) > self.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )


class HybridTokenRateLimiter:
    def __init__(self, primary: Optional[RedisTokenRateLimiter], fallback: TokenRateLimiter):
        self.primary = primary
        self.fallback = fallback
        self._last_warning = 0.0

    def enforce(self, key: str) -> None:
        if self.primary is not None:
            try:
                self.primary.enforce(key)
                return
            except Exception as exc:
                now = time.monotonic()
                if now - self._last_warning > 30:
                    logger.warning("Gateway Redis limiter unavailable, using in-memory fallback: %s", exc)
                    self._last_warning = now
        self.fallback.enforce(key)


def _build_rate_limiter(limit_per_minute: int) -> HybridTokenRateLimiter:
    fallback = TokenRateLimiter(limit_per_minute)

    if RATE_LIMIT_BACKEND in {"memory", "in-memory", "inmemory"}:
        logger.info("Gateway rate limiting backend: in-memory")
        return HybridTokenRateLimiter(None, fallback)

    if not RATE_LIMIT_REDIS_URL:
        if RATE_LIMIT_BACKEND == "redis":
            logger.warning("GATEWAY_RATE_LIMIT_BACKEND=redis but GATEWAY_RATE_LIMIT_REDIS_URL is not set; using in-memory limiter")
        return HybridTokenRateLimiter(None, fallback)

    try:
        primary = RedisTokenRateLimiter(limit_per_minute, RATE_LIMIT_REDIS_URL)
        logger.info("Gateway rate limiting backend: redis")
        return HybridTokenRateLimiter(primary, fallback)
    except Exception as exc:
        logger.warning("Failed to initialize gateway Redis limiter; using in-memory fallback: %s", exc)
        return HybridTokenRateLimiter(None, fallback)


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
        self.rate_limiter = _build_rate_limiter(rate_limit_per_minute)
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
            if GATEWAY_ALLOWLIST_FAIL_OPEN:
                return
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Source IP not allowed")

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

        # Support both dedicated OTLP token and legacy key-based token to
        # preserve compatibility with existing agents/configs.
        stmt = (
            select(db_models.UserApiKey.key)
            .join(db_models.User, db_models.User.id == db_models.UserApiKey.user_id)
            .join(db_models.Tenant, db_models.Tenant.id == db_models.User.tenant_id)
            .where(
                and_(
                    or_(
                        db_models.UserApiKey.otlp_token == token,
                        db_models.UserApiKey.key == token,
                    ),
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
        except SQLAlchemyError as exc:
            logger.warning("Database error validating OTLP token")
            # Normalize internal DB errors to a service-level exception so the
            # HTTP layer can return an appropriate 503 without leaking internals.
            raise DatabaseUnavailable("Auth database unavailable") from exc

    def health(self) -> dict:
        try:
            with db_models.SessionLocal() as db:
                db.execute(select(func.count()).select_from(db_models.UserApiKey).limit(1))
        except Exception:
            return {"status": "unhealthy", "service": "gateway-auth-service"}
        return {"status": "healthy", "service": "gateway-auth-service"}
