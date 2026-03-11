"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio
import json
import types

import httpx
import pytest
from fastapi import HTTPException

from tests._env import ensure_test_env

ensure_test_env()

from models.observability.tempo_models import Trace, TraceQuery, TraceResponse
from routers.observability import tempo_router
from services import tempo_service as tempo_service_module


def _trace(trace_id: str, service_name: str = "svc", operation_name: str = "op") -> Trace:
    return Trace.model_validate(
        {
            "traceID": trace_id,
            "spans": [
                {
                    "spanID": f"{trace_id}-span",
                    "traceID": trace_id,
                    "parentSpanID": None,
                    "operationName": operation_name,
                    "startTime": 1,
                    "duration": 2,
                    "tags": [],
                    "serviceName": service_name,
                    "attributes": {},
                    "processID": service_name,
                    "warnings": None,
                }
            ],
            "processes": {},
            "warnings": None,
        }
    )


@pytest.mark.asyncio
async def test_tempo_service_helpers_and_get_json(monkeypatch):
    service = tempo_service_module.TempoService("http://tempo.test/")
    assert service.tempo_url == "http://tempo.test"
    assert service._get_headers("tenant-a") == {"X-Scope-OrgID": "tenant-a"}
    assert tempo_service_module._json_dict([]) == {}
    assert tempo_service_module._dict_list([{"a": 1}, 2]) == [{"a": 1}]
    assert tempo_service_module._string_list([1, None, "x"]) == ["1", "x"]
    assert tempo_service_module._escape_traceql('svc"x\\y') == 'svc\\"x\\\\y'

    class Response:
        content = b"{}"

        def raise_for_status(self):
            return None

        def json(self):
            return ["bad"]

    class Client:
        async def get(self, url, params=None, headers=None):
            return Response()

    perf_values = iter([10.0, 10.5])
    monkeypatch.setattr(tempo_service_module.time, "perf_counter", lambda: next(perf_values))
    service._client = Client()
    assert await service._get_json("http://tempo.test/api/search") == {}
    assert service._metrics["tempo_search_total"] == 1.0
    assert service._metrics["tempo_search_duration_sum_seconds"] == 0.5

    class FailingClient:
        async def get(self, url, params=None, headers=None):
            raise RuntimeError("boom")

    perf_values = iter([20.0, 20.25])
    monkeypatch.setattr(tempo_service_module.time, "perf_counter", lambda: next(perf_values))
    service._client = FailingClient()
    with pytest.raises(RuntimeError, match="boom"):
        await service._get_json("http://tempo.test/api/search")
    assert service._metrics["tempo_search_errors_total"] == 1.0

    closed = []

    class ClosingClient:
        async def aclose(self):
            closed.append(True)

    service._client = ClosingClient()
    await service.aclose()
    assert closed == [True]


@pytest.mark.asyncio
async def test_tempo_service_public_api_edges(monkeypatch):
    service = tempo_service_module.TempoService("http://tempo.test")

    class AsyncCache:
        async def get_or_set(self, key, func, ttl):
            return await func()

    service._services_cache = AsyncCache()

    monkeypatch.setattr(
        tempo_service_module.tempo_parsers,
        "build_summary_trace",
        lambda raw: _trace(raw["traceID"], service_name="summary-svc") if raw.get("traceID") else None,
    )
    monkeypatch.setattr(
        service,
        "_get_json",
        lambda url, params=None, headers=None: asyncio.sleep(0, result={"traces": [{"traceID": "t-1"}, {}, {"traceID": ""}]})
    )
    summary = await service.search_traces(TraceQuery(limit=3), fetch_full_traces=False)
    assert summary.total == 1
    assert summary.data[0].trace_id == "t-1"

    monkeypatch.setattr(
        service,
        "_get_json",
        lambda url, params=None, headers=None: (_ for _ in ()).throw(httpx.ReadError("down")),
    )
    errored = await service.search_traces(TraceQuery(limit=2), fetch_full_traces=False)
    assert errored.total == 0
    assert errored.errors == ["down"]

    class EmptyResponse:
        content = b""

        def raise_for_status(self):
            return None

    class JsonErrorResponse:
        content = b"not-json"

        def raise_for_status(self):
            return None

        def json(self):
            raise json.JSONDecodeError("bad", "x", 0)

    class DictResponse:
        content = b"{}"

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    responses = iter([
        EmptyResponse(),
        JsonErrorResponse(),
        DictResponse({"traceID": "missing-batches"}),
        DictResponse({"batches": []}),
    ])

    class TraceClient:
        async def get(self, url, headers=None, params=None):
            return next(responses)

    service._client = TraceClient()
    monkeypatch.setattr(tempo_service_module.tempo_parsers, "parse_tempo_trace", lambda trace_id, data: _trace(trace_id, "parsed-svc"))
    assert await service.get_trace("a") is None
    assert await service.get_trace("b") is None
    assert await service.get_trace("c") is None
    parsed = await service.get_trace("d")
    assert parsed is not None and parsed.spans[0].service_name == "parsed-svc"

    class FailingTraceClient:
        async def get(self, url, headers=None, params=None):
            raise httpx.ReadError("trace failed")

    service._client = FailingTraceClient()
    assert await service.get_trace("e") is None

    async def full_search_json(url, params=None, headers=None):
        return {"traces": [{"traceID": "good"}, {"traceID": "bad"}]}

    async def fetch_full_trace(trace_id, tenant_id="default"):
        if trace_id == "bad":
            raise httpx.ReadError("missing")
        return _trace(trace_id, "svc-full")

    monkeypatch.setattr(service, "_get_json", full_search_json)
    monkeypatch.setattr(service, "get_trace", fetch_full_trace)
    full = await service.search_traces(TraceQuery(limit=2), fetch_full_traces=True)
    assert full.total == 2
    assert full.data[0].trace_id == "good"
    assert full.data[1].warnings == ["Trace details unavailable"]

    calls = []

    async def get_json_services(url, headers=None, params=None):
        calls.append((url, headers, params))
        return {"data": {"tagNames": ["ignored", "service"]}}

    async def infer_services(*args, **kwargs):
        return TraceResponse.model_validate({"data": [_trace("t1", "svc-b"), _trace("t2", "svc-a")], "total": 2, "limit": 50, "offset": 0})

    monkeypatch.setattr(service, "_get_json", get_json_services)
    monkeypatch.setattr(service, "search_traces", infer_services)

    class TagValuesClient:
        async def get(self, url, headers=None, params=None):
            raise httpx.ReadError("tag failure")

    service._client = TagValuesClient()
    assert await service.get_services("tenant-a") == ["svc-a", "svc-b"]

    class MixedTagValuesClient:
        async def get(self, url, headers=None, params=None):
            class ValueResponse:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"tagValues": [{"value": "svc-c"}, {"tagValue": "svc-d"}, {"value": ""}, "svc-e"]}

            return ValueResponse()

    service._client = MixedTagValuesClient()
    assert await service.get_services("tenant-a") == ["svc-c", "svc-d", "svc-e"]

    async def broken_get_json(url, headers=None, params=None):
        raise httpx.ReadError("tags down")

    monkeypatch.setattr(service, "_get_json", broken_get_json)
    assert await service.get_services("tenant-a") == []

    async def empty_tag_json(url, headers=None, params=None):
        return {"tagNames": []}

    async def broken_service_search(*args, **kwargs):
        raise RuntimeError("infer failed")

    monkeypatch.setattr(service, "_get_json", empty_tag_json)
    monkeypatch.setattr(service, "search_traces", broken_service_search)
    assert await service.get_services("tenant-a") == []

    op_responses = iter([
        httpx.ReadError("first failed"),
        ["op-b", "op-a", "op-b"],
    ])

    class OperationsClient:
        async def get(self, url, params=None, headers=None):
            response = next(op_responses)
            if isinstance(response, Exception):
                raise response

            class ValueResponse:
                def raise_for_status(self):
                    return None

                def json(self):
                    return response

            return ValueResponse()

    service._client = OperationsClient()
    assert await service.get_operations('svc"x', tenant_id="tenant-a") == ["op-a", "op-b"]

    class DictOperationsClient:
        async def get(self, url, params=None, headers=None):
            class ValueResponse:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"data": ["op-c", None, "op-a"]}

            return ValueResponse()

    service._client = DictOperationsClient()
    assert await service.get_operations("svc-y") == ["op-a", "op-c"]

    async def fallback_ops(*args, **kwargs):
        return TraceResponse.model_validate({"data": [_trace("t3", "svc-x", "op-z"), _trace("t4", "svc-x", "op-a")], "total": 2, "limit": 50, "offset": 0})

    monkeypatch.setattr(service, "search_traces", fallback_ops)

    class NoOperationsClient:
        async def get(self, url, params=None, headers=None):
            raise httpx.ReadError("none")

    service._client = NoOperationsClient()
    assert await service.get_operations("svc-x") == ["op-a", "op-z"]

    async def broken_operations_fallback(*args, **kwargs):
        raise RuntimeError("ops failed")

    monkeypatch.setattr(service, "search_traces", broken_operations_fallback)
    assert await service.get_operations("svc-x") == []


@pytest.mark.asyncio
async def test_tempo_router_edges(monkeypatch):
    tenant_calls = []

    async def fake_resolve_tenant_id(request, current_user):
        tenant_calls.append((request.url.path, current_user))
        return "tenant-a"

    search_calls = []
    monkeypatch.setattr(tempo_router, "resolve_tenant_id", fake_resolve_tenant_id)
    monkeypatch.setattr(
        tempo_router,
        "tempo_service",
        types.SimpleNamespace(
            search_traces=lambda query, tenant_id, fetch_full_traces: search_calls.append((query, tenant_id, fetch_full_traces)) or asyncio.sleep(0, result=TraceResponse.model_validate({"data": [_trace("t1")], "total": 1, "limit": query.limit, "offset": 0})),
            get_trace=lambda trace_id, tenant_id: asyncio.sleep(0, result=_trace(trace_id)),
            get_services=lambda tenant_id: asyncio.sleep(0, result=["svc-a"]),
            get_operations=lambda service, tenant_id: asyncio.sleep(0, result=["op-a"]),
            aclose=lambda: asyncio.sleep(0),
        ),
    )

    user = types.SimpleNamespace()
    request = types.SimpleNamespace(url=types.SimpleNamespace(path="/api/tempo/traces/search"))
    search_result = await tempo_router.search_traces(request, service="svc", operation="op", min_duration="1ms", max_duration="2ms", start=1, end=2, limit=7, fetch_full=True, current_user=user)
    assert search_result.total == 1
    built_query, tenant_id, fetch_full = search_calls[0]
    assert built_query.service == "svc"
    assert built_query.operation == "op"
    assert built_query.min_duration == "1ms"
    assert built_query.max_duration == "2ms"
    assert tenant_id == "tenant-a"
    assert fetch_full is True

    trace = await tempo_router.get_trace("trace-a", request, current_user=user)
    assert trace.trace_id == "trace-a"
    assert await tempo_router.get_services(request, current_user=user) == ["svc-a"]
    assert await tempo_router.get_operations("svc-a", request, current_user=user) == ["op-a"]
    assert len(tenant_calls) == 4


@pytest.mark.asyncio
async def test_tempo_router_timeout_and_lifespan_edges(monkeypatch):
    async def fake_resolve_tenant_id(request, current_user):
        return "tenant-a"

    async def timeout_search(*args, **kwargs):
        raise asyncio.TimeoutError()

    async def timeout_trace(*args, **kwargs):
        raise asyncio.TimeoutError()

    async def timeout_services(*args, **kwargs):
        raise asyncio.TimeoutError()

    async def timeout_operations(*args, **kwargs):
        raise asyncio.TimeoutError()

    closed = []
    monkeypatch.setattr(tempo_router, "resolve_tenant_id", fake_resolve_tenant_id)
    monkeypatch.setattr(
        tempo_router,
        "tempo_service",
        types.SimpleNamespace(
            search_traces=timeout_search,
            get_trace=lambda trace_id, tenant_id: asyncio.sleep(0, result=None),
            get_services=timeout_services,
            get_operations=timeout_operations,
            aclose=lambda: closed.append(True) or asyncio.sleep(0),
        ),
    )

    request = types.SimpleNamespace(url=types.SimpleNamespace(path="/api/tempo"))
    user = types.SimpleNamespace()

    with pytest.raises(HTTPException, match="Tempo search timed out"):
        await tempo_router.search_traces(
            request,
            service=None,
            operation=None,
            min_duration=None,
            max_duration=None,
            start=None,
            end=None,
            limit=20,
            fetch_full=False,
            current_user=user,
        )

    monkeypatch.setattr(tempo_router.tempo_service, "get_trace", timeout_trace)
    with pytest.raises(HTTPException, match="Tempo trace lookup timed out for trace-a"):
        await tempo_router.get_trace("trace-a", request, current_user=user)

    monkeypatch.setattr(tempo_router.tempo_service, "get_trace", lambda trace_id, tenant_id: asyncio.sleep(0, result=None))
    with pytest.raises(HTTPException, match="Trace trace-a not found"):
        await tempo_router.get_trace("trace-a", request, current_user=user)

    with pytest.raises(HTTPException, match="Tempo services lookup timed out"):
        await tempo_router.get_services(request, current_user=user)

    with pytest.raises(HTTPException, match="Tempo operations lookup timed out for service svc-a"):
        await tempo_router.get_operations("svc-a", request, current_user=user)

    async with tempo_router.lifespan(types.SimpleNamespace()):
        pass
    assert closed == [True]