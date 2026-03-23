"""
Runtime quota probing for native and Prometheus sources.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, cast
import time

from .parsing import (
    extract_from_text,
    extract_nested_numeric,
    extract_path,
    extract_prom_result,
    extract_tenant_scoped_numeric,
    format_with_tenant,
    prom_query_url,
    response_payload,
)


ConfigGetter = Callable[[], Any]
HttpxGetter = Callable[[], Any]


@dataclass
class QuotaProbe:
    source: str
    limit: Optional[float]
    used: Optional[float]
    message: Optional[str] = None

    def complete(self) -> bool:
        return self.limit is not None and self.used is not None

    def any_value(self) -> bool:
        return self.limit is not None or self.used is not None


class RuntimeQuotaProbe:
    def __init__(self, *, config_getter: ConfigGetter, httpx_getter: HttpxGetter) -> None:
        self._get_config = config_getter
        self._get_httpx = httpx_getter

    def _error_types(self) -> tuple[type[BaseException], ...]:
        httpx_module = self._get_httpx()
        return cast(
            tuple[type[BaseException], ...],
            (httpx_module.HTTPError, ValueError, TypeError),
        )

    def loki_limit_from_payload(
        self,
        payload: object,
        configured_path: str,
        tenant_id: str,
    ) -> Optional[float]:
        configured = extract_path(payload, configured_path)
        if configured is not None:
            return configured

        tenant_scoped = extract_tenant_scoped_numeric(
            payload,
            tenant_id=tenant_id,
            key_candidates=[
                "max_streams_per_user",
                "max_global_streams_per_user",
                "ingestion_rate_mb",
            ],
        )
        if tenant_scoped is not None:
            return tenant_scoped

        if isinstance(payload, dict):
            raw = str(payload.get("__raw_text") or "")
            if raw:
                for key in (
                    "max_streams_per_user",
                    "max_global_streams_per_user",
                    "ingestion_rate_mb",
                ):
                    parsed = extract_from_text(raw, key)
                    if parsed is not None:
                        return parsed

        return extract_nested_numeric(
            payload,
            [
                "limits_config.max_streams_per_user",
                "limits_config.max_global_streams_per_user",
                "limits_config.ingestion_rate_mb",
                "max_streams_per_user",
                "max_global_streams_per_user",
                "ingestion_rate_mb",
                "data.max_streams_per_user",
                "data.max_global_streams_per_user",
                "data.ingestion_rate_mb",
                "limits.max_streams_per_user",
                "limits.max_global_streams_per_user",
                "ingestion_limits.max_streams_per_user",
                "ingestion_limits.max_global_streams_per_user",
            ],
        )

    def tempo_limit_from_payload(
        self,
        payload: object,
        configured_path: str,
        tenant_id: str,
    ) -> Optional[float]:
        configured = extract_path(payload, configured_path)
        if configured is not None:
            return configured

        tenant_scoped = extract_tenant_scoped_numeric(
            payload,
            tenant_id=tenant_id,
            key_candidates=[
                "max_traces_per_user",
                "max_bytes_per_trace",
                "ingestion_rate_limit_bytes",
            ],
        )
        if tenant_scoped is not None:
            return tenant_scoped

        if isinstance(payload, dict):
            raw = str(payload.get("__raw_text") or "")
            if raw:
                for key in (
                    "max_traces_per_user",
                    "max_bytes_per_trace",
                    "ingestion_rate_limit_bytes",
                ):
                    parsed = extract_from_text(raw, key)
                    if parsed is not None:
                        return parsed

        return extract_nested_numeric(
            payload,
            [
                "limits.max_traces_per_user",
                "limits.max_bytes_per_trace",
                "limits.ingestion_rate_limit_bytes",
                "max_traces_per_user",
                "max_bytes_per_trace",
                "ingestion_rate_limit_bytes",
                "defaults.max_traces_per_user",
                "defaults.max_bytes_per_trace",
                "defaults.ingestion_rate_limit_bytes",
                "overrides.max_traces_per_user",
                "overrides.max_bytes_per_trace",
                "overrides.ingestion_rate_limit_bytes",
                "runtime_config.overrides.max_traces_per_user",
                "runtime_config.overrides.max_bytes_per_trace",
                "runtime_config.overrides.ingestion_rate_limit_bytes",
            ],
        )

    def loki_used_from_payload(
        self,
        payload: object,
        configured_path: str,
        tenant_id: str,
    ) -> Optional[float]:
        configured = extract_path(payload, configured_path)
        if configured is not None:
            return configured

        tenant_scoped = extract_tenant_scoped_numeric(
            payload,
            tenant_id=tenant_id,
            key_candidates=[
                "streams",
                "active_streams",
                "streams_in_use",
                "current_streams",
            ],
        )
        if tenant_scoped is not None:
            return tenant_scoped

        return extract_nested_numeric(
            payload,
            [
                "streams",
                "active_streams",
                "streams_in_use",
                "current_streams",
                "data.streams",
                "stats.streams",
                "limits.current_streams",
                "usage.streams",
                "overrides.streams",
            ],
        )

    def tempo_used_from_payload(
        self,
        payload: object,
        configured_path: str,
        tenant_id: str,
    ) -> Optional[float]:
        configured = extract_path(payload, configured_path)
        if configured is not None:
            return configured

        tenant_scoped = extract_tenant_scoped_numeric(
            payload,
            tenant_id=tenant_id,
            key_candidates=[
                "active_traces",
                "traces_active",
                "current_traces",
                "traces_in_use",
            ],
        )
        if tenant_scoped is not None:
            return tenant_scoped

        return extract_nested_numeric(
            payload,
            [
                "active_traces",
                "traces_active",
                "current_traces",
                "traces_in_use",
                "usage.active_traces",
                "usage.current_traces",
                "data.active_traces",
                "stats.active_traces",
            ],
        )

    async def fetch_loki_used_streams(self, *, tenant_id: str) -> Optional[float]:
        cfg = self._get_config()
        httpx_module = self._get_httpx()
        end_ns = int(time.time() * 1_000_000_000)
        start_ns = end_ns - int(cfg.QUOTA_USAGE_WINDOW_SECONDS) * 1_000_000_000
        async with httpx_module.AsyncClient(
            timeout=float(cfg.QUOTA_NATIVE_TIMEOUT_SECONDS)
        ) as client:
            series_resp = await client.get(
                f"{cfg.LOKI_URL.rstrip('/')}/loki/api/v1/series",
                headers={"X-Scope-OrgID": tenant_id},
                params={"match[]": "{}", "start": str(start_ns), "end": str(end_ns)},
            )
            series_resp.raise_for_status()
            payload = response_payload(series_resp)
            if isinstance(payload, dict):
                data = payload.get("data")
                if isinstance(data, list):
                    return float(len(data))

            stats_resp = await client.get(
                f"{cfg.LOKI_URL.rstrip('/')}/loki/api/v1/index/stats",
                headers={"X-Scope-OrgID": tenant_id},
                params={"query": "{}", "start": str(start_ns), "end": str(end_ns)},
            )
            stats_resp.raise_for_status()
            stats_payload = response_payload(stats_resp)
            streams = extract_nested_numeric(
                stats_payload,
                ["streams", "data.streams", "stats.streams"],
            )
            if streams is not None:
                return streams
        return None

    async def fetch_tempo_used_traces(self, *, tenant_id: str) -> Optional[float]:
        cfg = self._get_config()
        httpx_module = self._get_httpx()
        end_us = int(time.time() * 1_000_000)
        start_us = end_us - int(cfg.QUOTA_USAGE_WINDOW_SECONDS) * 1_000_000
        async with httpx_module.AsyncClient(
            timeout=float(cfg.QUOTA_NATIVE_TIMEOUT_SECONDS)
        ) as client:
            try:
                response = await client.get(
                    f"{cfg.TEMPO_URL.rstrip('/')}/api/search",
                    headers={"X-Scope-OrgID": tenant_id},
                    params={"start": str(start_us), "end": str(end_us), "limit": "1000"},
                )
                response.raise_for_status()
                payload = response_payload(response)
                traces = payload.get("traces") if isinstance(payload, dict) else None
                if isinstance(traces, list):
                    return float(len(traces))
            except self._error_types():
                pass

            try:
                end_s = int(time.time())
                start_s = end_s - int(cfg.QUOTA_USAGE_WINDOW_SECONDS)
                response_s = await client.get(
                    f"{cfg.TEMPO_URL.rstrip('/')}/api/search",
                    headers={"X-Scope-OrgID": tenant_id},
                    params={"start": str(start_s), "end": str(end_s), "limit": "1000"},
                )
                response_s.raise_for_status()
                payload_s = response_payload(response_s)
                traces_s = payload_s.get("traces") if isinstance(payload_s, dict) else None
                if isinstance(traces_s, list):
                    return float(len(traces_s))
            except self._error_types():
                pass

            for usage_path in ("/status/usage", "/api/status/usage"):
                try:
                    usage_resp = await client.get(
                        f"{cfg.TEMPO_URL.rstrip('/')}{usage_path}",
                        headers={"X-Scope-OrgID": tenant_id},
                    )
                    usage_resp.raise_for_status()
                    usage_payload = response_payload(usage_resp)
                    usage_val = extract_nested_numeric(
                        usage_payload,
                        [
                            "active_traces",
                            "traces_active",
                            "current_traces",
                            "traces_in_use",
                            "usage.active_traces",
                            "usage.traces_active",
                            "data.active_traces",
                        ],
                    )
                    if usage_val is not None:
                        return usage_val
                except self._error_types():
                    continue
        return None

    def candidate_native_paths(
        self,
        *,
        service_name: str,
        configured_path: str,
    ) -> list[str]:
        candidates: list[str] = []
        if configured_path:
            candidates.append(configured_path)
        if service_name == "loki":
            candidates.extend(
                [
                    "/loki/api/v1/status/limits",
                    "/loki/api/v1/status/config",
                    "/config",
                ]
            )
        elif service_name == "tempo":
            candidates.extend(
                [
                    "/status/overrides",
                    "/api/status/overrides",
                    "/status/config",
                    "/api/status/config",
                ]
            )
        return list(dict.fromkeys(candidates))

    async def fetch_native_quota(
        self,
        *,
        service_name: str,
        base_url: str,
        path_template: str,
        tenant_id: str,
        limit_field: str,
        used_field: str,
    ) -> QuotaProbe:
        cfg = self._get_config()
        httpx_module = self._get_httpx()

        if not cfg.QUOTA_NATIVE_ENABLED:
            return QuotaProbe(source="none", limit=None, used=None, message=None)

        candidate_paths = self.candidate_native_paths(
            service_name=service_name,
            configured_path=path_template,
        )
        if not candidate_paths:
            return QuotaProbe(source="none", limit=None, used=None, message=None)

        last_error: Optional[str] = None
        collected_limit: Optional[float] = None
        collected_used: Optional[float] = None

        for candidate_path in candidate_paths:
            target = (
                f"{base_url.rstrip('/')}/"
                f"{format_with_tenant(candidate_path, tenant_id).lstrip('/')}"
            )
            try:
                async with httpx_module.AsyncClient(
                    timeout=float(cfg.QUOTA_NATIVE_TIMEOUT_SECONDS)
                ) as client:
                    response = await client.get(
                        target,
                        headers={"X-Scope-OrgID": tenant_id},
                    )
                    response.raise_for_status()
                    payload = response_payload(response)

                if service_name == "loki":
                    limit = self.loki_limit_from_payload(payload, limit_field, tenant_id)
                    used = self.loki_used_from_payload(payload, used_field, tenant_id)
                    if used is None:
                        try:
                            used = await self.fetch_loki_used_streams(tenant_id=tenant_id)
                        except self._error_types():
                            used = None
                elif service_name == "tempo":
                    limit = self.tempo_limit_from_payload(payload, limit_field, tenant_id)
                    used = self.tempo_used_from_payload(payload, used_field, tenant_id)
                    if used is None:
                        try:
                            used = await self.fetch_tempo_used_traces(tenant_id=tenant_id)
                        except self._error_types():
                            used = None
                else:
                    limit = extract_path(payload, limit_field)
                    used = extract_path(payload, used_field)

                if collected_limit is None and limit is not None:
                    collected_limit = limit
                if collected_used is None and used is not None:
                    collected_used = used

                if collected_limit is not None and collected_used is not None:
                    return QuotaProbe(
                        source="native",
                        limit=collected_limit,
                        used=collected_used,
                        message=None,
                    )
            except self._error_types() as exc:
                last_error = type(exc).__name__

        if collected_limit is not None or collected_used is not None:
            return QuotaProbe(
                source="native",
                limit=collected_limit,
                used=collected_used,
                message=None,
            )

        return QuotaProbe(
            source="native",
            limit=None,
            used=None,
            message=(
                f"{service_name.capitalize()} runtime quota endpoint unavailable"
                if last_error
                else None
            ),
        )

    async def query_prometheus_value(
        self,
        query_template: str,
        tenant_id: str,
    ) -> Optional[float]:
        cfg = self._get_config()
        httpx_module = self._get_httpx()

        query_url = prom_query_url(cfg)
        if not query_url or not query_template:
            return None

        query = format_with_tenant(query_template, tenant_id)
        async with httpx_module.AsyncClient(
            timeout=float(cfg.QUOTA_PROMETHEUS_TIMEOUT_SECONDS)
        ) as client:
            response = await client.get(
                query_url,
                params={"query": query},
                headers={"X-Scope-OrgID": tenant_id},
            )
            response.raise_for_status()
            payload = response.json()
        return extract_prom_result(payload)

    async def fetch_prometheus_quota(
        self,
        *,
        service_name: str,
        tenant_id: str,
        limit_query: str,
        used_query: str,
    ) -> QuotaProbe:
        cfg = self._get_config()
        if not cfg.QUOTA_PROMETHEUS_ENABLED:
            return QuotaProbe(source="none", limit=None, used=None, message=None)
        if not prom_query_url(cfg):
            return QuotaProbe(source="none", limit=None, used=None, message=None)
        if not limit_query and not used_query:
            return QuotaProbe(source="none", limit=None, used=None, message=None)

        try:
            limit = (
                await self.query_prometheus_value(limit_query, tenant_id)
                if limit_query
                else None
            )
            used = (
                await self.query_prometheus_value(used_query, tenant_id)
                if used_query
                else None
            )
            return QuotaProbe(source="prometheus", limit=limit, used=used, message=None)
        except self._error_types():
            return QuotaProbe(
                source="prometheus",
                limit=None,
                used=None,
                message=f"{service_name.capitalize()} quota fallback unavailable",
            )
