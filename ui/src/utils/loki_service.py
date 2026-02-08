"""Loki service for log operations."""
import httpx
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from models import (
    LogQuery, LogResponse, LogLabelsResponse, 
    LogLabelValuesResponse
)
from middleware.resilience import with_retry, with_timeout

logger = logging.getLogger(__name__)

class LokiService:
    """Service for interacting with Loki logging backend."""
    
    def __init__(self, loki_url: str = "http://loki:3100"):
        """Initialize Loki service.
        
        Args:
            loki_url: Base URL for Loki instance
        """
        self.loki_url = loki_url.rstrip('/')
        self.timeout = 30.0
    
    @with_retry()
    @with_timeout()
    async def query_logs(self, query: LogQuery) -> LogResponse:
        """Query logs using LogQL.
        
        Args:
            query: LogQuery with search parameters
            
        Returns:
            LogResponse with matching log streams
        """
        params = self._build_query_params(query)
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.loki_url}/loki/api/v1/query_range",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                
                return LogResponse(
                    status=data.get("status", "success"),
                    data=data.get("data", {}),
                    stats=self._calculate_stats(data.get("data", {}))
                )
                
            except httpx.HTTPError as e:
                logger.error(f"Error querying logs: {e}")
                return LogResponse(
                    status="error",
                    data={"result": [], "resultType": "streams"},
                    stats=None
                )
    
    @with_retry()
    @with_timeout()
    async def query_logs_instant(self, query_str: str, time: Optional[int] = None) -> LogResponse:
        """Query logs at a specific point in time.
        
        Args:
            query_str: LogQL query string
            time: Time in nanoseconds (defaults to now)
            
        Returns:
            LogResponse with log results
        """
        params = {
            "query": query_str,
            "limit": 100
        }
        if time:
            params["time"] = time
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.loki_url}/loki/api/v1/query",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                
                return LogResponse(
                    status=data.get("status", "success"),
                    data=data.get("data", {})
                )
                
            except httpx.HTTPError as e:
                logger.error(f"Error querying logs (instant): {e}")
                return LogResponse(
                    status="error",
                    data={"result": []}
                )
    
    @with_retry()
    @with_timeout()
    async def get_labels(self, start: Optional[int] = None, end: Optional[int] = None) -> LogLabelsResponse:
        """Get all available log labels.
        
        Args:
            start: Start time in nanoseconds
            end: End time in nanoseconds
            
        Returns:
            List of label names
        """
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.loki_url}/loki/api/v1/labels",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                
                return LogLabelsResponse(
                    status=data.get("status", "success"),
                    data=data.get("data", [])
                )
                
            except httpx.HTTPError as e:
                logger.error(f"Error fetching labels: {e}")
                return LogLabelsResponse(status="error", data=[])
    
    @with_retry()
    @with_timeout()
    async def get_label_values(
        self, 
        label: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
        query: Optional[str] = None
    ) -> LogLabelValuesResponse:
        """Get values for a specific label.
        
        Args:
            label: Label name
            start: Start time in nanoseconds
            end: End time in nanoseconds
            query: Optional LogQL query to filter results
            
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
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.loki_url}/loki/api/v1/label/{label}/values",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                
                return LogLabelValuesResponse(
                    status=data.get("status", "success"),
                    data=data.get("data", [])
                )
                
            except httpx.HTTPError as e:
                logger.error(f"Error fetching label values: {e}")
                return LogLabelValuesResponse(status="error", data=[])
    
    async def aggregate_logs(
        self,
        query_str: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
        step: int = 60
    ) -> Dict[str, Any]:
        """Aggregate logs using LogQL aggregation queries.
        
        Args:
            query_str: LogQL aggregation query (e.g., rate, count_over_time)
            start: Start time in nanoseconds
            end: End time in nanoseconds
            step: Query resolution step in seconds
            
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
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.loki_url}/loki/api/v1/query_range",
                    params=params
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
                logger.error(f"Error aggregating logs: {e}")
                return {
                    "status": "error",
                    "error": str(e),
                    "query": query_str
                }
    
    async def get_log_volume(
        self,
        query_str: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
        step: int = 300
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
        
        volume_query = f'sum(count_over_time({query_str}[{step}s]))'
        return await self.aggregate_logs(volume_query, start, end, step)
    
    async def search_logs_by_pattern(
        self,
        pattern: str,
        labels: Optional[Dict[str, str]] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 100
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
    
    async def filter_logs(
        self,
        labels: Dict[str, str],
        filters: Optional[List[str]] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 100
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
            logger.error(f"Error calculating stats: {e}")
            return None
