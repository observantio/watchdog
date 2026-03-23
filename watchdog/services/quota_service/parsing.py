"""
Parsing and extraction helpers for quota services.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Optional


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def format_with_tenant(template: str, tenant_id: str) -> str:
    try:
        return str(template).format(tenant_id=tenant_id)
    except (KeyError, ValueError):
        return str(template)


def extract_path(payload: object, path: str) -> Optional[float]:
    if not path:
        return None
    current: object = payload
    for part in [p for p in str(path).split(".") if p]:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    if isinstance(current, bool):
        return float(int(current))
    if isinstance(current, (int, float)):
        return float(current)
    if isinstance(current, str):
        try:
            return float(current.strip())
        except ValueError:
            return None
    return None


def extract_from_text(text: str, key: str) -> Optional[float]:
    if not text or not key:
        return None
    pattern = re.compile(
        rf"(?im)^\s*{re.escape(key)}\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*$"
    )
    match = pattern.search(text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def response_payload(response: object) -> object:
    try:
        payload = response.json()  # type: ignore[attr-defined]
        if isinstance(payload, (dict, list)):
            return payload
    except (AttributeError, TypeError, ValueError):
        pass
    raw_text = str(getattr(response, "text", "") or "")
    return {"__raw_text": raw_text} if raw_text else {}


def extract_nested_numeric(payload: object, candidates: list[str]) -> Optional[float]:
    for path in candidates:
        value = extract_path(payload, path)
        if value is not None:
            return value
    return None


def extract_tenant_scoped_numeric(
    payload: object,
    *,
    tenant_id: str,
    key_candidates: list[str],
) -> Optional[float]:
    if not isinstance(payload, dict):
        return None

    for key in key_candidates:
        direct = extract_path(payload, f"{tenant_id}.{key}")
        if direct is not None:
            return direct

        for container in (
            "overrides",
            "limits",
            "ingestion_limits",
            "runtime_config.overrides",
            "data.overrides",
            "data.limits",
            "data.ingestion_limits",
        ):
            value = extract_path(payload, f"{container}.{tenant_id}.{key}")
            if value is not None:
                return value
    return None


def compute_remaining(limit: Optional[float], used: Optional[float]) -> Optional[float]:
    if limit is None or used is None:
        return None
    return max(0.0, float(limit) - float(used))


def prom_query_url(config_obj: object) -> str:
    base = str(getattr(config_obj, "QUOTA_PROMETHEUS_BASE_URL", "") or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/api/v1/query"):
        return base
    if base.endswith("/prometheus"):
        return f"{base}/api/v1/query"
    return f"{base}/prometheus/api/v1/query"


def extract_prom_result(payload: object) -> Optional[float]:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    result = data.get("result")
    if not isinstance(result, list) or not result:
        return None
    first = result[0]
    if not isinstance(first, dict):
        return None
    value = first.get("value")
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        return float(value[1])
    except (TypeError, ValueError):
        return None
