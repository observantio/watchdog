"""
Service for managing interactions with Loki, providing functions to query logs, retrieve labels and label values, and perform log aggregation. This module includes logic to construct appropriate LogQL queries based on input parameters, to handle responses from Loki, and to implement fallback mechanisms for cases where initial queries do not return results. The service also includes caching for label retrieval to improve performance and reduce load on the Loki instance, as well as metrics collection for monitoring query performance and error rates.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from config import config
from middleware.resilience import with_retry, with_timeout
from models.observability.loki_models import (
    LogLabelsResponse,
    LogLabelValuesResponse,
    LogQuery,
    LogResponse,
    LogDirection,
    LogStatsResponse,
)
from services.common.http_client import create_async_client
from services.common.ttl_cache import TTLCache
from services.loki.label_utils import (
    normalize_label_value,
    normalize_label_values,
    parse_labelset_value,
)
from services.loki.http_client import LokiHttpClient
from services.loki.fallback import build_service_fallback_queries, run_fallback_queries

logger = logging.getLogger(__name__)

_SERVICE_LABEL_EXACT_RE = re.compile(
    r'(?P<label>service_name|service\.name)\s*=\s*"(?P<value>[^"]+)"'
)


class LokiService:
    def __init__(self, loki_url: str = config.LOKI_URL):
        self.loki_url = loki_url.rstrip("/")
        self.timeout = config.DEFAULT_TIMEOUT
        self._client = create_async_client(self.timeout)
        self._cache_ttl_seconds = max(1, int(config.SERVICE_CACHE_TTL_SECONDS))
        self._volume_cache_ttl_seconds = max(1, int(getattr(config, "LOKI_VOLUME_CACHE_TTL_SECONDS", self._cache_ttl_seconds)))
        self._metrics: Dict[str, float] = {
            "loki_query_total": 0,
            "loki_query_errors_total": 0,
            "loki_query_fallbacks_total": 0,
            "loki_query_duration_sum_seconds": 0.0,
        }
        self._labels_cache = TTLCache()
        self._volume_cache = TTLCache()
        self._volume_inflight: Dict[str, asyncio.Future] = {}
        self._volume_inflight_lock = asyncio.Lock()
        self._http_client = LokiHttpClient(self._metrics)
        logging.getLogger("httpx").setLevel(logging.WARNING)

    def _observe(self, metric: str, value: float = 1.0) -> None:
        self._metrics[metric] = float(self._metrics.get(metric, 0.0) + value)

    async def _timed_get_json(
        self, url: str, *, params: Dict[str, Any], headers: Dict[str, str]
    ) -> Dict[str, Any]:
        return await self._http_client.timed_get_json(self._client, url, params=params, headers=headers)

    async def _safe_get_json(
        self, url: str, *, params: Dict[str, Any], headers: Dict[str, str], quiet: bool = False
    ) -> Optional[Dict[str, Any]]:
        return await self._http_client.safe_get_json(self._client, url, params=params, headers=headers, quiet=quiet)

    def _get_headers(self, tenant_id: str = config.DEFAULT_ORG_ID) -> Dict[str, str]:
        return {"X-Scope-OrgID": tenant_id}

    def _escape_logql_string(self, value: str) -> str:
        if not isinstance(value, str):
            return value
        return (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )

    def _build_label_selector(self, labels: Dict[str, str]) -> str:
        if not labels:
            return "{}"
        return "{" + ", ".join(f'{k}="{self._escape_logql_string(v)}"' for k, v in labels.items()) + "}"

    def _build_query_params(self, query: LogQuery) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "query": query.query,
            "limit": query.limit,
            "direction": query.direction.value,
        }
        for key in ("start", "end", "step"):
            val = getattr(query, key, None)
            if val is not None:
                params[key] = val
        return params

    def _normalize_range_for_step(
        self,
        start_ns: Optional[int],
        end_ns: Optional[int],
        step_s: int,
    ) -> tuple[int, int]:
        now_ns = int(time.time() * 1_000_000_000)
        end = int(end_ns or now_ns)
        start = int(start_ns or (end - 3_600 * 1_000_000_000))
        step_ns = max(1, int(step_s)) * 1_000_000_000
        start = (start // step_ns) * step_ns
        end = (end // step_ns) * step_ns
        if end <= start:
            end = start + step_ns
        return start, end

    async def _get_or_build_volume(
        self,
        cache_key: str,
        builder,
    ) -> Dict[str, Any]:
        cached = await self._volume_cache.get(cache_key)
        if cached is not None:
            return cached

        owner = False
        async with self._volume_inflight_lock:
            cached = await self._volume_cache.get(cache_key)
            if cached is not None:
                return cached
            future = self._volume_inflight.get(cache_key)
            if future is None:
                future = asyncio.get_running_loop().create_future()
                self._volume_inflight[cache_key] = future
                owner = True

        if not owner:
            return await future

        try:
            result = await builder()
            await self._volume_cache.set(cache_key, result, self._volume_cache_ttl_seconds)
            if not future.done():
                future.set_result(result)
            return result
        except Exception as exc:
            if not future.done():
                future.set_exception(exc)
                # Mark retrieved for the owner path when there are no waiters.
                _ = future.exception()
            raise
        finally:
            async with self._volume_inflight_lock:
                self._volume_inflight.pop(cache_key, None)

    def _calculate_stats(self, data: Dict[str, Any]) -> Optional[LogStatsResponse]:
        try:
            result = data.get("result", [])
            if not result:
                return None
            payload = {
                "total_entries": sum(len(s.get("values", [])) for s in result),
                "total_bytes": sum(
                    len(v[1]) for s in result for v in s.get("values", []) if len(v) > 1
                ),
                "streams": len(result),
                "chunks": 0,
            }
            return LogStatsResponse.model_validate(payload)
        except Exception as e:
            logger.error("Error calculating stats: %s", e)
            return None

    def _normalize_stream_labels(self, data: Dict[str, Any]) -> None:
        result = data.get("result")
        if not isinstance(result, list):
            return
        for stream in result:
            labels = stream.get("stream")
            if not isinstance(labels, dict):
                continue
            for key, value in list(labels.items()):
                normalized, parsed = normalize_label_value(key, value)
                if normalized is not None:
                    labels[key] = normalized
                if parsed:
                    for k, v in parsed.items():
                        if k not in labels:
                            labels[k] = v

    async def _run_fallback_queries(
        self,
        endpoint: str,
        base_params: Dict[str, Any],
        headers: Dict[str, str],
        query_str: str,
    ) -> Optional[Dict[str, Any]]:
        candidates = build_service_fallback_queries(query_str)[: max(0, config.LOKI_MAX_FALLBACK_QUERIES)]
        if not candidates:
            return None
        self._observe("loki_query_fallbacks_total", len(candidates))
        return await run_fallback_queries(
            endpoint=endpoint,
            base_params=base_params,
            headers=headers,
            query_str=query_str,
            client=self._client,
            http_client=self._http_client,
            max_fallbacks=config.LOKI_MAX_FALLBACK_QUERIES,
            concurrency=config.LOKI_FALLBACK_CONCURRENCY,
        )

    @with_retry()
    @with_timeout()
    async def query_logs(
        self, query: LogQuery, tenant_id: str = config.DEFAULT_ORG_ID
    ) -> LogResponse:
        params = self._build_query_params(query)
        headers = self._get_headers(tenant_id)
        endpoint = f"{self.loki_url}/loki/api/v1/query_range"

        try:
            data = await self._timed_get_json(endpoint, params=params, headers=headers)
            if query.query and not data.get("data", {}).get("result"):
                fallback = await self._run_fallback_queries(endpoint, params, headers, query.query)
                if fallback:
                    data = fallback
            data_payload = data.get("data", {})
            self._normalize_stream_labels(data_payload)
            return LogResponse(
                status=data.get("status", "success"),
                data=data_payload,
                stats=self._calculate_stats(data_payload),
            )
        except httpx.HTTPError as e:
            self._observe("loki_query_errors_total")
            logger.error("Error querying logs: %s", e)
            return LogResponse(status="error", data={"result": [], "resultType": "streams"}, stats=None)

    @with_retry()
    @with_timeout()
    async def query_logs_instant(
        self,
        query_str: str,
        at_time: Optional[int] = None,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> LogResponse:
        params: Dict[str, Any] = {"query": query_str, "limit": 100}
        if at_time is not None:
            params["time"] = at_time

        headers = self._get_headers(tenant_id)
        endpoint = f"{self.loki_url}/loki/api/v1/query"

        try:
            data = await self._timed_get_json(endpoint, params=params, headers=headers)
            if query_str and not data.get("data", {}).get("result"):
                candidates = build_service_fallback_queries(query_str)[: max(0, config.LOKI_MAX_FALLBACK_QUERIES)]
                semaphore = asyncio.Semaphore(max(1, config.LOKI_FALLBACK_CONCURRENCY))

                async def _query(candidate: str) -> Optional[Dict[str, Any]]:
                    async with semaphore:
                        return await self._safe_get_json(
                            endpoint,
                            params={**params, "query": candidate},
                            headers=headers,
                            quiet=True,
                        )

                tasks = [asyncio.create_task(_query(candidate)) for candidate in candidates]
                try:
                    for task in asyncio.as_completed(tasks):
                        payload = await task
                        if isinstance(payload, dict) and payload.get("data", {}).get("result"):
                            data = payload
                            for pending in tasks:
                                if pending is not task and not pending.done():
                                    pending.cancel()
                            await asyncio.gather(*tasks, return_exceptions=True)
                            break
                finally:
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
            data_payload = data.get("data", {})
            self._normalize_stream_labels(data_payload)
            return LogResponse(status=data.get("status", "success"), data=data_payload)
        except httpx.HTTPError as e:
            logger.error("Error querying logs (instant): %s", e)
            return LogResponse(status="error", data={"result": []})

    @with_retry()
    @with_timeout()
    async def get_labels(
        self,
        start: Optional[int] = None,
        end: Optional[int] = None,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> LogLabelsResponse:
        cache_key = f"{tenant_id}:{start}:{end}"

        async def _fetch_labels():
            params: Dict[str, Any] = {}
            if start:
                params["start"] = start
            if end:
                params["end"] = end
            payload = await self._safe_get_json(
                f"{self.loki_url}/loki/api/v1/labels",
                params=params,
                headers=self._get_headers(tenant_id),
            )
            if isinstance(payload, dict) and payload.get("data") is not None:
                return list(payload["data"])
            return None

        try:
            cached = await self._labels_cache.get_or_set(cache_key, _fetch_labels, self._cache_ttl_seconds)
            if cached is None:
                return LogLabelsResponse(status="error", data=[])
            return LogLabelsResponse(status="success", data=list(cached))
        except httpx.HTTPError as e:
            logger.error("Error fetching labels: %s", e)
            return LogLabelsResponse(status="error", data=[])

    @with_retry()
    @with_timeout()
    async def get_label_values(
        self,
        label: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
        query: Optional[str] = None,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> LogLabelValuesResponse:
        original_start, original_end = start, end
        now_ns = int(datetime.now().timestamp() * 1e9)
        end = end or now_ns
        start = start or int((datetime.now() - timedelta(hours=1)).timestamp() * 1e9)

        try:
            max_hours = int(getattr(config, "LOKI_LABEL_VALUES_MAX_RANGE_HOURS", 24))
        except (TypeError, ValueError):
            max_hours = 24

        max_range_ns = int(max_hours * 3600 * 1e9)
        if end - start > max_range_ns:
            logger.debug("Label values range capped to last %s hours", max_hours)
            start = int(end - max_range_ns)

        params: Dict[str, Any] = {"start": start, "end": end}
        if query:
            params["query"] = query

        range_key = "default" if original_start is None and original_end is None else f"{start}:{end}"
        cache_key = f"label_values:{tenant_id}:{label}:{range_key}:{query or ''}"

        async def _fetch_values():
            payload = await self._safe_get_json(
                f"{self.loki_url}/loki/api/v1/label/{label}/values",
                params=params,
                headers=self._get_headers(tenant_id),
                quiet=True,
            )
            if isinstance(payload, dict) and payload.get("data") is not None:
                values = payload["data"]
            else:
                self._observe("loki_query_fallbacks_total")
                selector = query if isinstance(query, str) and query.strip().startswith("{") else f'{{{label}=~".+"}}'
                log_response = await self.query_logs(
                    LogQuery(query=selector, limit=1000, start=start, end=end),
                    tenant_id=tenant_id,
                )
                results = log_response.data.get("result") if isinstance(log_response.data, dict) else None
                values = list(dict.fromkeys(
                    stream["stream"][label]
                    for stream in (results or [])
                    if isinstance(stream.get("stream"), dict) and stream["stream"].get(label)
                ))

            return list(dict.fromkeys(normalize_label_values(label, values)))

        try:
            values = await self._labels_cache.get_or_set(cache_key, _fetch_values, self._cache_ttl_seconds)
            return LogLabelValuesResponse(status="success", data=values or [])
        except Exception as e:
            logger.error("Error during label-values fallback: %s", e)
            return LogLabelValuesResponse(status="error", data=[])

    @with_retry()
    @with_timeout()
    async def aggregate_logs(
        self,
        query_str: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
        step: int = 60,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> Dict[str, Any]:
        now = datetime.now()
        params: Dict[str, Any] = {
            "query": query_str,
            "step": step,
            "start": start or int((now - timedelta(hours=1)).timestamp() * 1e9),
            "end": end or int(now.timestamp() * 1e9),
        }
        try:
            data = await self._timed_get_json(
                f"{self.loki_url}/loki/api/v1/query_range",
                params=params,
                headers=self._get_headers(tenant_id),
            )
            return {"status": data.get("status", "success"), "data": data.get("data", {}), "query": query_str, "step": step}
        except httpx.HTTPError as e:
            self._observe("loki_query_errors_total")
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            log_fn = logger.debug if status_code and 400 <= status_code < 500 else logger.error
            log_fn("Error aggregating logs (%s): %s", status_code, e)
            return {"status": "error", "error": str(e), "query": query_str}

    @with_retry()
    @with_timeout()
    async def get_log_volume(
        self,
        query_str: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
        step: int = 300,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> Dict[str, Any]:
        step = max(1, int(step))
        start_ns, end_ns = self._normalize_range_for_step(start, end, step)
        query_for_key = str(query_str or "").strip()
        cache_key = f"{tenant_id}:{query_for_key}:{start_ns}:{end_ns}:{step}"

        async def _build() -> Dict[str, Any]:
            base_candidates = [query_str, *build_service_fallback_queries(query_str)]
            if "service_name" in query_str or "service.name" in query_str:
                base_candidates += [
                    query_str.replace("service.name", "service_name"),
                    query_str.replace("service_name", "service"),
                    '{service=~".+"}',
                ]
            candidates = list(dict.fromkeys(base_candidates))[: max(1, config.LOKI_MAX_FALLBACK_QUERIES + 2)]

            semaphore = asyncio.Semaphore(max(1, config.LOKI_FALLBACK_CONCURRENCY))
            last_result: Dict[str, Any] = {"status": "success", "data": {"result": []}, "query": query_str, "step": step}

            async def _aggregate(candidate: str) -> Dict[str, Any]:
                async with semaphore:
                    return await self.aggregate_logs(
                        f"sum(count_over_time({candidate}[{step}s]))",
                        start_ns,
                        end_ns,
                        step,
                        tenant_id=tenant_id,
                    )

            tasks = [asyncio.create_task(_aggregate(candidate)) for candidate in candidates]
            try:
                for task in asyncio.as_completed(tasks):
                    result = await task
                    last_result = result
                    if isinstance(result.get("data"), dict) and result["data"].get("result"):
                        for pending in tasks:
                            if pending is not task and not pending.done():
                                pending.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
                        return result
                return last_result
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

        return await self._get_or_build_volume(cache_key, _build)

    @with_retry()
    @with_timeout()
    async def search_logs_by_pattern(
        self,
        pattern: str,
        labels: Optional[Dict[str, str]] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 100,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> LogResponse:
        label_selector = self._build_label_selector(labels) if labels else "{}"
        query_str = f'{label_selector} |= "{self._escape_logql_string(pattern)}"'
        return await self.query_logs(LogQuery(query=query_str, limit=limit, start=start, end=end, direction=LogDirection.BACKWARD, step=None), tenant_id=tenant_id)

    @with_retry()
    @with_timeout()
    async def filter_logs(
        self,
        labels: Dict[str, str],
        filters: Optional[List[str]] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 100,
        tenant_id: str = config.DEFAULT_ORG_ID,
    ) -> LogResponse:
        query_str = self._build_label_selector(labels)
        if filters:
            query_str += "".join(f' |= "{self._escape_logql_string(f)}"' for f in filters)
        return await self.query_logs(LogQuery(query=query_str, limit=limit, start=start, end=end, direction=LogDirection.BACKWARD, step=None), tenant_id=tenant_id)
