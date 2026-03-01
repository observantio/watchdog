"""Unit tests for agent service helpers and wrapper class."""

import asyncio
from datetime import datetime, timezone, timedelta

import pytest

from models.observability.agent_models import AgentHeartbeat, AgentInfo
from services.agent import AgentService
from services.agent import helpers


def test_make_agent_id():
    assert helpers.make_agent_id("agent", "") == "agent"
    assert helpers.make_agent_id("agent", "tenant") == "tenant:agent"


def test_update_registry_new_and_existing():
    registry: dict[str, AgentInfo] = {}
    now = datetime.now(timezone.utc)
    hb = AgentHeartbeat(name="a", tenant_id="t", timestamp=now, attributes={"host.name": "h"}, signal="s")
    helpers.update_agent_registry(registry, hb)
    assert "t:a" in registry
    info = registry["t:a"]
    assert info.name == "a"
    assert info.host_name == "h"
    assert info.signals == ["s"]
    # update again with new signal
    later = now + timedelta(seconds=5)
    hb2 = AgentHeartbeat(name="a", tenant_id="t", timestamp=later, attributes={}, signal="s2")
    helpers.update_agent_registry(registry, hb2)
    info2 = registry["t:a"]
    assert info2.last_seen == later
    assert "s2" in info2.signals


def test_extract_metrics_count():
    assert helpers.extract_metrics_count({}) == 0
    payload = {"data": {"result": [{"value": [123, "7.0"]}]}}
    assert helpers.extract_metrics_count(payload) == 7


class DummyClient:
    def __init__(self, payload):
        self.payload = payload

    async def get(self, url, params=None, headers=None):
        class Resp:
            def __init__(self, data):
                self._data = data

            def raise_for_status(self):
                pass

            def json(self):
                return self._data

        return Resp(self.payload)


@pytest.mark.asyncio
async def test_query_key_activity_success():
    payload = {"data": {"result": [{"value": [0, "3"]}]}}
    client = DummyClient(payload)
    result = await helpers.query_key_activity("key", client)
    assert result["metrics_active"]
    assert result["metrics_count"] == 3


@pytest.mark.asyncio
async def test_service_wrapper_methods():
    svc = AgentService()
    hb = AgentHeartbeat(name="a", tenant_id="t")
    svc.update_from_heartbeat(hb)
    agents = svc.list_agents()
    assert len(agents) == 1
    # test extract_metrics_count via service
    assert svc.extract_metrics_count({}) == 0
    client = DummyClient({"data": {"result": []}})
    result = await svc.key_activity("k", client)
    assert not result["metrics_active"]
    assert result["metrics_count"] == 0
