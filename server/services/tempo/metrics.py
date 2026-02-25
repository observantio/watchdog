"""
Tempo metrics queries and processing logic, providing functions to query Tempo for trace metrics based on alert rule conditions and to process the retrieved metrics for use in alert evaluation. This module includes logic to construct appropriate queries for Tempo based on the alert rule configurations, to handle the responses from Tempo, and to extract relevant metric data that can be used in the context of alerting. The metrics processing functions ensure that the data retrieved from Tempo is in a format suitable for evaluating alert conditions and making decisions about when to trigger alerts based on trace metrics.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


from typing import Any, Dict, List, Optional, Callable, Tuple
import logging

import httpx
from config import config

logger = logging.getLogger(__name__)

_empty = {"status": "error", "data": {"result": []}}


async def query_metrics_range(
    client: Any,
    promql: str,
    start_us: Optional[int],
    end_us: Optional[int],
    step_s: int = 300,
    tenant_id: str = config.DEFAULT_ORG_ID,
    mimir_url: str = config.MIMIR_URL,
    get_headers: Callable[[str], Dict[str, str]] = lambda tid: {"X-Scope-OrgID": tid},
    observe: Callable[[str, float], None] = lambda *a, **k: None,
    metrics_enabled: bool = True,
) -> Tuple[Dict[str, Any], bool]:
    if not metrics_enabled:
        return _empty, False

    params: Dict[str, Any] = {"query": promql, "step": step_s}
    if start_us:
        params["start"] = int(start_us / 1_000_000)
    if end_us:
        params["end"] = int(end_us / 1_000_000)

    headers = get_headers(tenant_id)

    try:
        resp = await client.get(
            f"{mimir_url.rstrip('/')}/api/v1/query_range",
            params=params,
            headers=headers,
        )
        resp.raise_for_status()
        observe("tempo_metrics_queries_total")
        return resp.json(), True
    except httpx.HTTPError as e:
        observe("tempo_metrics_query_errors_total")
        logger.debug("Mimir metrics query failed: %s", e)
        return _empty, metrics_enabled


def extract_metric_values(metrics_resp: Dict[str, Any]) -> List[List[Any]]:
    results = (metrics_resp.get("data") or {}).get("result") if isinstance(metrics_resp, dict) else None
    if not results:
        return []
    ts_map: Dict[int, int] = {}
    for series in results:
        for ts, v in series.get("values") or []:
            try:
                ts_map[int(float(ts))] = ts_map.get(int(float(ts)), 0) + int(float(v))
            except (TypeError, ValueError):
                continue
    return [[ts, str(ts_map[ts])] for ts in sorted(ts_map)]
