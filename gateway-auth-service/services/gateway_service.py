"""
Gateway authentication and rate limiting service.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import json
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request
from ipaddress import ip_address, ip_network
from typing import Optional

from fastapi import HTTPException, Request, status

from . import config as gw_config
from .rate_limit import make_default_rate_limiter
from .token_cache import make_token_cache

logger = logging.getLogger(__name__)


class DatabaseUnavailable(Exception):
    pass


def _parse_networks(allowlist: str) -> list:
    networks = []
    for entry in (e.strip() for e in allowlist.split(",") if e.strip()):
        if "/" not in entry:
            addr = ip_address(entry)
            prefix = "32" if addr.version == 4 else "128"
            entry = f"{entry}/{prefix}"
        networks.append(ip_network(entry, strict=False))
    return networks


def _build_ssl_context() -> ssl.SSLContext | None:
    if not gw_config.AUTH_API_URL.startswith("https"):
        return None
    ctx = ssl.create_default_context()
    if gw_config.SSL_CA_CERTS:
        ctx.load_verify_locations(gw_config.SSL_CA_CERTS)
    if not gw_config.SSL_VERIFY:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


class GatewayAuthService:
    __slots__ = ("_rate_limiter", "_networks", "_token_cache", "_ssl_ctx")

    def __init__(
        self,
        *,
        rate_limit_per_minute: Optional[int] = None,
        ip_allowlist: Optional[str] = None,
        token_cache_ttl: Optional[int] = None,
        rate_limit_backend: Optional[str] = None,
        rate_limit_redis_url: Optional[str] = None,
    ) -> None:
        self._rate_limiter = make_default_rate_limiter(
            rate_limit_per_minute if rate_limit_per_minute is not None else gw_config.RATE_LIMIT_PER_MINUTE,
            rate_limit_backend if rate_limit_backend is not None else gw_config.RATE_LIMIT_BACKEND,
            rate_limit_redis_url if rate_limit_redis_url is not None else gw_config.RATE_LIMIT_REDIS_URL,
        )
        self._networks = _parse_networks(
            ip_allowlist if ip_allowlist is not None else gw_config.IP_ALLOWLIST
        )
        self._token_cache = make_token_cache(
            token_cache_ttl if token_cache_ttl is not None else gw_config.TOKEN_CACHE_TTL,
            gw_config.TOKEN_CACHE_REDIS_URL or None,
        )
        self._ssl_ctx = _build_ssl_context()

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
            if not gw_config.ALLOWLIST_FAIL_OPEN:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Source IP not allowed")
            return

        raw_ip = self._client_ip(request)
        try:
            addr = ip_address(raw_ip)
        except ValueError:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid client IP")

        if not any(addr in net for net in self._networks):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Source IP not allowed")

    def enforce_rate_limit(self, request: Request) -> None:
        self._rate_limiter.enforce(self._client_ip(request))

    def _fetch_org_from_api(self, token: str) -> Optional[str]:
        url = f"{gw_config.AUTH_API_URL}?token={urllib.parse.quote(token)}"
        headers = {}
        if gw_config.INTERNAL_SERVICE_TOKEN:
            headers["X-Internal-Token"] = gw_config.INTERNAL_SERVICE_TOKEN

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=2, context=self._ssl_ctx) as resp:
                if resp.status == 200:
                    try:
                        data = json.loads(resp.read())
                    except Exception:
                        return None
                    return data.get("org_id")
                if resp.status == 404:
                    return None
                raise DatabaseUnavailable(f"unexpected status {resp.status}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            logger.warning("Auth API HTTPError %s", e)
            raise DatabaseUnavailable from e
        except Exception as e:
            logger.warning("Auth API request failed: %s", e)
            raise DatabaseUnavailable from e

    def validate_otlp_token(self, token: str) -> Optional[str]:
        if not token:
            return None

        hit, cached = self._token_cache.get(token)
        if hit:
            return cached

        try:
            org = self._fetch_org_from_api(token)
        except DatabaseUnavailable:
            raise
        except Exception:
            logger.warning("Auth API fetch unexpected error", exc_info=True)
            raise DatabaseUnavailable

        self._token_cache.set(token, org)
        return org

    def health(self) -> dict:
        return {"status": "healthy", "service": "gateway-auth-service"}