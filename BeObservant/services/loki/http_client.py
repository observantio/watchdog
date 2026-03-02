"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import logging
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class LokiHttpClient:
    def __init__(self, metrics: Optional[Dict[str, float]] = None) -> None:
        self._metrics: Dict[str, float] = metrics if metrics is not None else {}

    def _observe(self, metric: str, value: float = 1.0) -> None:
        self._metrics[metric] = self._metrics.get(metric, 0.0) + value

    async def timed_get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        finally:
            self._observe("loki_query_total")
            self._observe("loki_query_duration_sum_seconds", time.perf_counter() - started)

    async def safe_get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: Dict[str, Any],
        headers: Dict[str, str],
        quiet: bool = False,
    ) -> Optional[Dict[str, Any]]:
        try:
            return await self.timed_get_json(client, url, params=params, headers=headers)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            self._observe("loki_query_errors_total")
            is_client_error = 400 <= status < 500
            if quiet or is_client_error:
                logger.debug("Loki %s error for %s", status, url)
            else:
                logger.warning("Loki server error %s for %s", status, url)
        except httpx.HTTPError as e:
            self._observe("loki_query_errors_total")
            log = logger.debug if quiet else logger.warning
            log("Loki request failed for %s: %s", url, e)
        return None