import asyncio
import httpx
import time

import pytest

from services.loki_service import LokiService
from models.observability.loki_models import LogQuery
from config import config as _config


class FakeResponse:
    def __init__(self, payload=None, status=200):
        self._payload = payload or {}
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=httpx.Response(self.status_code))

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, behavior):
        self._behavior = behavior

    async def get(self, url, params=None, headers=None):
        result = self._behavior(url, params or {}, headers or {})
        if isinstance(result, Exception):
            raise result
        return FakeResponse(result)


def test_query_logs_instant_uses_fallback_candidates():
    async def _inner():
        s = LokiService(loki_url="http://loki")

        async def fake_timed_get_json(url, params=None, headers=None):
            return {'status': 'success', 'data': {'result': []}}

        async def fake_safe_get(url, *, params, headers, quiet=False):
            q = params.get('query', '')
            if 'service_name' in q or 'service' in q:
                return {
                    'status': 'success',
                    'data': {'result': [{'stream': {'app': 'app="web",region="us"'}, 'values': [["1", "m"]]}]}
                }
            return {'status': 'success', 'data': {'result': []}}

        s._timed_get_json = fake_timed_get_json
        s._safe_get_json = fake_safe_get

        resp = await s.query_logs_instant('{service.name="my"}')
        assert resp.status == 'success'
        assert resp.data.get('result')

    asyncio.run(_inner())


def test_with_retry_retries_on_transient_errors():
    async def _inner():
        s = LokiService(loki_url="http://loki")
        calls = {'c': 0}

        async def flaky_timed(url, params=None, headers=None):
            calls['c'] += 1
            if calls['c'] < 3:
                raise asyncio.TimeoutError()
            return {'status': 'success', 'data': {'result': [{'stream': {'app': 'web'}, 'values': [["1", "x"]]}]}}

        s._timed_get_json = flaky_timed

        class Q:
            def __init__(self, query):
                self.query = query
                self.limit = 10
                self.direction = type('D', (), {'value': 'FORWARD'})

        resp = await s.query_logs(Q('{}'))
        assert resp.status == 'success'
        assert calls['c'] >= 3

    asyncio.run(_inner())


def test_with_retry_does_not_retry_on_4xx():
    async def _inner():
        s = LokiService(loki_url="http://loki")

        async def fail_once(url, params=None, headers=None):
            raise httpx.HTTPStatusError("err", request=None, response=httpx.Response(400))

        s._timed_get_json = fail_once

        class Q:
            def __init__(self, query):
                self.query = query
                self.limit = 1
                self.direction = type('D', (), {'value': 'FORWARD'})

        resp = await s.query_logs(Q('{}'))
        # query_logs handles HTTP errors and returns an error response (no retry expected)
        assert resp.status == 'error'

    asyncio.run(_inner())


def test_get_label_values_concurrent_cache_dedup(monkeypatch):
    async def _inner():
        s = LokiService(loki_url="http://loki")
        calls = {'c': 0}

        async def slow_safe_get(url, *, params, headers, quiet=False):
            calls['c'] += 1
            await asyncio.sleep(0.02)
            return {'status': 'success', 'data': ['a', 'b']}

        s._safe_get_json = slow_safe_get

        async def worker():
            r = await s.get_label_values('app')
            return r.data

        tasks = [asyncio.create_task(worker()) for _ in range(8)]
        results = await asyncio.gather(*tasks)
        assert all(r == ['a', 'b'] for r in results)
        # the cache factory should only have been invoked once
        assert calls['c'] == 1

    asyncio.run(_inner())


def test_fallback_semaphore_respects_concurrency(monkeypatch):
    async def _inner():
        s = LokiService(loki_url="http://loki")

        # make aggregate_logs artificially slow and measure concurrent invocations
        concurrent = {'n': 0, 'max': 0}

        async def slow_aggregate(query_str, start=None, end=None, step=300, tenant_id="default"):
            concurrent['n'] += 1
            concurrent['max'] = max(concurrent['max'], concurrent['n'])
            await asyncio.sleep(0.02)
            concurrent['n'] -= 1
            return {'status': 'success', 'data': {'result': []}, 'query': query_str}

        s.aggregate_logs = slow_aggregate

        # force concurrency limit to 1 for the test
        monkeypatch.setattr(_config, 'LOKI_FALLBACK_CONCURRENCY', 1)

        # run get_log_volume which will spawn fallback aggregates
        await s.get_log_volume('{service.name="api"}', step=1)
        assert concurrent['max'] <= 1

    asyncio.run(_inner())
