"""
Proxy client for forwarding Resolver API calls through Watchdog.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Dict, Optional, TypeAlias
import httpx
from fastapi import HTTPException, status
from config import config
from models.access.auth_models import TokenData
from custom_types.json import JSONDict, JSONValue, is_json_value
from services.common.ttl_cache import TTLCache
from services.proxy.base_proxy import BaseProxyService
from middleware.resilience import with_retry, with_timeout

QueryParamValue: TypeAlias = str | int | float | bool
QueryParams: TypeAlias = dict[str, QueryParamValue]


class ResolverProxyService(BaseProxyService):
    _resource_type = "resolver_proxy"

    def __init__(self) -> None:
        super().__init__(
            base_url=config.RESOLVER_URL,
            timeout=float(config.RESOLVER_TIMEOUT_SECONDS),
            tls_enabled=bool(config.RESOLVER_TLS_ENABLED),
            ca_cert_path=config.RESOLVER_CA_CERT_PATH,
        )
        self._cache_ttl_seconds = max(
            0, int(getattr(config, "RESOLVER_PROXY_CACHE_TTL_SECONDS", 15))
        )
        self._read_cache = TTLCache()
        self._read_inflight: Dict[str, asyncio.Future[JSONValue]] = {}
        self._read_inflight_lock = asyncio.Lock()

    @staticmethod
    def _is_volatile_read(upstream_path: str) -> bool:
        return (
            upstream_path.startswith("/api/v1/jobs")
            or upstream_path.startswith("/api/v1/reports")
        )

    def _resolve_cache_ttl(
        self,
        *,
        method: str,
        upstream_path: str,
        cache_ttl_seconds: Optional[int],
    ) -> int:
        configured_cache_ttl = (
            self._cache_ttl_seconds
            if cache_ttl_seconds is None
            else max(0, int(cache_ttl_seconds))
        )
        if method.upper() == "GET" and self._is_volatile_read(upstream_path):
            return 0
        return configured_cache_ttl

    @staticmethod
    def _cache_key(
        *,
        method: str,
        upstream_path: str,
        tenant_id: str,
        params: Optional[QueryParams],
        payload: Optional[JSONDict],
    ) -> str:
        return json.dumps(
            {
                "m": method.upper(),
                "p": upstream_path,
                "t": tenant_id,
                "q": params or {},
                "b": payload or {},
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def _sign_context_token(self, *, current_user: TokenData, tenant_id: str) -> str:
        key = config.get_secret("RESOLVER_CONTEXT_SIGNING_KEY")
        if not key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Missing Resolver signing key",
            )
        claims = self._build_base_jwt_claims(
            current_user=current_user,
            tenant_id=tenant_id,
            issuer=config.RESOLVER_CONTEXT_ISSUER,
            audience=config.RESOLVER_CONTEXT_AUDIENCE,
            ttl_seconds=int(config.RESOLVER_CONTEXT_TTL_SECONDS),
        )
        return self._encode_jwt(
            claims,
            key,
            str(config.RESOLVER_CONTEXT_ALGORITHM or "HS256").strip(),
        )

    def _resolve_inflight_error(
        self,
        owner: bool,
        future: Optional[asyncio.Future[JSONValue]],
        exc: HTTPException,
    ) -> None:
        if owner and future is not None and not future.done():
            future.set_exception(exc)
            _ = future.exception()

    @with_retry()
    @with_timeout()
    async def request_json(
        self,
        *,
        method: str,
        upstream_path: str,
        current_user: TokenData,
        tenant_id: str,
        payload: Optional[JSONDict] = None,
        params: Optional[QueryParams] = None,
        audit_action: str = "resolver.proxy",
        correlation_id: Optional[str] = None,
        cache_ttl_seconds: Optional[int] = None,
    ) -> JSONValue:
        service_token = config.get_secret("RESOLVER_SERVICE_TOKEN")
        if not service_token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Resolver service token not configured",
            )

        method_upper = method.upper()
        effective_cache_ttl = self._resolve_cache_ttl(
            method=method_upper,
            upstream_path=upstream_path,
            cache_ttl_seconds=cache_ttl_seconds,
        )
        cache_key: Optional[str] = None
        inflight_future: Optional[asyncio.Future[JSONValue]] = None
        owner = False

        if method_upper == "GET" and effective_cache_ttl > 0:
            cache_key = self._cache_key(
                method=method_upper,
                upstream_path=upstream_path,
                tenant_id=tenant_id,
                params=params,
                payload=payload,
            )
            cached = await self._read_cache.get(cache_key)
            if cached is not None:
                return cached
            async with self._read_inflight_lock:
                cached = await self._read_cache.get(cache_key)
                if cached is not None:
                    return cached
                inflight_future = self._read_inflight.get(cache_key)
                if inflight_future is None:
                    inflight_future = asyncio.get_running_loop().create_future()
                    self._read_inflight[cache_key] = inflight_future
                    owner = True
            if not owner:
                return await inflight_future

        context_token = self._sign_context_token(
            current_user=current_user, tenant_id=tenant_id
        )
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
                method=method_upper,
                url=target,
                headers=headers,
                params=params or None,
                json=payload if payload is not None else None,
            )
        except httpx.TimeoutException as exc:
            err = HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Resolver request timed out",
            )
            self._resolve_inflight_error(owner, inflight_future, err)
            self.write_audit(
                current_user=current_user,
                action=f"{audit_action}.timeout",
                resource_id=upstream_path,
                details={
                    "correlation_id": corr,
                    "timeout": self.timeout,
                    "method": method_upper,
                },
            )
            raise err from exc
        except Exception as exc:
            err = HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to contact Resolver",
            )
            self._resolve_inflight_error(owner, inflight_future, err)
            self.write_audit(
                current_user=current_user,
                action=f"{audit_action}.error",
                resource_id=upstream_path,
                details={
                    "correlation_id": corr,
                    "error": type(exc).__name__,
                    "method": method_upper,
                },
            )
            raise err from exc

        elapsed_ms = int((time.time() - started) * 1000)
        self.write_audit(
            current_user=current_user,
            action=f"{audit_action}.complete",
            resource_id=upstream_path,
            details={
                "correlation_id": corr,
                "status_code": response.status_code,
                "latency_ms": elapsed_ms,
                "method": method_upper,
            },
        )

        if response.status_code >= 400:
            detail = self._extract_error_detail(response)
            err = HTTPException(status_code=response.status_code, detail=detail)
            self._resolve_inflight_error(owner, inflight_future, err)
            raise err

        try:
            result = response.json()
            if not is_json_value(result):
                raise ValueError("Resolver returned non-JSON data")
            if cache_key:
                await self._read_cache.set(cache_key, result, effective_cache_ttl)
            if owner and inflight_future is not None and not inflight_future.done():
                inflight_future.set_result(result)
            return result
        except ValueError as exc:
            err = HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Resolver returned invalid JSON",
            )
            self._resolve_inflight_error(owner, inflight_future, err)
            raise err from exc
        finally:
            if owner and cache_key:
                async with self._read_inflight_lock:
                    self._read_inflight.pop(cache_key, None)

resolver_proxy_service = ResolverProxyService()
