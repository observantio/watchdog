"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx

from services.grafana.normalize import normalize_grafana_next_path
from services.loki.http_client import LokiHttpClient


class ResponseStub:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://loki")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("bad", request=request, response=response)

    def json(self):
        return self._payload


class ClientStub:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc

    async def get(self, url, params=None, headers=None):
        if self.exc:
            raise self.exc
        return self.response


def test_normalize_grafana_next_path_variants():
    assert normalize_grafana_next_path(None) == "/dashboards"
    assert normalize_grafana_next_path("  ") == "/dashboards"
    assert normalize_grafana_next_path("https://evil.test") == "/dashboards"
    assert normalize_grafana_next_path("//evil.test") == "/dashboards"
    assert normalize_grafana_next_path("explore") == "/explore"
    assert normalize_grafana_next_path("/grafana") == "/dashboards"
    assert normalize_grafana_next_path("/grafana/explore") == "/explore"


def test_loki_http_client_success_and_error_paths():
    client = LokiHttpClient()

    payload = asyncio.run(
        client.timed_get_json(
            ClientStub(response=ResponseStub({"data": 1})),
            "https://loki",
            params={"q": "x"},
            headers={},
        )
    )
    assert payload == {"data": 1}
    assert client._metrics["loki_query_total"] == 1.0
    assert client._metrics["loki_query_duration_sum_seconds"] >= 0.0

    non_dict = asyncio.run(
        client.timed_get_json(
            ClientStub(response=ResponseStub([1, 2, 3])),
            "https://loki",
            params={"q": "x"},
            headers={},
        )
    )
    assert non_dict == {}

    status_result = asyncio.run(
        client.safe_get_json(
            ClientStub(response=ResponseStub({}, status_code=404)),
            "https://loki",
            params={"q": "x"},
            headers={},
            quiet=True,
        )
    )
    assert status_result is None

    request = httpx.Request("GET", "https://loki")
    http_error = httpx.ConnectError("boom", request=request)
    error_result = asyncio.run(
        client.safe_get_json(
            ClientStub(exc=http_error),
            "https://loki",
            params={"q": "x"},
            headers={},
        )
    )
    assert error_result is None
    assert client._metrics["loki_query_errors_total"] == 2.0
