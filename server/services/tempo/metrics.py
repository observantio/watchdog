"""Metrics query helpers for TempoService.

Exports:
- query_metrics_range(...) -> (result_dict, metrics_enabled_flag)
- extract_metric_values(metrics_resp) -> List[List[Any]]

These functions are extracted to keep TempoService small; `query_metrics_range` is stateful
via the returned `metrics_enabled` flag which the caller should assign back to the
service instance when needed.
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
    tempo_url: str = config.TEMPO_URL,
    mimir_url: str = config.MIMIR_URL,
    get_headers: Callable[[str], Dict[str, str]] = lambda tid: {"X-Scope-OrgID": tid},
    observe: Callable[[str, float], None] = lambda *a, **k: None,
    metrics_enabled: bool = True,
) -> Tuple[Dict[str, Any], bool]:
    """Query metrics endpoint(s). Returns (result, metrics_enabled).

    Behavior mirrors the previous `TempoService._query_metrics_range`:
    - if metrics_enabled is False, returns an _empty response immediately
    - tries tempo `/api/metrics/query_range` first, then falls back to Mimir
    - updates metrics_enabled to False when a 4xx is received from primary endpoint
    """
    if not metrics_enabled:
        return _empty, False

    params: Dict[str, Any] = {"query": promql, "step": step_s}
    if start_us:
        params["start"] = int(start_us / 1_000_000)
    if end_us:
        params["end"] = int(end_us / 1_000_000)

    headers = get_headers(tenant_id)

    async def _fetch(url: str, req_params: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], bool]:
        """Return (payload_or_none, saw_4xx_flag)."""
        try:
            resp = await client.get(url, params=req_params, headers=headers)
            if 400 <= getattr(resp, "status_code", 0) < 500:
                observe("tempo_metrics_query_errors_total")
                logger.debug("Metrics endpoint %s returned %s, disabling", url, getattr(resp, "status_code", None))
                return None, True
            # raise for 5xx and other client/network errors
            if hasattr(resp, "raise_for_status"):
                resp.raise_for_status()
            observe("tempo_metrics_queries_total")
            return resp.json(), False
        except httpx.HTTPError as e:
            observe("tempo_metrics_query_errors_total")
            logger.debug("Metrics query failed for %s: %s", url, e)
            return None, False

    result, saw_4xx = await _fetch(f"{tempo_url.rstrip('/')}/api/metrics/query_range", params)
    if result is not None:
        return result, True

    # if the primary returned a 4xx, disable future metrics queries
    if saw_4xx:
        metrics_enabled = False

    mimir_params = {**params, "start": params.get("start"), "end": params.get("end")}
    result, _ = await _fetch(f"{mimir_url.rstrip('/')}/api/v1/query_range", mimir_params)
    return (result if result is not None else _empty), metrics_enabled


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
