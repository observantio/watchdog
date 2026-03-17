"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import asyncio
from tests._env import ensure_test_env
ensure_test_env()
from models.observability.tempo_models import TraceQuery
from services.tempo_service import TempoService, _dict_list

def test_search_traces_fetches_full_traces_with_concurrency():
    service = TempoService(tempo_url="http://tempo.test")

    async def fake_search(*args, **kwargs):
        return {"traces": [{"traceID": "t1"}, {"traceID": "t2"}, {"traceID": "t3"}]}

    inflight = 0
    max_inflight = 0

    async def fake_get_trace(trace_id, tenant_id="default"):
        nonlocal inflight, max_inflight
        inflight += 1
        max_inflight = max(max_inflight, inflight)
        await asyncio.sleep(0.03)
        inflight -= 1
        return {
            "traceID": trace_id,
            "spans": [],
            "processes": {},
            "warnings": None,
        }

    service._get_json = fake_search
    service.get_trace = fake_get_trace
    result = asyncio.run(service.search_traces(TraceQuery(limit=3), fetch_full_traces=True))
    assert result.total == 3
    assert len(result.data) == 3
    assert max_inflight > 1


def test_tempo_helper_and_list_response_paths(monkeypatch):
    assert _dict_list("bad") == []

    service = TempoService(tempo_url="http://tempo.test")

    async def tags_json(url, headers=None, params=None):
        return {"tagNames": ["service"]}

    monkeypatch.setattr(service, "_get_json", tags_json)

    class ServicesClient:
        async def get(self, url, headers=None, params=None):
            class Response:
                def raise_for_status(self):
                    return None

                def json(self):
                    return ["svc-b", None, "svc-a"]

            return Response()

    service._client = ServicesClient()
    assert asyncio.run(service.get_services("tenant-a")) == ["svc-a", "svc-b"]

    responses = iter([[], ["op-z"]])

    class OperationsClient:
        async def get(self, url, params=None, headers=None):
            payload = next(responses)

            class Response:
                def raise_for_status(self):
                    return None

                def json(self):
                    return payload

            return Response()

    service._client = OperationsClient()
    assert asyncio.run(service.get_operations("svc-a", tenant_id="tenant-a")) == ["op-z"]
