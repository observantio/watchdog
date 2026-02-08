"""Tempo service for trace operations."""
import httpx
import logging
from typing import List, Optional, Dict, Any
from models.tempo_models import Trace, TraceQuery, TraceResponse, Span
from config import config
from middleware.resilience import with_retry, with_timeout

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
    
    @with_retry()
    @with_timeout()
    async def search_traces(self, query: TraceQuery) -> TraceResponse:
        """Search for traces matching query parameters.
        
        Args:
            query: TraceQuery with search parameters
            
        Returns:
            TraceResponse with matching traces
        """
        params = self._build_search_params(query)
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.tempo_url}/api/search",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                
                traces = []
                if "traces" in data:
                    for trace_data in data["traces"]:
                        trace_id = trace_data.get("traceID")
                        if trace_id:
                            full_trace = await self.get_trace(trace_id)
                            if full_trace:
                                traces.append(full_trace)
                
                return TraceResponse(
                    data=traces,
                    total=len(traces),
                    limit=query.limit,
                    offset=0
                )
                
            except httpx.HTTPError as e:
                logger.error(f"Error searching traces: {e}")
                return TraceResponse(
                    data=[],
                    total=0,
                    limit=query.limit,
                    errors=[str(e)]
                )
    
    @with_retry()
    @with_timeout()
    async def get_trace(self, trace_id: str) -> Optional[Trace]:
        """Get a specific trace by ID.
        
        Args:
            trace_id: Trace identifier
            
        Returns:
            Trace object or None if not found
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.tempo_url}/api/traces/{trace_id}"
                )
                response.raise_for_status()
                data = response.json()
                
                
                if "batches" in data:
                    trace = self._parse_tempo_trace(trace_id, data)
                    return trace
                
                return None
                
            except httpx.HTTPError as e:
                logger.error(f"Error fetching trace {trace_id}: {e}")
                return None
    
    @with_retry()
    @with_timeout()
    async def get_services(self) -> List[str]:
        """Get list of services that have traces.
        
        Returns:
            List of service names
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.tempo_url}/api/search/tags"
                )
                response.raise_for_status()
                data = response.json()
                services = []
                if "tagNames" in data:
                    for tag in data["tagNames"]:
                        if tag in SERVICE_KEYS:
                            values_response = await client.get(
                                f"{self.tempo_url}/api/search/tag/{tag}/values"
                            )
                            values_response.raise_for_status()
                            values_data = values_response.json()
                            if "tagValues" in values_data:
                                services.extend(values_data["tagValues"])
                
                return list(set(services))
                
            except httpx.HTTPError as e:
                logger.error(f"Error fetching services: {e}")
                return []
    
    async def get_operations(self, service: str) -> List[str]:
        """Get operations for a specific service.
        
        Args:
            service: Service name
            
        Returns:
            List of operation names
        """
        query = TraceQuery(service=service, limit=100)
        response = await self.search_traces(query)
        
        operations = set()
        for trace in response.data:
            for span in trace.spans:
                operations.add(span.operation_name)
        
        return sorted(operations)
    
    async def get_trace_metrics(
        self,
        service: Optional[str] = None,
        start: Optional[int] = None,
        end: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get trace metrics/statistics.
        
        Args:
            service: Optional service name filter
            start: Start time in microseconds
            end: End time in microseconds
            
        Returns:
            Dictionary with trace metrics
        """
        query = TraceQuery(service=service, start=start, end=end, limit=1000)
        response = await self.search_traces(query)
        
        total_spans = sum(len(trace.spans) for trace in response.data)
        durations = []
        error_count = 0
        
        for trace in response.data:
            for span in trace.spans:
                durations.append(span.duration)
                for tag in span.tags:
                    if tag.key == "error" and tag.value is True:
                        error_count += 1
                        break
        
        avg_duration = sum(durations) / len(durations) if durations else 0
        max_duration = max(durations) if durations else 0
        min_duration = min(durations) if durations else 0
        
        return {
            "total_traces": response.total,
            "total_spans": total_spans,
            "error_count": error_count,
            "avg_duration_us": int(avg_duration),
            "max_duration_us": max_duration,
            "min_duration_us": min_duration,
            "service": service
        }
    
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
