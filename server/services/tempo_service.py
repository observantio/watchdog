"""
Service for managing trace Tempo integration, providing functions to query and retrieve trace data from Tempo based on various parameters such as trace ID, service name, and time range. This module includes logic to construct appropriate queries for Tempo, to handle responses from Tempo, and to implement retry mechanisms for failed requests. The service also includes functionality to normalize and process trace data for use within the application.
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from config import config
from middleware.resilience import with_retry, with_timeout
from models.observability.tempo_models import Span, Trace, TraceQuery, TraceResponse
from services.common.http_client import create_async_client
from services.common.ttl_cache import TTLCache

from services.tempo import parsers as tempo_parsers
from services.tempo import promql as tempo_promql
from services.tempo import metrics as tempo_metrics
from services.tempo import params as tempo_params

logger = logging.getLogger(__name__)

_SERVICE_NAME_KEY = "service.name"
_SERVICE_ALIAS_KEY = "service"
_SERVICE_KEYS = {_SERVICE_NAME_KEY, _SERVICE_ALIAS_KEY}
_SEARCH_LIMIT_CAP = 1000


class TempoService:
    def __init__(self, tempo_url: str = config.TEMPO_URL):
        self.tempo_url = tempo_url.rstrip("/")
        self.timeout = config.DEFAULT_TIMEOUT
        self._client = create_async_client(self.timeout)
        self._cache_ttl_seconds = max(1, int(config.SERVICE_CACHE_TTL_SECONDS))
        self._services_cache = TTLCache()
        self._volume_cache = TTLCache()
        self._metrics_enabled = True
        self._metrics: Dict[str, float] = {
            "tempo_search_total": 0,
            "tempo_search_duration_sum_seconds": 0.0,
            "tempo_search_errors_total": 0,
            "tempo_full_trace_fetch_total": 0,
            "tempo_count_traces_calls_total": 0,
            "tempo_metrics_queries_total": 0,
            "tempo_metrics_query_errors_total": 0,
        }

    def _observe(self, metric: str, value: float = 1.0) -> None:
        self._metrics[metric] = self._metrics[metric] + value

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

    async def _query_metrics_range(
        self,
        promql: str,
        start_us: Optional[int],
        end_us: Optional[int],
        step_s: int = 300,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> Dict[str, Any]:
        result, metrics_enabled = await tempo_metrics.query_metrics_range(
            client=self._client,
            promql=promql,
            start_us=start_us,
            end_us=end_us,
            step_s=step_s,
            tenant_id=tenant_id,
            tempo_url=self.tempo_url,
            mimir_url=config.MIMIR_URL,
            get_headers=self._get_headers,
            observe=self._observe,
            metrics_enabled=self._metrics_enabled,
        )
        self._metrics_enabled = metrics_enabled
        return result

    # --- Delegation helpers ---

    def _build_promql_selector(self, service: Optional[str]) -> List[str]:
        return tempo_promql.build_promql_selector(service)

    def _build_count_promql(self, service: Optional[str], range_s: int) -> str:
        return tempo_promql.build_count_promql(service, range_s)

    def _extract_metric_values(self, metrics_resp: Dict[str, Any]) -> List[List[Any]]:
        return tempo_metrics.extract_metric_values(metrics_resp)

    def _parse_span(
        self,
        span_data: Dict[str, Any],
        trace_id: str,
        process_id: str,
        service_name: Optional[str],
        resource_attrs: Optional[Dict[str, Any]] = None,
    ) -> Span:
        return tempo_parsers.parse_span(span_data, trace_id, process_id, service_name, resource_attrs)

    def _parse_tempo_trace(self, trace_id: str, data: Dict[str, Any]) -> Trace:
        return tempo_parsers.parse_tempo_trace(trace_id, data)

    def _build_search_params(self, query: TraceQuery) -> Dict[str, Any]:
        return tempo_params.build_search_params(query)

    def _build_summary_trace(self, trace_data: Dict[str, Any]) -> Optional[Trace]:
        return tempo_parsers.build_summary_trace(trace_data)

    # --- Public API ---

    @with_retry()
    @with_timeout()
    async def search_traces(
        self,
        query: TraceQuery,
        tenant_id: str = config.DEFAULT_ORG_ID,
        fetch_full_traces: bool = True,
    ) -> TraceResponse:
        params = self._build_search_params(query)
        headers = self._get_headers(tenant_id)
        try:
            data = await self._get_json(f"{self.tempo_url}/api/search", params=params, headers=headers)
            raw_traces = data.get("traces", [])

            if fetch_full_traces:
                semaphore = asyncio.Semaphore(max(1, config.TEMPO_TRACE_FETCH_CONCURRENCY))

                async def _fetch_one(trace_id: str) -> Trace:
                    async with semaphore:
                        self._observe("tempo_full_trace_fetch_total")
                        return await self.get_trace(trace_id, tenant_id=tenant_id) or Trace(
                            traceID=trace_id,
                            spans=[],
                            processes={},
                            warnings=["Trace details unavailable"],
                        )

                traces = list(await asyncio.gather(
                    *[_fetch_one(t["traceID"]) for t in raw_traces if t.get("traceID")],
                    return_exceptions=False,
                ))
            else:
                traces = [t for t in (self._build_summary_trace(r) for r in raw_traces) if t]

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
            return self._parse_tempo_trace(trace_id, data) if "batches" in data else None
        except httpx.HTTPError as e:
            logger.error("Error fetching trace %s: %s", trace_id, e)
            return None

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
                    if tag not in _SERVICE_KEYS:
                        continue
                    try:
                        resp = await self._client.get(
                            f"{self.tempo_url}/api/search/tag/{tag}/values", headers=headers
                        )
                        resp.raise_for_status()
                        vd = resp.json()
                        if isinstance(vd, dict):
                            services.extend(vd.get("tagValues") or vd.get("values") or vd.get("data") or [])
                        elif isinstance(vd, list):
                            services.extend(vd)
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

                return sorted(set(filter(None, map(str, services)))) or None
            except httpx.HTTPError as e:
                logger.error("Error fetching services: %s", e)
                return None

        result = await self._services_cache.get_or_set(tenant_id, _fetch, self._cache_ttl_seconds)
        return list(result) if result else []

    async def get_operations(self, service: str, tenant_id: str = config.DEFAULT_ORG_ID) -> List[str]:
        headers = self._get_headers(tenant_id)
        for tag in ("span.name", "name"):
            try:
                resp = await self._client.get(
                    f"{self.tempo_url}/api/search/tag/{tag}/values",
                    params={"q": f'{{service.name="{service}"}}'},
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
        response = await self.search_traces(
            TraceQuery.model_validate({"service": service, "limit": 50}),
            tenant_id=tenant_id,
            fetch_full_traces=False,
        )
        return sorted({span.operation_name for trace in response.data for span in trace.spans})

    async def get_trace_metrics(
        self,
        service: Optional[str] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> Dict[str, Any]:
        query = TraceQuery.model_validate({
            "service": service,
            "start": start,
            "end": end,
            "limit": min(config.MAX_QUERY_LIMIT, _SEARCH_LIMIT_CAP),
        })
        response = await self.search_traces(query, tenant_id=tenant_id, fetch_full_traces=False)
        traces = response.data

        durations = [
            s.duration
            for t in traces
            for s in t.spans
            if s.duration is not None and not s.parent_span_id
        ]
        error_count = sum(
            1 for t in traces for s in t.spans if getattr(s, "error", False)
        )

        return {
            "total_traces": response.total,
            "total_spans": sum(len(t.spans) for t in traces),
            "error_count": error_count,
            "avg_duration_us": int(sum(durations) / len(durations)) if durations else None,
            "max_duration_us": max(durations) if durations else None,
            "min_duration_us": min(durations) if durations else None,
            "service": service,
        }

    async def get_trace_volume(
        self,
        service: Optional[str] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        step: int = 300,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> Dict[str, Any]:
        now_us = int(time.time() * 1_000_000)
        end = end or now_us
        start = start or (end - 3_600 * 1_000_000)
        step = max(1, step)

        cache_key = f"{tenant_id}:{service or '__all__'}:{start}:{end}:{step}"
        cached = await self._volume_cache.get(cache_key)
        if cached is not None:
            return cached

        start_s = start // 1_000_000
        total_s = max(0, (end - start) // 1_000_000)
        num_buckets = max(1, min(240, (total_s + step - 1) // step))
        expected_ts = [start_s + i * step for i in range(num_buckets)]

        def _empty_result() -> Dict[str, Any]:
            return {"data": {"result": [{"metric": {}, "values": [[ts, "0"] for ts in expected_ts]}]}}

        async def _cache_and_return(result: Dict[str, Any]) -> Dict[str, Any]:
            await self._volume_cache.set(cache_key, result, self._cache_ttl_seconds)
            return result

        if config.TEMPO_USE_METRICS_FOR_COUNT:
            try:
                for sel in self._build_promql_selector(service):
                    resp = await self._query_metrics_range(
                        f"sum(count_over_time({sel}[{step}s]))",
                        start, end, step, tenant_id=tenant_id,
                    )
                    raw_values = self._extract_metric_values(resp)
                    if raw_values:
                        ts_map = {int(ts): int(float(v)) for ts, v in raw_values}
                        normalized = [[ts, str(ts_map.get(ts, 0))] for ts in expected_ts]
                        result = {"data": {"result": [{"metric": {}, "values": normalized}]}}
                        return await _cache_and_return(result)
            except Exception:
                logger.debug("Metrics-based volume query failed, falling back", exc_info=True)

        try:
            metrics = await self.get_trace_metrics(service=service, start=start, end=end, tenant_id=tenant_id)
            total = int(metrics.get("total_traces") or 0)
            if total > 0:
                base, rem = divmod(total, num_buckets)
                values = [
                    [expected_ts[i], str(base + (1 if i < rem else 0))]
                    for i in range(num_buckets)
                ]
                result = {"data": {"result": [{"metric": {}, "values": values}]}}
                return await _cache_and_return(result)
        except Exception:
            logger.debug("Failed to estimate trace volume from totals", exc_info=True)

        return await _cache_and_return(_empty_result())

    async def count_traces(self, query: TraceQuery, tenant_id: str = config.DEFAULT_ORG_ID) -> int:
        if config.TEMPO_USE_METRICS_FOR_COUNT and query.start and query.end:
            try:
                duration_s = max(1, (query.end - query.start) // 1_000_000)
                for sel in self._build_promql_selector(query.service):
                    resp = await self._query_metrics_range(
                        f"sum(count_over_time({sel}[{duration_s}s]))",
                        query.start, query.end, duration_s, tenant_id=tenant_id,
                    )
                    result = (resp.get("data") or {}).get("result") if isinstance(resp, dict) else None
                    if result:
                        vals = result[0].get("values", [])
                        if vals:
                            return int(float(vals[-1][1]))
            except Exception:
                logger.debug("Metrics-based count failed, falling back", exc_info=True)

        capped = query.model_copy(update={"limit": min(query.limit, _SEARCH_LIMIT_CAP)})
        response = await self.search_traces(capped, tenant_id=tenant_id, fetch_full_traces=False)
        self._observe("tempo_count_traces_calls_total")
        return response.total