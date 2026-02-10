"""Loki service for log operations."""
import httpx
import logging
import re
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from models import (
    LogQuery, LogResponse, LogLabelsResponse, 
    LogLabelValuesResponse
)
from middleware.resilience import with_retry, with_timeout
from config import config

logger = logging.getLogger(__name__)

SERVICE_NAME_LABEL = "service.name"
SERVICE_NAME_ALIAS = "service_name"
LABELSET_PAIR_RE = re.compile(r'([A-Za-z0-9_.:-]+)="([^"]*)"')
SERVICE_LABEL_EXACT_RE = re.compile(r'(?P<label>service_name|service\.name)\s*=\s*"(?P<value>[^"]+)"')

class LokiService:
    """Service for interacting with Loki logging backend."""
    
    def __init__(self, loki_url: str = "http://loki:3100"):
        """Initialize Loki service.
        
        Args:
            loki_url: Base URL for Loki instance
        """
        self.loki_url = loki_url.rstrip('/')
        self.timeout = 30.0
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    def _get_headers(self, tenant_id: str = config.DEFAULT_ORG_ID) -> dict:
        """Get headers including tenant ID for multi-tenancy.
        
        Args:
            tenant_id: Organization/tenant ID for data isolation
            
        Returns:
            Dictionary of headers
        """
        return {"X-Scope-OrgID": tenant_id}

    def _normalize_service_label_query(self, query_str: str) -> str:
        if SERVICE_NAME_LABEL not in query_str and SERVICE_NAME_ALIAS not in query_str:
            return query_str

        def replace_in_selector(match: re.Match) -> str:
            content = match.group(1)
            updated = re.sub(
                rf'(?<![\w.]){SERVICE_NAME_LABEL}(?=\s*(=|=~))',
                SERVICE_NAME_ALIAS,
                content
            )
            updated = re.sub(
                rf'(?<![\w.]){SERVICE_NAME_ALIAS}(?=\s*(=|=~))',
                SERVICE_NAME_ALIAS,
                updated
            )
            return "{" + updated + "}"

        return re.sub(r"\{([^}]*)\}", replace_in_selector, query_str)

    def _expand_service_label_matchers(self, query_str: str) -> str:
        def replace_match(match: re.Match) -> str:
            label = match.group("label")
            value = match.group("value")
            return f'{label}=~"{value}.*"'

        return SERVICE_LABEL_EXACT_RE.sub(replace_match, query_str)

    def _build_service_fallback_queries(self, query_str: str) -> List[str]:
        candidates: List[str] = []

        normalized = self._normalize_service_label_query(query_str)
        if normalized != query_str:
            candidates.append(normalized)

        expanded_original = self._expand_service_label_matchers(query_str)
        if expanded_original != query_str:
            candidates.append(expanded_original)

        expanded_normalized = self._expand_service_label_matchers(normalized)
        if expanded_normalized not in (query_str, expanded_original):
            candidates.append(expanded_normalized)

        return candidates

    def _parse_labelset_value(self, label_key: str, raw_value: str) -> Optional[Dict[str, str]]:
        if not isinstance(raw_value, str) or '="' not in raw_value:
            return None

        candidate = raw_value
        if f'{label_key}="' not in raw_value:
            candidate = f'{label_key}="{raw_value}'

        pairs = LABELSET_PAIR_RE.findall(candidate)
        if not pairs:
            return None
        return dict(pairs)

    def _normalize_label_value(self, label_key: str, value: Any) -> tuple[Optional[str], Optional[Dict[str, str]]]:
        if not isinstance(value, str):
            return None, None
        if '="' not in value or '",' not in value:
            return None, None

        parsed = self._parse_labelset_value(label_key, value)
        if parsed:
            return parsed.get(label_key, value), parsed

        cut_index = value.find('",')
        if cut_index > 0:
            return value[:cut_index], None

        return None, None

    def _normalize_label_dict(self, labels: Dict[str, Any]) -> Dict[str, str]:
        extra_labels: Dict[str, str] = {}
        for key, value in labels.items():
            normalized_value, parsed = self._normalize_label_value(key, value)
            if normalized_value is not None:
                labels[key] = normalized_value
            if parsed:
                for parsed_key, parsed_value in parsed.items():
                    if parsed_key not in labels:
                        extra_labels[parsed_key] = parsed_value

        return extra_labels

    def _normalize_stream_labels(self, data: Dict[str, Any]) -> None:
        result = data.get("result")
        if not isinstance(result, list):
            return

        for stream in result:
            labels = stream.get("stream")
            if not isinstance(labels, dict):
                continue

            extra = self._normalize_label_dict(labels)
            if extra:
                labels.update(extra)

    def _normalize_label_values(self, label: str, values: List[str]) -> List[str]:
        cleaned: List[str] = []
        for value in values:
            if not isinstance(value, str):
                cleaned.append(value)
                continue

            parsed = self._parse_labelset_value(label, value)
            if parsed and label in parsed:
                cleaned.append(parsed[label])
                continue

            cut_index = value.find('",')
            if cut_index > 0:
                cleaned.append(value[:cut_index])
            else:
                cleaned.append(value)

        return cleaned
    
    @with_retry()
    @with_timeout()
    async def query_logs(self, query: LogQuery, tenant_id: str = config.DEFAULT_ORG_ID) -> LogResponse:
        """Query logs using LogQL.
        
        Args:
            query: LogQuery with search parameters
            tenant_id: Organization/tenant ID for data isolation
            
        Returns:
            LogResponse with matching log streams
        """
        params = self._build_query_params(query)
        headers = self._get_headers(tenant_id)
        
        try:
            response = await self._client.get(
                f"{self.loki_url}/loki/api/v1/query_range",
                params=params,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            
            if query.query and not data.get("data", {}).get("result"):
                for candidate in self._build_service_fallback_queries(query.query):
                    params["query"] = candidate
                    response = await self._client.get(
                        f"{self.loki_url}/loki/api/v1/query_range",
                        params=params,
                        headers=headers
                    )
                    response.raise_for_status()
                    data = response.json()
                    if data.get("data", {}).get("result"):
                        break

            data_payload = data.get("data", {})
            self._normalize_stream_labels(data_payload)

            return LogResponse(
                status=data.get("status", "success"),
                data=data_payload,
                stats=self._calculate_stats(data_payload)
            )
            
        except httpx.HTTPError as e:
            logger.error("Error querying logs: %s", e)
            return LogResponse(
                status="error",
                data={"result": [], "resultType": "streams"},
                stats=None
            )
    
    @with_retry()
    @with_timeout()
    async def query_logs_instant(self, query_str: str, time: Optional[int] = None, tenant_id: str = config.DEFAULT_ORG_ID) -> LogResponse:
        """Query logs at a specific point in time.
        
        Args:
            query_str: LogQL query string
            time: Time in nanoseconds (defaults to now)
            tenant_id: Organization/tenant ID for data isolation
            
        Returns:
            LogResponse with log results
        """
        params = {
            "query": query_str,
            "limit": 100
        }
        if time:
            params["time"] = time
        
        headers = self._get_headers(tenant_id)
        try:
            response = await self._client.get(
                f"{self.loki_url}/loki/api/v1/query",
                params=params,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            
            if query_str and not data.get("data", {}).get("result"):
                for candidate in self._build_service_fallback_queries(query_str):
                    params["query"] = candidate
                    response = await self._client.get(
                        f"{self.loki_url}/loki/api/v1/query",
                        params=params
                    )
                    response.raise_for_status()
                    data = response.json()
                    if data.get("data", {}).get("result"):
                        break

            data_payload = data.get("data", {})
            self._normalize_stream_labels(data_payload)

            return LogResponse(
                status=data.get("status", "success"),
                data=data_payload
            )
            
        except httpx.HTTPError as e:
            logger.error("Error querying logs (instant): %s", e)
            return LogResponse(
                status="error",
                data={"result": []}
            )
    
    @with_retry()
    @with_timeout()
    async def get_labels(self, start: Optional[int] = None, end: Optional[int] = None, tenant_id: str = config.DEFAULT_ORG_ID) -> LogLabelsResponse:
        """Get all available log labels.
        
        Args:
            start: Start time in nanoseconds
            end: End time in nanoseconds
            tenant_id: Organization/tenant ID for data isolation
            
        Returns:
            List of label names
        """
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        
        headers = self._get_headers(tenant_id)
        try:
            response = await self._client.get(
                f"{self.loki_url}/loki/api/v1/labels",
                params=params,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            
            return LogLabelsResponse(
                status=data.get("status", "success"),
                data=data.get("data", [])
            )
            
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
        tenant_id: str = config.DEFAULT_ORG_ID
    ) -> LogLabelValuesResponse:
        """Get values for a specific label.
        
        Args:
            label: Label name
            start: Start time in nanoseconds
            end: End time in nanoseconds
            query: Optional LogQL query to filter results
            tenant_id: Organization/tenant ID for data isolation
            
        Returns:
            List of values for the label
        """
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if query:
            params["query"] = query
        
        headers = self._get_headers(tenant_id)
        try:
            response = await self._client.get(
                f"{self.loki_url}/loki/api/v1/label/{label}/values",
                params=params,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            
            values = data.get("data", [])
            normalized_values = self._normalize_label_values(label, values)

            return LogLabelValuesResponse(
                status=data.get("status", "success"),
                data=normalized_values
            )
            
        except httpx.HTTPError as e:
            logger.error("Error fetching label values: %s", e)
            return LogLabelValuesResponse(status="error", data=[])
    
    @with_retry()
    @with_timeout()
    async def aggregate_logs(
        self,
        query_str: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
        step: int = 60,
        tenant_id: str = config.DEFAULT_ORG_ID
    ) -> Dict[str, Any]:
        """Aggregate logs using LogQL aggregation queries.
        
        Args:
            query_str: LogQL aggregation query (e.g., rate, count_over_time)
            start: Start time in nanoseconds
            end: End time in nanoseconds
            step: Query resolution step in seconds
            tenant_id: Organization/tenant ID for data isolation
            
        Returns:
            Aggregated log data
        """
        params = {
            "query": query_str,
            "step": step
        }
        
        if not start:
            start = int((datetime.now() - timedelta(hours=1)).timestamp() * 1e9)
        if not end:
            end = int(datetime.now().timestamp() * 1e9)
        
        params["start"] = start
        params["end"] = end
        
        headers = self._get_headers(tenant_id)
        try:
            response = await self._client.get(
                f"{self.loki_url}/loki/api/v1/query_range",
                params=params,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            
            return {
                "status": data.get("status", "success"),
                "data": data.get("data", {}),
                "query": query_str,
                "step": step
            }
            
        except httpx.HTTPError as e:
            logger.error("Error aggregating logs: %s", e)
            return {
                "status": "error",
                "error": str(e),
                "query": query_str
            }
    
    @with_retry()
    @with_timeout()
    async def get_log_volume(
        self,
        query_str: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
        step: int = 300,
        tenant_id: str = config.DEFAULT_ORG_ID
    ) -> Dict[str, Any]:
        """Get log volume over time.
        
        Args:
            query_str: LogQL selector query
            start: Start time in nanoseconds
            end: End time in nanoseconds
            step: Time step in seconds
            
        Returns:
            Log volume data over time
        """
        
        candidates = [query_str]
        candidates.extend(self._build_service_fallback_queries(query_str))
        if "service_name" in query_str or "service.name" in query_str:
            candidates.append(query_str.replace("service.name", "service_name"))
            candidates.append(query_str.replace("service_name", "service"))
            candidates.append('{service=~".+"}')
        candidates.append("{}")

        candidates = list(dict.fromkeys(candidates))

        last_result: Dict[str, Any] = {
            "status": "success",
            "data": {"result": []},
            "query": query_str,
            "step": step
        }

        for candidate in candidates:
            volume_query = f'sum(count_over_time({candidate}[{step}s]))'
            result = await self.aggregate_logs(volume_query, start, end, step, tenant_id=tenant_id)
            last_result = result
            data = result.get("data") if isinstance(result, dict) else None
            if isinstance(data, dict) and data.get("result"):
                return result

        return last_result
    
    @with_retry()
    @with_timeout()
    async def search_logs_by_pattern(
        self,
        pattern: str,
        labels: Optional[Dict[str, str]] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 100,
        tenant_id: str = config.DEFAULT_ORG_ID
    ) -> LogResponse:
        """Search logs by text pattern.
        
        Args:
            pattern: Text pattern to search for
            labels: Label filters
            start: Start time in nanoseconds
            end: End time in nanoseconds
            limit: Maximum results
            
        Returns:
            LogResponse with matching logs
        """
        
        label_selector = self._build_label_selector(labels) if labels else '{}'
        query_str = f'{label_selector} |= "{pattern}"'
        
        query = LogQuery(
            query=query_str,
            limit=limit,
            start=start,
            end=end
        )
        
        return await self.query_logs(query)
    
    @with_retry()
    @with_timeout()
    async def filter_logs(
        self,
        labels: Dict[str, str],
        filters: Optional[List[str]] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 100,
        tenant_id: str = config.DEFAULT_ORG_ID
    ) -> LogResponse:
        """Filter logs by labels and optional text filters.
        
        Args:
            labels: Label filters (e.g., {"app": "nginx", "level": "error"})
            filters: Optional text filters to apply
            start: Start time in nanoseconds
            end: End time in nanoseconds
            limit: Maximum results
            
        Returns:
            LogResponse with filtered logs
        """
        label_selector = self._build_label_selector(labels)
        query_str = label_selector
        
        
        if filters:
            for f in filters:
                query_str += f' |= "{f}"'
        
        query = LogQuery(
            query=query_str,
            limit=limit,
            start=start,
            end=end
        )
        
        return await self.query_logs(query)
    
    def _build_query_params(self, query: LogQuery) -> Dict[str, Any]:
        """Build query parameters for Loki API.
        
        Args:
            query: LogQuery object
            
        Returns:
            Dictionary of query parameters
        """
        params = {
            "query": query.query,
            "limit": query.limit,
            "direction": query.direction.value
        }
        
        if query.start:
            params["start"] = query.start
        if query.end:
            params["end"] = query.end
        if query.step:
            params["step"] = query.step
        
        return params
    
    def _build_label_selector(self, labels: Dict[str, str]) -> str:
        """Build LogQL label selector from dictionary.
        
        Args:
            labels: Dictionary of label key-value pairs
            
        Returns:
            LogQL label selector string
        """
        if not labels:
            return "{}"
        
        selectors = [f'{k}="{v}"' for k, v in labels.items()]
        return "{" + ", ".join(selectors) + "}"
    
    def _calculate_stats(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Calculate statistics from log query results.
        
        Args:
            data: Query result data
            
        Returns:
            Statistics dictionary or None
        """
        try:
            result = data.get("result", [])
            if not result:
                return None
            
            total_entries = 0
            total_bytes = 0
            streams = len(result)
            
            for stream in result:
                values = stream.get("values", [])
                total_entries += len(values)
                for value in values:
                    
                    if len(value) > 1:
                        total_bytes += len(value[1])
            
            return {
                "total_entries": total_entries,
                "total_bytes": total_bytes,
                "streams": streams,
                "chunks": 0  
            }
        except Exception as e:
            logger.error("Error calculating stats: %s", e)
            return None
