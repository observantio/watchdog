"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

Agent service for agent registry and activity tracking.
"""


import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any

import httpx

from config import config

from models.observability.agent_models import AgentHeartbeat, AgentInfo

logger = logging.getLogger(__name__)


class AgentService:
    """In-memory registry of recently active OTLP agents."""
    
    ATTR_HOST_NAME = "host.name"
    ATTR_HOST_HOSTNAME = "host.hostname"

    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}

    def _make_agent_id(self, name: str, tenant_id: str) -> str:
        return f"{tenant_id}:{name}" if tenant_id else name

    def update_from_heartbeat(self, heartbeat: AgentHeartbeat) -> None:
        ts = heartbeat.timestamp or datetime.now(timezone.utc)
        agent_id = self._make_agent_id(heartbeat.name, heartbeat.tenant_id)
        attributes = heartbeat.attributes or {}
        host_name = attributes.get(self.ATTR_HOST_NAME) or attributes.get(self.ATTR_HOST_HOSTNAME)
        info = self._agents.get(agent_id)
        if not info:
            info = AgentInfo(
                id=agent_id,
                name=heartbeat.name,
                tenant_id=heartbeat.tenant_id,
                host_name=str(host_name) if host_name else None,
                last_seen=ts,
                signals=[heartbeat.signal] if heartbeat.signal else [],
                attributes=attributes
            )
        else:
            info.last_seen = ts
            if host_name:
                info.host_name = str(host_name)
            if heartbeat.signal and heartbeat.signal not in info.signals:
                info.signals.append(heartbeat.signal)
        self._agents[agent_id] = info

    def list_agents(self) -> List[AgentInfo]:
        return sorted(self._agents.values(), key=lambda a: a.last_seen, reverse=True)

    @staticmethod
    def extract_metrics_count(payload: Dict[str, Any]) -> int:
        result = payload.get("data", {}).get("result", [])
        if not result:
            return 0
        value = result[0].get("value", [0, 0])[1]
        return int(float(value))

    async def key_activity(self, key_value: str, mimir_client: httpx.AsyncClient) -> Dict[str, Any]:
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
            metrics_count = self.extract_metrics_count(payload)
            metrics_active = metrics_count > 0
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            metrics_active = False

        return {
            "metrics_active": metrics_active,
            "metrics_count": metrics_count,
        }
