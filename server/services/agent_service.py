"""
Lightweight service class that delegates the core work to helper functions.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
"""

import logging
from typing import Dict, List, Any

import httpx

from models.observability.agent_models import AgentHeartbeat, AgentInfo

from services.agent.helpers import (
    make_agent_id,
    update_agent_registry,
    extract_metrics_count,
    query_key_activity,
)

logger = logging.getLogger(__name__)

class AgentService:
    ATTR_HOST_NAME = "host.name"
    ATTR_HOST_HOSTNAME = "host.hostname"

    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}

    def _make_agent_id(self, name: str, tenant_id: str) -> str:
        return make_agent_id(name, tenant_id)

    def update_from_heartbeat(self, heartbeat: AgentHeartbeat) -> None:
        update_agent_registry(self._agents, heartbeat)

    def list_agents(self) -> List[AgentInfo]:
        return sorted(self._agents.values(), key=lambda a: a.last_seen, reverse=True)

    @staticmethod
    def extract_metrics_count(payload: Dict[str, Any]) -> int:
        return extract_metrics_count(payload)

    async def key_activity(self, key_value: str, mimir_client: httpx.AsyncClient) -> Dict[str, Any]:
        return await query_key_activity(key_value, mimir_client)
