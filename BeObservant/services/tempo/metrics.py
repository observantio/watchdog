"""
Tempo metrics queries and processing logic, providing functions to query Mimir for trace
metrics derived from Tempo and to extract aggregated values for alert evaluation.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from config import config

logger = logging.getLogger(__name__)


def _empty_response() -> Dict[str, Any]:
    return {"status": "error", "data": {"result": []}}


async def query_metrics_range(
    client: Any,
    promql: str,
    start_us: Optional[int],
    end_us: Optional[int],
    step_s: int = 300,
    tenant_id: str = config.DEFAULT_ORG_ID,
    mimir_url: str = config.MIMIR_URL,
    get_headers: Callable[[str], Dict[str, str]] = lambda tid: {"X-Scope-OrgID": tid},
    observe: Callable[[str, float], None] = lambda metric, value: None,
    metrics_enabled: bool = True,
) -> Tuple[Dict[str, Any], bool]:
    if not metrics_enabled:
        return _empty_response(), False

    params: Dict[str, Any] = {"query": promql, "step": step_s}
    if start_us:
        params["start"] = int(start_us / 1_000_000)
    if end_us:
        params["end"] = int(end_us / 1_000_000)

    try:
        resp = await client.get(
            f"{mimir_url.rstrip('/')}/api/v1/query_range",
            params=params,
            headers=get_headers(tenant_id),
        )
        resp.raise_for_status()
        observe("tempo_metrics_queries_total", 1.0)
        return resp.json(), True
    except httpx.HTTPError as e:
        observe("tempo_metrics_query_errors_total", 1.0)
        logger.debug("Mimir metrics query failed: %s", e)
        return _empty_response(), False


def extract_metric_values(metrics_resp: Dict[str, Any]) -> List[List[Any]]:
    if not isinstance(metrics_resp, dict):
        return []
    results = (metrics_resp.get("data") or {}).get("result")
    if not results:
        return []

    ts_map: Dict[int, int] = {}
    for series in results:
        for ts, v in series.get("values") or []:
            try:
                key = int(float(ts))
                ts_map[key] = ts_map.get(key, 0) + int(float(v))
            except (TypeError, ValueError):
                continue

    return [[ts, str(ts_map[ts])] for ts in sorted(ts_map)]