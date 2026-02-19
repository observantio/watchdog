"""
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
_SERVICE_KEYS = [_SERVICE_NAME_KEY, _SERVICE_ALIAS_KEY]
_OTLP_VALUE_TYPES = ("stringValue", "intValue", "boolValue", "doubleValue")


class TempoService:
    def __init__(self, tempo_url: str = config.TEMPO_URL):
        self.tempo_url = tempo_url.rstrip("/")
        self.timeout = config.DEFAULT_TIMEOUT
        self._client = create_async_client(self.timeout)
        self._cache_ttl_seconds = max(1, int(config.SERVICE_CACHE_TTL_SECONDS))
        # replace ad-hoc dict caches with shared async-safe TTLCache
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
        self._metrics[metric] = float(self._metrics.get(metric, 0.0) + value)

    async def _timed_get_json(
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
        finally:
            self._observe("tempo_search_total")
            self._observe("tempo_search_duration_sum_seconds", time.perf_counter() - started)

    def _get_headers(self, tenant_id: str = config.DEFAULT_ORG_ID) -> Dict[str, str]:
        return {"X-Scope-OrgID": tenant_id}

    async def _query_metrics_range(
        self,
        promql: str,
        start_us: Optional[int],
        end_us: Optional[int],
        step_s: int = 300,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> Dict[str, Any]:
        """Delegate to `services.tempo.metrics.query_metrics_range` and preserve metrics flag."""
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

    def _build_promql_selector(self, service: Optional[str]) -> List[str]:
        return tempo_promql.build_promql_selector(service)

    def _build_count_promql(self, service: Optional[str], range_s: int) -> str:
        return tempo_promql.build_count_promql(service, range_s)

    def _extract_metric_values(self, metrics_resp: Dict[str, Any]) -> List[List[Any]]:
        return tempo_metrics.extract_metric_values(metrics_resp)

    def _parse_attributes(self, attrs: List[Dict[str, Any]]) -> Dict[str, Any]:
        return tempo_parsers.parse_attributes(attrs)

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
            data = await self._timed_get_json(f"{self.tempo_url}/api/search", params=params, headers=headers)
            raw_traces = data.get("traces", [])

            if fetch_full_traces:
                semaphore = asyncio.Semaphore(max(1, config.TEMPO_TRACE_FETCH_CONCURRENCY))

                async def _fetch_full(trace_id: str) -> Trace:
                    async with semaphore:
                        self._observe("tempo_full_trace_fetch_total")
                        return await self.get_trace(trace_id, tenant_id=tenant_id) or Trace(
                            traceID=trace_id,
                            spans=[],
                            processes={},
                            warnings=["Trace details unavailable"],
                        )

                traces = await asyncio.gather(*[
                    _fetch_full(t["traceID"]) for t in raw_traces if t.get("traceID")
                ])
            else:
                traces = [t for t in map(self._build_summary_trace, raw_traces) if t]

            return TraceResponse(data=list(traces), total=len(traces), limit=query.limit, offset=0)
        except httpx.HTTPError as e:
            self._observe("tempo_search_errors_total")
            logger.error("Error searching traces: %s", e)
            return TraceResponse(data=[], total=0, limit=query.limit, errors=[str(e)])

    @with_retry()
    @with_timeout()
    async def get_trace(self, trace_id: str, tenant_id: str = config.DEFAULT_ORG_ID) -> Optional[Trace]:
        headers = self._get_headers(tenant_id)
        try:
            response = await self._client.get(f"{self.tempo_url}/api/traces/{trace_id}", headers=headers)
            response.raise_for_status()
            if not response.content:
                logger.debug("Empty response for trace %s", trace_id)
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

    @with_retry()
    @with_timeout()
    async def get_services(self, tenant_id: str = config.DEFAULT_ORG_ID) -> List[str]:
        # try fast path via TTLCache
        cached = await self._services_cache.get(tenant_id)
        if cached is not None:
            return list(cached)

        headers = self._get_headers(tenant_id)

        async def _fetch_services():
            try:
                data = await self._timed_get_json(f"{self.tempo_url}/api/search/tags", headers=headers)
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
                            services.extend(
                                vd.get("tagValues") or vd.get("values") or vd.get("data") or []
                            )
                        elif isinstance(vd, list):
                            services.extend(vd)
                    except httpx.HTTPError as e:
                        logger.warning("Failed to fetch tag values for %s: %s", tag, e)

                if not services:
                    logger.debug("No services from tags, inferring from recent traces")
                    try:
                        resp = await self.search_traces(TraceQuery(limit=50), tenant_id=tenant_id)
                        services = [
                            span.service_name
                            for trace in resp.data
                            for span in trace.spans
                            if span.service_name
                        ]
                    except Exception as e:
                        logger.warning("Failed to infer services from traces: %s", e)

                result = sorted(set(filter(None, map(str, services))))
                return result
            except httpx.HTTPError as e:
                logger.error("Error fetching services: %s", e)
                return None

        services = await self._services_cache.get_or_set(tenant_id, _fetch_services, self._cache_ttl_seconds)
        return list(services) if services else []

    async def get_operations(self, service: str, tenant_id: str = config.DEFAULT_ORG_ID) -> List[str]:
        response = await self.search_traces(TraceQuery(service=service, limit=100), tenant_id=tenant_id)
        return sorted({span.operation_name for trace in response.data for span in trace.spans})

    async def get_trace_metrics(
        self,
        service: Optional[str] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> Dict[str, Any]:
        query = TraceQuery(service=service, start=start, end=end, limit=min(config.MAX_QUERY_LIMIT, 1000))
        response = await self.search_traces(query, tenant_id=tenant_id, fetch_full_traces=False)
        return {
            "total_traces": response.total,
            "total_spans": None,
            "error_count": None,
            "avg_duration_us": None,
            "max_duration_us": None,
            "min_duration_us": None,
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
        """Return trace counts over time.

        Implementation strategy (efficient + resilient):
        - Try metrics-based query first (very cheap).
        - If metrics are unavailable, try a single aggregated count (via get_trace_metrics)
          and build an *estimated* evenly-distributed series (cheap) so the UI still
          shows meaningful data.
        - Only fall back to per-trace aggregation (expensive) when we cannot estimate.
        - Cache recent results for a short TTL to avoid repeated heavy queries.
        """
        now_us = int(time.time() * 1_000_000)
        end = end or now_us
        start = start or (end - 60 * 60 * 1_000_000)
        step = max(1, step)
        cache_key = f"{tenant_id}:{service or '__all__'}:{start}:{end}:{step}"
        cached = await self._volume_cache.get(cache_key)
        if cached is not None:
            return cached

        if config.TEMPO_USE_METRICS_FOR_COUNT:
            try:
                raw_values = self._extract_metric_values(
                    await self._query_metrics_range(
                        self._build_count_promql(service, step), start, end, step, tenant_id=tenant_id
                    )
                )
                if raw_values:
                    # Normalize into fixed buckets covering [start, end) with step seconds.
                    # Fill missing timestamps with "0" so the UI always receives a full series.
                    start_s = int(start / 1_000_000)
                    total_seconds = max(0, int((end - start) / 1_000_000))
                    num_buckets = max(1, min(240, (total_seconds + step - 1) // step))
                    expected_ts = [start_s + i * step for i in range(num_buckets)]

                    # raw_values is a list of [ts, value_str]; build a map and fill missing
                    ts_map = {int(ts): int(v) for ts, v in raw_values}
                    normalized = [[ts, str(ts_map.get(ts, 0))] for ts in expected_ts]

                    result = {"data": {"result": [{"metric": {}, "values": normalized}]}}
                    await self._volume_cache.set(cache_key, result, self._cache_ttl_seconds)
                    return result
            except Exception:
                logger.debug("Metrics-based volume query failed, falling back", exc_info=True)

        total_seconds = max(0, int((end - start) / 1_000_000))
        num_buckets = max(1, min(240, (total_seconds + step - 1) // step))

        try:
            metrics = await self.get_trace_metrics(service=service, start=start, end=end, tenant_id=tenant_id)
            total_traces = int(metrics.get("total_traces") or 0)
            if total_traces > 0:
                base = total_traces // num_buckets
                rem = total_traces % num_buckets
                counts = [str(base + (1 if i < rem else 0)) for i in range(num_buckets)]
                values = [
                    [int((start + i * step * 1_000_000) / 1_000_000), counts[i]]
                    for i in range(num_buckets)
                ]
                result = {"data": {"result": [{"metric": {}, "values": values}]}}
                await self._volume_cache.set(cache_key, result, self._cache_ttl_seconds)
                return result
        except Exception:
            logger.debug("Failed to estimate trace volume from totals", exc_info=True)

        counts = [0] * num_buckets
        values = [
            [int((start + i * step * 1_000_000) / 1_000_000), str(counts[i])]
            for i in range(num_buckets)
        ]
        result = {"data": {"result": [{"metric": {}, "values": values}]}}
        await self._volume_cache.set(cache_key, result, self._cache_ttl_seconds)
        return result

    async def count_traces(self, query: TraceQuery, tenant_id: str = config.DEFAULT_ORG_ID) -> int:
        if config.TEMPO_USE_METRICS_FOR_COUNT and query.start and query.end:
            try:
                duration_s = max(1, int((query.end - query.start) / 1_000_000))
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

        query_copy = TraceQuery(
            service=query.service,
            operation=query.operation,
            min_duration=query.min_duration,
            max_duration=query.max_duration,
            start=query.start,
            end=query.end,
            tags=query.tags,
            limit=min(query.limit, 1000),
        )
        response = await self.search_traces(query_copy, tenant_id=tenant_id, fetch_full_traces=False)
        self._observe("tempo_count_traces_calls_total")
        return response.total