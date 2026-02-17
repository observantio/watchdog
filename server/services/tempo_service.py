"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

Tempo service for trace operations.
"""
import httpx
import logging
import json
from typing import List, Optional, Dict, Any
from models.observability.tempo_models import Trace, TraceQuery, TraceResponse, Span
from config import config
from middleware.resilience import with_retry, with_timeout
from services.common.http_client import create_async_client

logger = logging.getLogger(__name__)


SERVICE_NAME_KEY = "service.name"
SERVICE_ALIAS_KEY = "service"
SERVICE_KEYS = [SERVICE_NAME_KEY, SERVICE_ALIAS_KEY]

class TempoService:
    """Service for interacting with Tempo tracing backend."""
    
    def __init__(self, tempo_url: str = config.TEMPO_URL):
        """Initialize Tempo service.
        
        Args:
            tempo_url: Base URL for Tempo instance
        """
        self.tempo_url = tempo_url.rstrip('/')
        self.timeout = config.DEFAULT_TIMEOUT
        self._client = create_async_client(self.timeout)
    
    def _get_headers(self, tenant_id: str = config.DEFAULT_ORG_ID) -> dict:
        """Get headers including tenant ID for multi-tenancy.
        
        Args:
            tenant_id: Organization/tenant ID for data isolation
            
        Returns:
            Dictionary of headers
        """
        return {"X-Scope-OrgID": tenant_id}
    
    @with_retry()
    @with_timeout()
    async def search_traces(
        self,
        query: TraceQuery,
        tenant_id: str = config.DEFAULT_ORG_ID,
        fetch_full_traces: bool = True
    ) -> TraceResponse:
        """Search for traces matching query parameters.
        
        Args:
            query: TraceQuery with search parameters
            tenant_id: Organization/tenant ID for data isolation
            
        Returns:
            TraceResponse with matching traces
        """
        params = self._build_search_params(query)
        headers = self._get_headers(tenant_id)
        
        try:
            response = await self._client.get(
                f"{self.tempo_url}/api/search",
                params=params,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            
            traces = []
            if "traces" in data:
                for trace_data in data["traces"]:
                    trace_id = trace_data.get("traceID")
                    if trace_id:
                        if fetch_full_traces:
                            full_trace = await self.get_trace(trace_id, tenant_id=tenant_id)
                            if full_trace:
                                traces.append(full_trace)
                            else:
                                traces.append(
                                    Trace(
                                        traceID=trace_id,
                                        spans=[],
                                        processes={},
                                        warnings=["Trace details unavailable"]
                                    )
                                )
                        else:
                            traces.append(
                                Trace(
                                    traceID=trace_id,
                                    spans=[],
                                    processes={},
                                    warnings=["Trace details not fetched"]
                                )
                            )
            
            return TraceResponse(
                data=traces,
                total=len(traces),
                limit=query.limit,
                offset=0
            )
            
        except httpx.HTTPError as e:
            logger.error("Error searching traces: %s", e)
            return TraceResponse(
                data=[],
                total=0,
                limit=query.limit,
                errors=[str(e)]
            )
    
    @with_retry()
    @with_timeout()
    async def get_trace(self, trace_id: str, tenant_id: str = config.DEFAULT_ORG_ID) -> Optional[Trace]:
        """Get a specific trace by ID.
        
        Args:
            trace_id: Trace identifier
            tenant_id: Organization/tenant ID for data isolation
            
        Returns:
            Trace object or None if not found
        """
        headers = self._get_headers(tenant_id)
        try:
            response = await self._client.get(
                f"{self.tempo_url}/api/traces/{trace_id}",
                headers=headers
            )
            response.raise_for_status()
            if not response.content:
                logger.debug("Tempo returned empty response for trace %s", trace_id)
                return None

            try:
                data = response.json()
            except json.JSONDecodeError:
                logger.debug("Tempo returned non-JSON response for trace %s", trace_id)
                return None
            
            
            if "batches" in data:
                trace = self._parse_tempo_trace(trace_id, data)
                return trace
            
            return None
            
        except httpx.HTTPError as e:
            logger.error("Error fetching trace %s: %s", trace_id, e)
            return None
    
    @with_retry()
    @with_timeout()
    async def get_services(self, tenant_id: str = config.DEFAULT_ORG_ID) -> List[str]:
        """Get list of services that have traces.
        
        Args:
            tenant_id: Organization/tenant ID for data isolation
        
        Returns:
            List of service names
        """
        headers = self._get_headers(tenant_id)
        try:
            response = await self._client.get(f"{self.tempo_url}/api/search/tags", headers=headers)
            response.raise_for_status()
            data = response.json()
            logger.debug("Tempo /api/search/tags response: %s", data)

            services = []

            tag_names = []
            if isinstance(data, dict):
                if "tagNames" in data and isinstance(data["tagNames"], list):
                    tag_names = data["tagNames"]
                elif "data" in data and isinstance(data["data"], dict) and "tagNames" in data["data"]:
                    tag_names = data["data"]["tagNames"]
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "tagName" in item:
                        tag_names.append(item.get("tagName"))

            for tag in tag_names:
                if tag in SERVICE_KEYS:
                    try:
                        values_resp = await self._client.get(
                            f"{self.tempo_url}/api/search/tag/{tag}/values",
                            headers=headers
                        )
                        values_resp.raise_for_status()
                        values_data = values_resp.json()
                        logger.debug("Tempo /api/search/tag/%s/values response: %s", tag, values_data)

                        if isinstance(values_data, dict):
                            if "tagValues" in values_data and isinstance(values_data["tagValues"], list):
                                services.extend(values_data["tagValues"])
                            elif "values" in values_data and isinstance(values_data["values"], list):
                                services.extend(values_data["values"])
                            elif "data" in values_data and isinstance(values_data["data"], list):
                                services.extend(values_data["data"])
                        elif isinstance(values_data, list):
                            services.extend(values_data)
                    except httpx.HTTPError as ve:
                        logger.warning("Failed to fetch tag values for %s: %s", tag, ve)

            if not services:
                logger.debug("No services found from tag endpoints, attempting to infer from recent traces")
                try:
                    search_resp = await self.search_traces(TraceQuery(limit=50), tenant_id=tenant_id)
                    for trace in search_resp.data:
                        for span in trace.spans:
                            if span.service_name:
                                services.append(span.service_name)
                except Exception as ie:
                    logger.warning("Failed to infer services from traces: %s", ie)

            normalized = [s for s in map(str, services) if s]
            return sorted(set(normalized))
            
        except httpx.HTTPError as e:
            logger.error("Error fetching services: %s", e)
            return []
    
    async def get_operations(self, service: str, tenant_id: str = config.DEFAULT_ORG_ID) -> List[str]:
        """Get operations for a specific service.
        
        Args:
            service: Service name
            
        Returns:
            List of operation names
        """
        query = TraceQuery(service=service, limit=100)
        response = await self.search_traces(query, tenant_id=tenant_id)
        
        operations = set()
        for trace in response.data:
            for span in trace.spans:
                operations.add(span.operation_name)
        
        return sorted(operations)
    
    async def get_trace_metrics(
        self,
        service: Optional[str] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        tenant_id: str = config.DEFAULT_ORG_ID
    ) -> Dict[str, Any]:
        """Get trace metrics/statistics.
        
        Args:
            service: Optional service name filter
            start: Start time in microseconds
            end: End time in microseconds
            
        Returns:
            Dictionary with trace metrics
        """
        safe_limit = min(config.MAX_QUERY_LIMIT, 1000)
        query = TraceQuery(service=service, start=start, end=end, limit=safe_limit)
        response = await self.search_traces(query, tenant_id=tenant_id, fetch_full_traces=False)

        return {
            "total_traces": response.total,
            "total_spans": None,
            "error_count": None,
            "avg_duration_us": None,
            "max_duration_us": None,
            "min_duration_us": None,
            "service": service
        }

    async def get_trace_volume(
        self,
        service: Optional[str] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        step: int = 300,
        tenant_id: str = config.DEFAULT_ORG_ID
    ) -> Dict[str, Any]:
        """Return trace counts over time as a Prometheus-style matrix response.

        Time range is in microseconds (matches other Tempo endpoints).
        Buckets the range into `step`-second intervals and counts traces in
        each bucket using `count_traces`. Returns shape compatible with the
        frontend `getVolumeValues` helper (i.e. data.result[0].values).
        """
        import time

        now_us = int(time.time() * 1_000_000)
        if end is None:
            end = now_us
        if start is None:
            # default to last 1 hour
            start = end - (60 * 60 * 1000000)

        if step <= 0:
            step = 300

        # limit number of buckets to avoid excessive load
        max_buckets = 240
        total_seconds = max(0, int((end - start) / 1_000_000))
        num_buckets = int(max(1, min(max_buckets, (total_seconds + step - 1) // step)))

        values = []
        for i in range(num_buckets):
            bucket_start = int(start + i * step * 1_000_000)
            bucket_end = int(min(end, bucket_start + step * 1_000_000))
            try:
                q = TraceQuery(service=service, start=bucket_start, end=bucket_end, limit=1000)
                cnt = await self.count_traces(q, tenant_id=tenant_id)
            except Exception:
                cnt = 0
            ts_seconds = int(bucket_start / 1_000_000)
            values.append([ts_seconds, str(cnt)])

        return {"data": {"result": [{"metric": {}, "values": values}]}}

    async def count_traces(
        self,
        query: TraceQuery,
        tenant_id: str = config.DEFAULT_ORG_ID
    ) -> int:
        """Count traces without fetching full trace details."""
        safe_limit = min(query.limit, 1000)
        query = TraceQuery(
            service=query.service,
            operation=query.operation,
            min_duration=query.min_duration,
            max_duration=query.max_duration,
            start=query.start,
            end=query.end,
            tags=query.tags,
            limit=safe_limit
        )
        response = await self.search_traces(query, tenant_id=tenant_id, fetch_full_traces=False)
        return response.total
    
    def _build_search_params(self, query: TraceQuery) -> Dict[str, Any]:
        """Build search query parameters for Tempo API.
        
        Args:
            query: TraceQuery object
            
        Returns:
            Dictionary of query parameters
        """
        params = {
            "limit": query.limit
        }
        
        tags = {}
        if query.service:
            tags[SERVICE_NAME_KEY] = query.service
        if query.operation:
            tags["name"] = query.operation
        if query.tags:
            tags.update(query.tags)
        
        if tags:
            tag_queries = [f'{k}="{v}"' for k, v in tags.items()]
            params["tags"] = " && ".join(tag_queries)
        
        if query.start:
            params["start"] = int(int(query.start) / 1_000_000)
        if query.end:
            params["end"] = int(int(query.end) / 1_000_000)
    
        if query.min_duration:
            params["minDuration"] = query.min_duration
        if query.max_duration:
            params["maxDuration"] = query.max_duration
        
        return params

    def _parse_tempo_trace(self, trace_id: str, data: Dict[str, Any]) -> Trace:
        """Parse Tempo trace format into our Trace model.
        
        Args:
            trace_id: Trace ID
            data: Raw trace data from Tempo
            
        Returns:
            Parsed Trace object
        """
        spans = []
        processes = {}

        for batch in data.get("batches", []):
            resource_attrs = self._parse_attributes(batch.get("resource", {}).get("attributes", []))
            service_name = (
                resource_attrs.get(SERVICE_NAME_KEY)
                or resource_attrs.get(SERVICE_ALIAS_KEY)
                or resource_attrs.get("serviceName")
                or "unknown"
            )
            process_id = str(service_name)
            processes[process_id] = {
                "serviceName": service_name,
                "resource": batch.get("resource", {}),
                "attributes": resource_attrs,
            }

            for span_data in batch.get("scopeSpans", []):
                for span in span_data.get("spans", []):
                    span_obj = self._parse_span(span, trace_id, process_id, service_name, resource_attrs)
                    spans.append(span_obj)
        
        return Trace(
            traceID=trace_id,
            spans=spans,
            processes=processes
        )
    
    def _parse_span(
        self,
        span_data: Dict[str, Any],
        trace_id: str,
        process_id: str,
        service_name: Optional[str],
        resource_attrs: Optional[Dict[str, Any]] = None
    ) -> Span:
        """Parse individual span data.
        
        Args:
            span_data: Raw span data
            trace_id: Trace ID
            process_id: Process ID
            
        Returns:
            Parsed Span object
        """
        tags = []
        attr_map = self._parse_attributes(span_data.get("attributes", []))
        for key, value in attr_map.items():
            tags.append({"key": key, "value": value})

        
        if service_name and SERVICE_NAME_KEY not in attr_map:
            attr_map[SERVICE_NAME_KEY] = service_name
            tags.append({"key": SERVICE_NAME_KEY, "value": service_name})

        if resource_attrs:
            for rk, rv in resource_attrs.items():
                attr_map.setdefault(rk, rv)
        
        start_time = int(span_data.get("startTimeUnixNano", 0)) // 1000 
        end_time = int(span_data.get("endTimeUnixNano", 0)) // 1000
        duration = end_time - start_time
        
        parent_span_id = None
        if "parentSpanId" in span_data and span_data["parentSpanId"]:
            parent_span_id = span_data["parentSpanId"]
        
        return Span(
            spanID=span_data.get("spanId", ""),
            traceID=trace_id,
            parentSpanID=parent_span_id,
            operationName=span_data.get("name", ""),
            startTime=start_time,
            duration=duration,
            tags=tags,
            serviceName=service_name,
            attributes=attr_map,
            processID=process_id
        )

    def _parse_attributes(self, attrs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse OTLP attributes list into a key-value map."""
        parsed: Dict[str, Any] = {}
        for attr in attrs or []:
            key = attr.get("key", "")
            value = attr.get("value", {})
            for val_type in ["stringValue", "intValue", "boolValue", "doubleValue"]:
                if val_type in value:
                    parsed[key] = value[val_type]
                    break
        return parsed
