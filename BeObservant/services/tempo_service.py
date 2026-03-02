"""
Service for managing Tempo integration, providing functions to query and retrieve trace data
from Tempo based on trace ID, service name, and time range.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

import httpx

from config import config
from middleware.resilience import with_retry, with_timeout
from models.observability.tempo_models import Trace, TraceQuery, TraceResponse
from services.common.http_client import create_async_client
from services.common.ttl_cache import TTLCache
from services.tempo import params as tempo_params
from services.tempo import parsers as tempo_parsers

logger = logging.getLogger(__name__)

SERVICE_NAME_KEY = "service.name"
SERVICE_ALIAS_KEY = "service"
SERVICE_KEYS = {SERVICE_NAME_KEY, SERVICE_ALIAS_KEY}


def _escape_traceql(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


class TempoService:
    def __init__(self, tempo_url: str = config.TEMPO_URL):
        self.tempo_url = tempo_url.rstrip("/")
        self._client = create_async_client(config.DEFAULT_TIMEOUT)
        self._cache_ttl_seconds = max(1, int(config.SERVICE_CACHE_TTL_SECONDS))
        self._services_cache = TTLCache()
        self._metrics: Dict[str, float] = defaultdict(float)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _observe(self, metric: str, value: float = 1.0) -> None:
        self._metrics[metric] += value

    def _get_headers(self, tenant_id: str = config.DEFAULT_ORG_ID) -> Dict[str, str]:
        return {"X-Scope-OrgID": tenant_id}

    async def _get_json(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            response = await self._client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception:
            self._observe("tempo_search_errors_total")
            raise
        finally:
            self._observe("tempo_search_total")
            self._observe("tempo_search_duration_sum_seconds", time.perf_counter() - started)

    # --- Public API ---

    @with_retry()
    @with_timeout()
    async def search_traces(
        self,
        query: TraceQuery,
        tenant_id: str = config.DEFAULT_ORG_ID,
        fetch_full_traces: bool = True,
    ) -> TraceResponse:
        params = tempo_params.build_search_params(query)
        headers = self._get_headers(tenant_id)
        try:
            data = await self._get_json(f"{self.tempo_url}/api/search", params=params, headers=headers)
            raw_traces = data.get("traces", [])

            if fetch_full_traces:
                semaphore = asyncio.Semaphore(max(1, config.TEMPO_TRACE_FETCH_CONCURRENCY))

                async def _fetch_one(trace_id: str) -> Trace:
                    async with semaphore:
                        self._observe("tempo_full_trace_fetch_total")
                        try:
                            return await self.get_trace(trace_id, tenant_id=tenant_id) or Trace(
                                traceID=trace_id,
                                spans=[],
                                processes={},
                                warnings=["Trace details unavailable"],
                            )
                        except Exception:
                            logger.warning("Failed to fetch trace %s", trace_id)
                            return Trace(
                                traceID=trace_id,
                                spans=[],
                                processes={},
                                warnings=["Trace details unavailable"],
                            )

                traces = list(await asyncio.gather(
                    *[_fetch_one(t["traceID"]) for t in raw_traces if t.get("traceID")],
                ))
            else:
                traces = [t for t in (tempo_parsers.build_summary_trace(r) for r in raw_traces) if t]

            return TraceResponse.model_validate({
                "data": traces,
                "total": len(traces),
                "limit": query.limit,
                "offset": 0,
            })
        except httpx.HTTPError as e:
            logger.error("Error searching traces: %s", e)
            return TraceResponse.model_validate({
                "data": [],
                "total": 0,
                "limit": query.limit,
                "errors": [str(e)],
                "offset": 0,
            })

    @with_retry()
    @with_timeout()
    async def get_trace(self, trace_id: str, tenant_id: str = config.DEFAULT_ORG_ID) -> Optional[Trace]:
        headers = self._get_headers(tenant_id)
        try:
            response = await self._client.get(
                f"{self.tempo_url}/api/traces/{trace_id}", headers=headers
            )
            response.raise_for_status()
            if not response.content:
                return None
            try:
                data = response.json()
            except json.JSONDecodeError:
                logger.debug("Non-JSON response for trace %s", trace_id)
                return None
            return tempo_parsers.parse_tempo_trace(trace_id, data) if "batches" in data else None
        except httpx.HTTPError as e:
            logger.error("Error fetching trace %s: %s", trace_id, e)
            return None

    @with_retry()
    @with_timeout()
    async def get_services(self, tenant_id: str = config.DEFAULT_ORG_ID) -> List[str]:
        async def _fetch() -> Optional[List[str]]:
            headers = self._get_headers(tenant_id)
            try:
                data = await self._get_json(f"{self.tempo_url}/api/search/tags", headers=headers)
                logger.debug("Tempo /api/search/tags response: %s", data)

                tag_names: List[str] = []
                if isinstance(data, dict):
                    tag_names = (
                        data.get("tagNames")
                        or (data.get("data") or {}).get("tagNames")
                        or []
                    )
                elif isinstance(data, list):
                    tag_names = [item.get("tagName") for item in data if isinstance(item, dict)]

                services: List[str] = []
                for tag in tag_names:
                    if tag not in SERVICE_KEYS:
                        continue
                    try:
                        resp = await self._client.get(
                            f"{self.tempo_url}/api/search/tag/{tag}/values", headers=headers
                        )
                        resp.raise_for_status()
                        vd = resp.json()
                        raw_values: List[Any] = []
                        if isinstance(vd, dict):
                            raw_values = vd.get("tagValues") or vd.get("values") or vd.get("data") or []
                        elif isinstance(vd, list):
                            raw_values = vd
                        for v in raw_values:
                            if isinstance(v, dict):
                                val = v.get("value") or v.get("tagValue")
                                if val:
                                    services.append(str(val))
                            elif v:
                                services.append(str(v))
                    except httpx.HTTPError as e:
                        logger.warning("Failed to fetch tag values for %s: %s", tag, e)

                if not services:
                    logger.debug("No services from tags, inferring from recent traces")
                    try:
                        resp = await self.search_traces(
                            TraceQuery.model_validate({"limit": 50}),
                            tenant_id=tenant_id,
                            fetch_full_traces=False,
                        )
                        services = [
                            span.service_name
                            for trace in resp.data
                            for span in trace.spans
                            if span.service_name
                        ]
                    except Exception as e:
                        logger.warning("Failed to infer services from traces: %s", e)

                return sorted(set(filter(None, services))) or None
            except httpx.HTTPError as e:
                logger.error("Error fetching services: %s", e)
                return None

        result = await self._services_cache.get_or_set(tenant_id, _fetch, self._cache_ttl_seconds)
        return list(result) if result else []

    @with_retry()
    @with_timeout()
    async def get_operations(self, service: str, tenant_id: str = config.DEFAULT_ORG_ID) -> List[str]:
        headers = self._get_headers(tenant_id)
        svc_escaped = _escape_traceql(service)
        for tag in ("span.name", "name"):
            try:
                resp = await self._client.get(
                    f"{self.tempo_url}/api/search/tag/{tag}/values",
                    params={"q": f'{{service.name="{svc_escaped}"}}'},
                    headers=headers,
                )
                resp.raise_for_status()
                vd = resp.json()
                values: List[str] = []
                if isinstance(vd, dict):
                    values = vd.get("tagValues") or vd.get("values") or vd.get("data") or []
                elif isinstance(vd, list):
                    values = vd
                if values:
                    return sorted(set(filter(None, map(str, values))))
            except httpx.HTTPError:
                logger.debug("Tag values lookup failed for %s, trying next", tag)

        logger.debug("Falling back to trace search for operations of %s", service)
        try:
            response = await self.search_traces(
                TraceQuery.model_validate({"service": service, "limit": 50}),
                tenant_id=tenant_id,
                fetch_full_traces=False,
            )
            return sorted({span.operation_name for trace in response.data for span in trace.spans})
        except Exception as e:
            logger.warning("Failed to fetch operations for %s: %s", service, e)
            return []