"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/testdb")
os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "False")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

from tests._env import ensure_test_env

ensure_test_env()

from models.observability.loki_models import LogDirection, LogQuery
from services.loki_service import LokiService, _json_dict, _object_list, _string_list


def test_loki_service_small_helpers_cover_fallback_types(monkeypatch):
    service = LokiService(loki_url="http://example")
    assert _json_dict({"x": 1}) == {"x": 1}
    assert _json_dict("bad") == {}
    assert _object_list([1, 2]) == [1, 2]
    assert _object_list({}) == []
    assert _string_list(["a", 1, "b"]) == ["a", "b"]
    assert _string_list("bad") == []
    assert service._headers("tenant-1") == {"X-Scope-OrgID": "tenant-1"}
    assert service._query_params(LogQuery(query="{}", limit=5, direction=LogDirection.FORWARD, start=1, end=2, step=None)) == {
        "query": "{}",
        "limit": 5,
        "direction": "forward",
        "start": 1,
        "end": 2,
    }
    monkeypatch.setattr("services.loki_service.time.time", lambda: 10)
    assert service._normalize_range_for_step(20, 20, 5) == (0, 5_000_000_000)


def test_calculate_stats_and_normalize_stream_labels_cover_invalid_payloads():
    service = LokiService(loki_url="http://example")
    assert service._calculate_stats({"result": []}) is None
    assert service._calculate_stats({"result": ["bad"]}).total_entries == 0
    assert service._calculate_stats({"result": [{"values": [["1", "a"], ["2", "bb"]]}]}).total_bytes == 3

    payload = {
        "result": [
            {"stream": {"app": 'app="web",env="prod",', "plain": "value"}},
            {"stream": "bad"},
            "skip",
        ]
    }
    service._normalize_stream_labels(payload)
    assert payload["result"][0]["stream"]["app"] == "web"
    assert payload["result"][0]["stream"]["env"] == "prod"
    assert payload["result"][0]["stream"]["plain"] == "value"


@pytest.mark.asyncio
async def test_get_or_build_volume_uses_cache_waiters_and_cleans_failures():
    service = LokiService(loki_url="http://example")
    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    async def builder():
        calls.append("build")
        started.set()
        await release.wait()
        return {"status": "success", "data": {"result": [1]}}

    first = asyncio.create_task(service._get_or_build_volume("key", builder))
    await started.wait()
    second = asyncio.create_task(service._get_or_build_volume("key", builder))
    release.set()
    assert await first == {"status": "success", "data": {"result": [1]}}
    assert await second == {"status": "success", "data": {"result": [1]}}
    assert calls == ["build"]
    assert await service._get_or_build_volume("key", builder) == {"status": "success", "data": {"result": [1]}}
    assert calls == ["build"]

    async def failing_builder():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await service._get_or_build_volume("fail", failing_builder)
    assert "fail" not in service._volume_inflight


@pytest.mark.asyncio
async def test_query_logs_covers_fallback_and_http_errors(monkeypatch):
    service = LokiService(loki_url="http://example")

    async def timed_get_json(_client, endpoint, params=None, headers=None):
        assert endpoint.endswith("/query_range")
        assert params["query"] == "{app=\"web\"}"
        assert headers["X-Scope-OrgID"] == "tenant-a"
        return {"status": "success", "data": {"result": []}}

    async def fallback(*args, **kwargs):
        return {
            "status": "success",
            "data": {"result": [{"stream": {"app": 'app="web",env="prod",'}, "values": [["1", "msg"]]}]},
        }

    monkeypatch.setattr(service._http, "timed_get_json", timed_get_json)
    monkeypatch.setattr("services.loki_service.run_fallback_queries", fallback)
    response = await service.query_logs(
        LogQuery(query='{app="web"}', limit=10, start=1, end=2, direction=LogDirection.BACKWARD, step=None),
        tenant_id="tenant-a",
    )
    assert response.status == "success"
    assert response.data["result"][0]["stream"]["app"] == "web"
    assert response.data["result"][0]["stream"]["env"] == "prod"
    assert service._metrics["loki_query_fallbacks_total"] == 1

    async def failing_timed_get_json(*args, **kwargs):
        raise httpx.HTTPError("network")

    monkeypatch.setattr(service._http, "timed_get_json", failing_timed_get_json)
    response = await service.query_logs(
        LogQuery(query="{}", limit=1, start=None, end=None, direction=LogDirection.BACKWARD, step=None)
    )
    assert response.status == "error"
    assert response.data["result"] == []
    assert service._metrics["loki_query_errors_total"] == 1


@pytest.mark.asyncio
async def test_query_logs_instant_get_labels_and_label_values_cover_error_paths(monkeypatch):
    service = LokiService(loki_url="http://example")

    async def timed_get_json(_client, endpoint, params=None, headers=None):
        if endpoint.endswith("/query"):
            return {"status": "success", "data": {"result": []}}
        raise AssertionError(endpoint)

    async def fallback(*args, **kwargs):
        return {"status": "success", "data": {"result": [{"stream": {"service_name": "api"}}]}}

    async def safe_get_json(_client, endpoint, params=None, headers=None, quiet=False):
        if endpoint.endswith("/labels"):
            return {"data": ["app", "env"]}
        if endpoint.endswith("/label/service_name/values"):
            return {"data": None}
        raise AssertionError(endpoint)

    async def query_logs(log_query, tenant_id="default"):
        assert log_query.query == "{service_name=~\".+\"}"
        return SimpleNamespace(data={"result": [{"stream": {"service_name": "api"}}, {"stream": {"service_name": "worker"}}]})

    monkeypatch.setattr(service._http, "timed_get_json", timed_get_json)
    monkeypatch.setattr(service._http, "safe_get_json", safe_get_json)
    monkeypatch.setattr("services.loki_service.run_fallback_queries", fallback)
    monkeypatch.setattr(service, "query_logs", query_logs)

    instant = await service.query_logs_instant("{app=\"web\"}", at_time=10, tenant_id="tenant-a", limit=2)
    assert instant.status == "success"
    assert instant.data["result"][0]["stream"]["service_name"] == "api"

    labels = await service.get_labels(start=1, end=2, tenant_id="tenant-a")
    assert labels.status == "success"
    assert labels.data == ["app", "env"]

    values = await service.get_label_values("service_name", query="not-a-selector", tenant_id="tenant-a")
    assert values.status == "success"
    assert values.data == ["api", "worker"]
    assert service._metrics["loki_query_fallbacks_total"] >= 1

    async def http_error_safe_get_json(*args, **kwargs):
        raise httpx.HTTPError("bad")

    monkeypatch.setattr(service._http, "safe_get_json", http_error_safe_get_json)
    labels_error = await service.get_labels()
    assert labels_error.status == "error"
    assert labels_error.data == []
    values_error = await service.get_label_values("service_name")
    assert values_error.status == "error"
    assert values_error.data == []


@pytest.mark.asyncio
async def test_aggregate_volume_search_and_filter_cover_remaining_branches(monkeypatch):
    service = LokiService(loki_url="http://example")

    async def timed_get_json(_client, endpoint, params=None, headers=None):
        assert endpoint.endswith("/query_range")
        return {"status": "success", "data": {"result": [{"values": [["1", "2"]]}]}}

    monkeypatch.setattr(service._http, "timed_get_json", timed_get_json)
    aggregated = await service.aggregate_logs("sum(rate({}[5m]))", start=1, end=2, step=60, tenant_id="tenant-a")
    assert aggregated["status"] == "success"
    assert aggregated["query"] == "sum(rate({}[5m]))"

    async def status_error(*args, **kwargs):
        response = httpx.Response(status_code=429, request=httpx.Request("GET", "http://example"))
        raise httpx.HTTPStatusError("too many", request=response.request, response=response)

    monkeypatch.setattr(service._http, "timed_get_json", status_error)
    aggregated_error = await service.aggregate_logs("sum(rate({}[5m]))")
    assert aggregated_error["status"] == "error"
    assert service._metrics["loki_query_errors_total"] >= 1

    async def aggregate_logs(query_str, start=None, end=None, step=300, tenant_id="default"):
        if "candidate-1" in query_str:
            return {"status": "success", "data": {"result": []}, "query": query_str}
        return {"status": "success", "data": {"result": [{"values": [["1", "5"]]}]}, "query": query_str}

    monkeypatch.setattr(service, "aggregate_logs", aggregate_logs)
    monkeypatch.setattr("services.loki_service.build_volume_fallback_queries", lambda query, max_queries: ["candidate-1", "candidate-2"])
    volume = await service.get_log_volume("{service_name=\"api\"}", start=5, end=5, step=60, tenant_id="tenant-a")
    assert volume["data"]["result"]

    captured: list[tuple[str, int]] = []

    async def query_logs(log_query, tenant_id="default"):
        captured.append((log_query.query, log_query.limit))
        return SimpleNamespace(status="success", data={"result": []})

    monkeypatch.setattr(service, "query_logs", query_logs)
    await service.search_logs_by_pattern('error "quoted"', labels={"app": "web"}, limit=12)
    await service.filter_logs({"app": "web"}, filters=["timeout", "5xx"], limit=7)
    assert captured[0][0] == '{app="web"} |= "error \\\"quoted\\\""'
    assert captured[0][1] == 12
    assert captured[1][0] == '{app="web"} |= "timeout" |= "5xx"'
    assert captured[1][1] == 7
