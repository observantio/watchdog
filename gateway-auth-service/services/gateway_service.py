from __future__ import annotations

import os
import time
import logging
from threading import Lock
from typing import Optional
from ipaddress import ip_network, ip_address

from fastapi import Request, HTTPException, status
from sqlalchemy import select, and_, func, or_
from sqlalchemy.exc import SQLAlchemyError

import db_models

try:
    import redis
except ImportError:
    redis = None

logger = logging.getLogger(__name__)

_RATE_LIMIT        = int(os.getenv("GATEWAY_RATE_LIMIT_PER_MINUTE", "300"))
_IP_ALLOWLIST      = os.getenv("GATEWAY_IP_ALLOWLIST", "").strip()
_FAIL_OPEN         = os.getenv("GATEWAY_ALLOWLIST_FAIL_OPEN", "false").lower() in ("1", "true", "yes", "on")
_RL_BACKEND        = os.getenv("GATEWAY_RATE_LIMIT_BACKEND", "auto").strip().lower()
_RL_REDIS_URL      = os.getenv("GATEWAY_RATE_LIMIT_REDIS_URL", "").strip()
_TOKEN_CACHE_TTL   = int(os.getenv("GATEWAY_TOKEN_CACHE_TTL", "60"))


class DatabaseUnavailable(Exception):
    pass


from .rate_limit import TokenRateLimiter, HybridTokenRateLimiter, make_default_rate_limiter
from .token_cache import TokenCache

_InMemoryRateLimiter = TokenRateLimiter
_RedisRateLimiter = None 
_RateLimiter = make_default_rate_limiter
_TokenCache = TokenCache


def _parse_networks(allowlist: str) -> list:
    result = []
    for entry in (e.strip() for e in allowlist.split(",") if e.strip()):
        if "/" not in entry:
            ip = ip_address(entry)
            entry = f"{entry}/{'32' if ip.version == 4 else '128'}"
        result.append(ip_network(entry, strict=False))
    return result


class GatewayAuthService:
    def __init__(self, *, rate_limit_per_minute: Optional[int] = None, ip_allowlist: Optional[str] = None, token_cache_ttl: Optional[int] = None, rate_limit_backend: Optional[str] = None, rate_limit_redis_url: Optional[str] = None):
        """Initialize service.

        Optional keyword arguments override environment defaults (useful for tests).
        """
        rate_limit = rate_limit_per_minute if rate_limit_per_minute is not None else _RATE_LIMIT
        backend = rate_limit_backend if rate_limit_backend is not None else _RL_BACKEND
        redis_url = rate_limit_redis_url if rate_limit_redis_url is not None else _RL_REDIS_URL
        self._rate_limiter = make_default_rate_limiter(rate_limit, backend, redis_url)

        allowlist = ip_allowlist if ip_allowlist is not None else _IP_ALLOWLIST
        self._networks = _parse_networks(allowlist)

        # token cache (allow TTL override)
        ttl = token_cache_ttl if token_cache_ttl is not None else _TOKEN_CACHE_TTL
        self._token_cache = TokenCache(ttl)

    @staticmethod
    def _client_ip(request: Request) -> str:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            first = xff.split(",", 1)[0].strip()
            if first:
                return first
        return request.client.host if request.client else "unknown"

    @staticmethod
    def extract_otlp_token(value: Optional[str]) -> str:
        return (value or "").strip()

    def enforce_ip_allowlist(self, request: Request) -> None:
        if not self._networks:
            if not _FAIL_OPEN:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Source IP not allowed")
            return

        try:
            addr = ip_address(self._client_ip(request))
        except ValueError:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid client IP")

        if not any(addr in net for net in self._networks):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Source IP not allowed")

    def enforce_rate_limit(self, request: Request) -> None:
        self._rate_limiter.enforce(self._client_ip(request))

    def validate_otlp_token(self, token: str) -> Optional[str]:
        if not token:
            return None

        hit, cached = self._token_cache.get(token)
        if hit:
            return cached

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
                org_id = db.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as exc:
            logger.warning("Database error validating OTLP token")
            raise DatabaseUnavailable from exc

        self._token_cache.set(token, org_id)
        return org_id

    def health(self) -> dict:
        try:
            with db_models.SessionLocal() as db:
                db.execute(select(func.count()).select_from(db_models.UserApiKey).limit(1))
            return {"status": "healthy", "service": "gateway-auth-service"}
        except Exception:
            return {"status": "unhealthy", "service": "gateway-auth-service"}