"""
Gateway authentication and rate limiting service.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import logging
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
from typing import Optional
from urllib.parse import quote

import httpx
from fastapi import HTTPException, Request, status

import config as gw_config
from models.exceptions import DatabaseUnavailable
from .rate_limit import make_default_rate_limiter
from .token_cache import make_token_cache

logger = logging.getLogger(__name__)

__all__ = ["GatewayAuthService", "DatabaseUnavailable"]


def _parse_networks(allowlist: str) -> list[IPv4Network | IPv6Network]:
    networks: list[IPv4Network | IPv6Network] = []
    for entry in (e.strip() for e in allowlist.split(",") if e.strip()):
        if "/" not in entry:
            addr = ip_address(entry)
            prefix = "32" if addr.version == 4 else "128"
            entry = f"{entry}/{prefix}"
        networks.append(ip_network(entry, strict=False))
    return networks


def _http_verify_setting() -> str | bool:
    if not gw_config.AUTH_API_URL.startswith("https"):
        return False
    if gw_config.SSL_CA_CERTS:
        return gw_config.SSL_CA_CERTS
    return bool(gw_config.SSL_VERIFY)


class GatewayAuthService:
    __slots__ = ("_rate_limiter", "_networks", "_token_cache", "_http_verify", "_auth_api_url")

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
        self._http_verify = _http_verify_setting()
        self._auth_api_url = gw_config.AUTH_API_URL

    @staticmethod
    def _trusted_proxy_peer(request: Request) -> bool:
        if not gw_config.TRUST_PROXY_HEADERS:
            return False
        peer = request.client.host if request.client else ""
        if not peer:
            return False
        try:
            peer_ip = ip_address(peer)
        except ValueError:
            return False
        if not gw_config.TRUSTED_PROXY_CIDRS:
            return True
        for cidr in gw_config.TRUSTED_PROXY_CIDRS:
            try:
                if peer_ip in ip_network(cidr, strict=False):
                    return True
            except ValueError:
                continue
        return False

    @classmethod
    def _client_ip(cls, request: Request) -> str:
        if cls._trusted_proxy_peer(request):
            xff = request.headers.get("x-forwarded-for")
            if xff:
                first = xff.split(",", 1)[0].strip()
                if first:
                    return first
            x_real_ip = request.headers.get("x-real-ip", "").strip()
            if x_real_ip:
                return x_real_ip
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
        except ValueError as exc:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid client IP") from exc

        if not any(addr in net for net in self._networks):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Source IP not allowed")

    def enforce_rate_limit(self, request: Request) -> None:
        self._rate_limiter.enforce(self._client_ip(request))

    @staticmethod
    def _auth_request_headers(token: str | None = None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if gw_config.INTERNAL_SERVICE_TOKEN:
            headers["X-Internal-Token"] = gw_config.INTERNAL_SERVICE_TOKEN
        if token is not None:
            headers["X-OTLP-Token"] = token
            headers["Content-Type"] = "application/json"
        return headers

    @staticmethod
    def _extract_org_id(response: httpx.Response) -> Optional[str]:
        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        org_id = payload.get("org_id")
        return str(org_id).strip() if org_id else None

    def _fetch_org_from_api(self, token: str) -> Optional[str]:
        if not token:
            return None
        url = self._auth_api_url
        headers = self._auth_request_headers(token)
        try:
            with httpx.Client(timeout=2.0, verify=self._http_verify) as client:
                resp = client.post(url, headers=headers, json={"token": token})
            if resp.status_code == 200:
                return self._extract_org_id(resp)
            if resp.status_code == 404:
                return None
            if resp.status_code in {405}:
                return self._fetch_org_from_api_legacy_query(token)
            raise DatabaseUnavailable(f"unexpected status {resp.status_code}")
        except httpx.HTTPError as exc:
            logger.warning("Auth API HTTP transport failure: %s", type(exc).__name__)
            raise DatabaseUnavailable from exc

    def _fetch_org_from_api_legacy_query(self, token: str) -> Optional[str]:
        legacy_url = f"{self._auth_api_url}?token={quote(token)}"
        headers = self._auth_request_headers()
        try:
            with httpx.Client(timeout=2.0, verify=self._http_verify) as client:
                resp = client.get(legacy_url, headers=headers)
            if resp.status_code == 200:
                return self._extract_org_id(resp)
            if resp.status_code in {404, 410}:
                return None
            raise DatabaseUnavailable(f"unexpected status {resp.status_code}")
        except httpx.HTTPError as exc:
            logger.warning("Auth API legacy HTTP failure: %s", type(exc).__name__)
            raise DatabaseUnavailable from exc

    def probe_auth_api(self, token: str) -> Optional[str]:
        return self._fetch_org_from_api(token)

    def validate_otlp_token(self, token: str) -> Optional[str]:
        if not token:
            return None

        hit, cached = self._token_cache.get(token)
        if hit:
            return cached

        try:
            logger.info("Token cache miss for token: %s", token[:4] + "..." if len(token) > 7 else token)
            org = self._fetch_org_from_api(token)
        except DatabaseUnavailable:
            raise
        except Exception as exc:
            # Module reloads in tests can produce another DatabaseUnavailable class identity.
            if type(exc).__name__ == "DatabaseUnavailable":
                raise exc
            logger.warning("Auth API fetch unexpected error", exc_info=True)
            raise DatabaseUnavailable from exc

        self._token_cache.set(token, org)
        return org

    def health(self) -> dict[str, str]:
        return {"status": "healthy", "service": "gateway-auth-service"}
