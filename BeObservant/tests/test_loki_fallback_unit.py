from __future__ import annotations

import asyncio

import httpx
import pytest

from tests._env import ensure_test_env

ensure_test_env()

from services.loki import fallback


def test_build_service_and_volume_fallback_queries_cover_variants_and_limits():
    query = '{service.name="payments", level="error"}'
    alias_query = '{service_name="payments"}'

    assert fallback._normalize_service_label('{app="web"}') == '{app="web"}'

    service_variants = fallback.build_service_fallback_queries(query)
    assert any('service_name="payments"' in item for item in service_variants)
    assert any('service.name=~"payments.*"' in item for item in service_variants)
    assert len(service_variants) == len(set(service_variants))

    volume_variants = fallback.build_volume_fallback_queries(query, max_candidates=10)
    assert volume_variants[0] == query
    assert '{service=~".+"}' in volume_variants

    alias_variants = fallback.build_volume_fallback_queries(alias_query, max_candidates=10)
    assert any('service="payments"' in item for item in alias_variants)

    limited_variants = fallback.build_volume_fallback_queries(query, max_candidates=2)
    assert len(limited_variants) == 2

    same_query = '{service="api"}'
    assert fallback.build_service_fallback_queries(same_query) == []
    assert fallback.build_volume_fallback_queries(same_query, max_candidates=0) == [same_query]


class FakeHttpClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def safe_get_json(self, client, url, *, params, headers, quiet=False):
        self.calls.append({"url": url, "params": dict(params), "headers": dict(headers), "quiet": quiet})
        response = self.responses.pop(0)
        if asyncio.iscoroutine(response):
            return await response
        if isinstance(response, Exception):
            raise response
        return response


async def _delayed(value, delay=0.01):
    await asyncio.sleep(delay)
    return value


@pytest.mark.asyncio
async def test_run_fallback_queries_returns_first_non_empty_result_and_ignores_non_dict_payloads():
    http_client = FakeHttpClient(
        [
            _delayed(["not-a-dict"], delay=0.02),
            _delayed({"data": {"result": []}}, delay=0.01),
            _delayed({"data": {"result": [{"stream": {"service_name": "payments"}}]}}, delay=0.0),
        ]
    )

    async with httpx.AsyncClient() as client:
        payload = await fallback.run_fallback_queries(
            "http://loki.test/loki/api/v1/query_range",
            {"limit": 10},
            {"X-Scope-OrgID": "tenant-1"},
            '{service.name="payments"}',
            client,
            http_client,
            max_fallbacks=3,
            concurrency=2,
        )

    assert payload == {"data": {"result": [{"stream": {"service_name": "payments"}}]}}
    assert all(call["quiet"] is True for call in http_client.calls)
    assert all(call["params"]["limit"] == 10 for call in http_client.calls)
    assert any(call["params"]["query"] != '{service.name="payments"}' for call in http_client.calls)


@pytest.mark.asyncio
async def test_run_fallback_queries_returns_none_when_no_candidates_or_no_hits():
    async with httpx.AsyncClient() as client:
        no_candidates_client = FakeHttpClient([])
        assert await fallback.run_fallback_queries(
            "http://loki.test/query",
            {"limit": 5},
            {},
            '{service="api"}',
            client,
            no_candidates_client,
            max_fallbacks=0,
        ) is None
        assert no_candidates_client.calls == []

        http_client = FakeHttpClient([
            {"data": {"result": []}},
            None,
            {"data": "bad"},
        ])
        assert await fallback.run_fallback_queries(
            "http://loki.test/query",
            {"limit": 5},
            {},
            '{service.name="api"}',
            client,
            http_client,
            max_fallbacks=3,
            concurrency=1,
        ) is None