"""
Loki HTTP client utilities for performing HTTP requests to Loki servers with timing and error handling, providing functions to execute timed GET requests that return JSON responses while tracking metrics for query counts, durations, and errors. This module encapsulates the logic for making HTTP requests to Loki, including handling of HTTP status errors and other HTTP-related exceptions, while also integrating with a metrics system to observe query performance and error rates. The client is designed to be used within the LokiService for executing queries against Loki servers while ensuring that performance metrics are collected and errors are properly logged and categorized based on their nature (client vs server errors).

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import time
import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class LokiHttpClient:
    """Encapsulate HTTP get/json with metrics-aware timing and safe error mapping.

    The instance DOES NOT hold the upstream `httpx.AsyncClient` because callers (LokiService)
    replace `self._client` in tests; instead the client is passed into the helper methods.
    """

    def __init__(self, metrics: Optional[Dict[str, float]] = None) -> None:
        self._metrics = metrics if metrics is not None else {}

    def _observe(self, metric: str, value: float = 1.0) -> None:
        self._metrics[metric] = float(self._metrics.get(metric, 0.0) + value)

    async def timed_get_json(self, client: httpx.AsyncClient, url: str, *, params: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        finally:
            self._observe("loki_query_total")
            self._observe("loki_query_duration_sum_seconds", time.perf_counter() - started)

    async def safe_get_json(self, client: httpx.AsyncClient, url: str, *, params: Dict[str, Any], headers: Dict[str, str], quiet: bool = False) -> Optional[Dict[str, Any]]:
        try:
            return await self.timed_get_json(client, url, params=params, headers=headers)
        except httpx.HTTPStatusError as e:
            status = getattr(e.response, "status_code", None)
            self._observe("loki_query_errors_total")
            if quiet or (status and 400 <= status < 500):
                logger.debug("Loki error %s for %s", status, url)
            else:
                logger.warning("Loki server error %s for %s", status, url)
            return None
        except httpx.HTTPError as e:
            self._observe("loki_query_errors_total")
            (logger.debug if quiet else logger.warning)("Loki request failed for %s: %s", url, e)
            return None
