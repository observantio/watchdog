"""
Helper functions for OTLP agent management.

This module extracts shared routines from AgentService so that the main
service class remains lightweight and focused on orchestration. Helpers
include ID generation, registry updates, and Mimir query logic.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any

import httpx

from config import config
from models.observability.agent_models import AgentHeartbeat, AgentInfo

ATTR_HOST_NAME = "host.name"
ATTR_HOST_HOSTNAME = "host.hostname"


def make_agent_id(name: str, tenant_id: str) -> str:
    return f"{tenant_id}:{name}" if tenant_id else name


def update_agent_registry(registry: Dict[str, AgentInfo], heartbeat: AgentHeartbeat) -> None:
    ts = heartbeat.timestamp or datetime.now(timezone.utc)
    agent_id = make_agent_id(heartbeat.name, heartbeat.tenant_id)
    attributes = heartbeat.attributes or {}
    host_name = attributes.get(ATTR_HOST_NAME) or attributes.get(ATTR_HOST_HOSTNAME)
    info = registry.get(agent_id)
    if not info:
        info = AgentInfo(
            id=agent_id,
            name=heartbeat.name,
            tenant_id=heartbeat.tenant_id,
            host_name=str(host_name) if host_name else None,
            last_seen=ts,
            signals=[heartbeat.signal] if heartbeat.signal else [],
            attributes=attributes,
        )
    else:
        info.last_seen = ts
        if host_name:
            info.host_name = str(host_name)
        if heartbeat.signal and heartbeat.signal not in info.signals:
            info.signals.append(heartbeat.signal)
    registry[agent_id] = info


def extract_metrics_count(payload: Dict[str, Any]) -> int:
    result = payload.get("data", {}).get("result", [])
    if not result:
        return 0
    value = result[0].get("value", [0, 0])[1]
    return int(float(value))


async def query_key_activity(key_value: str, mimir_client: httpx.AsyncClient) -> Dict[str, Any]:
    """Ask Mimir whether a given API key has produced metrics recently.

    The query covers the last hour. Results include a boolean flag and the
    raw sample count. Errors are caught and treated as inactive.
    """
    now = datetime.now(timezone.utc)
    start_ns = int((now - timedelta(hours=1)).timestamp() * 1_000_000_000)
    end_ns = int(now.timestamp() * 1_000_000_000)

    metrics_active = False
    metrics_count = 0

    try:
        response = await mimir_client.get(
            f"{config.MIMIR_URL.rstrip('/')}/prometheus/api/v1/query",
            params={"query": "count({__name__=~\".+\"})", "start": start_ns, "end": end_ns},
            headers={"X-Scope-OrgID": key_value},
        )
        response.raise_for_status()
        payload = response.json()
        metrics_count = extract_metrics_count(payload)
        metrics_active = metrics_count > 0
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        metrics_active = False

    return {
        "metrics_active": metrics_active,
        "metrics_count": metrics_count,
    }
