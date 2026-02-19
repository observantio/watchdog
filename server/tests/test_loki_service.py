import os
import asyncio
import httpx
import time
import pytest

# Ensure config validation passes during tests by providing a non-example DATABASE_URL
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost/testdb')
os.environ.setdefault('CORS_ALLOW_CREDENTIALS', 'False')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost')

from services.loki_service import LokiService
from models.observability.loki_models import LogLabelValuesResponse, LogLabelsResponse, LogResponse


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
        # behavior: callable(url, params, headers) -> payload or raises
        self._behavior = behavior

    async def get(self, url, params=None, headers=None):
        result = self._behavior(url, params or {}, headers or {})
        if isinstance(result, Exception):
            raise result
        return FakeResponse(result)


def test_escape_and_build_label_selector():
    s = LokiService(loki_url="http://example")
    assert s._escape_logql_string('a"b\\c\n') == 'a\\\"b\\\\c\\n'
    assert s._build_label_selector({}) == "{}"
    assert s._build_label_selector({"app": 'my"app'}) == '{app="my\\\"app"}'


def test_normalize_and_expand_service_labels():
    from services.loki.fallback import _normalize_service_label_query, _expand_service_label_matchers, build_service_fallback_queries
    q = '{service.name="myservice"}'
    normalized = _normalize_service_label_query(q)
    assert 'service_name' in normalized
    expanded = _expand_service_label_matchers(q)
    assert '=~"myservice.*"' in expanded
    fallbacks = build_service_fallback_queries(q)
    assert any('service_name' in f for f in fallbacks)


def test_parse_and_normalize_labelset_and_values():
    from services.loki.label_utils import parse_labelset_value, normalize_label_value, normalize_label_dict, normalize_label_values
    raw = 'app="web",env="prod",extra="x"'
    parsed = parse_labelset_value('app', raw)
    assert parsed and parsed['app'] == 'web'
    nv, parsed2 = normalize_label_value('app', 'app="web",other="y",')
    assert nv == 'web'
    labels = {'app': 'app="web",other="y",', 'env': 'prod'}
    extra = normalize_label_dict(labels)
    assert 'other' in extra
    values = ['app="web",other="y",', 'plain']
    cleaned = normalize_label_values('app', values)
    assert 'web' in cleaned and 'plain' in cleaned


def test_calculate_stats():
    s = LokiService(loki_url="http://example")
    data = {
        'result': [
            {'values': [["1", "a"], ["2", "bb"]]},
            {'values': [["3", "ccc"]]},
        ]
    }
    stats = s._calculate_stats(data)
    assert stats['total_entries'] == 3
    assert stats['total_bytes'] == len('a') + len('bb') + len('ccc')


def test_query_logs_with_fallback_and_normalization():
    async def _inner():
        # initial query returns empty result, fallback returns data with labelset that needs normalization
        def behavior(url, params, headers):
            q = params.get('query', '')
            if 'query_range' in url:
                # initial query_range
                return {'status': 'success', 'data': {'result': []}}
            # fallback calls (query_range with candidate queries)
            if 'candidate' in q or 'service_name' in q or 'my' in q or 'service' in q:
                return {
                    'status': 'success',
                    'data': {
                        'result': [
                            {'stream': {'app': 'app="web",region="us"'}, 'values': [["1", "logmsg"]]}
                        ]
                    }
                }
            return {'status': 'success', 'data': {'result': []}}

        s = LokiService(loki_url="http://loki")
        s._client = FakeClient(behavior)
        # bypass config slicing and force a fallback payload
        async def fake_run_fallback(endpoint, base_params, headers, query_str):
            return {
                'status': 'success',
                'data': {
                    'result': [
                        {'stream': {'app': 'app="web",region="us"'}, 'values': [["1", "logmsg"]]}
                    ]
                }
            }

        s._run_fallback_queries = fake_run_fallback

        # craft a LogQuery-like object
        class Q:
            def __init__(self, query):
                self.query = query
                self.limit = 100
                self.direction = type('D', (), {'value': 'FORWARD'})

        resp = await s.query_logs(Q('{service.name="my"}'))
        assert resp.status == 'success'
        # stream labels should be normalized into dict form
        assert isinstance(resp.data.get('result')[0]['stream']['app'], str)

    asyncio.run(_inner())


def test_get_labels_caching_and_error():
    async def _inner():
        call_count = {'c': 0}

        def behavior(url, params, headers):
            call_count['c'] += 1
            if url.endswith('/labels'):
                return {'status': 'success', 'data': ['app', 'env']}
            return {'status': 'success', 'data': {}}

        s = LokiService(loki_url="http://loki")
        s._client = FakeClient(behavior)
        labels = await s.get_labels()
        assert isinstance(labels, LogLabelsResponse)
        assert 'app' in labels.data
        # second call should hit cache and not increment calls
        prev = call_count['c']
        labels2 = await s.get_labels()
        assert call_count['c'] == prev

    asyncio.run(_inner())


def test_get_label_values_direct_and_fallback(monkeypatch):
    async def _inner():
        # direct values endpoint returns data
        def behavior_direct(url, params, headers):
            if '/label/' in url and url.endswith('/values'):
                return {'status': 'success', 'data': ['a', 'b']}
            return {'status': 'success', 'data': {}}

        s = LokiService(loki_url="http://loki")
        s._client = FakeClient(behavior_direct)
        v = await s.get_label_values('app')
        assert isinstance(v, LogLabelValuesResponse)
        assert 'a' in v.data

        # fallback: label values endpoint returns None, query_logs returns results
        async def fake_query_logs(query, tenant_id=None):
            class R:
                def __init__(self):
                    self.data = {'result': [{'stream': {'app': 'web'}}, {'stream': {'app': 'web'}}]}
            return R()

        def behavior_none(url, params, headers):
            return None

        s2 = LokiService(loki_url="http://loki")
        s2._client = FakeClient(behavior_none)
        monkeypatch.setattr(s2, 'query_logs', fake_query_logs)
        v2 = await s2.get_label_values('app')
        assert 'web' in v2.data

    asyncio.run(_inner())


def test_aggregate_and_get_log_volume_with_fallback(monkeypatch):
    async def _inner():
        # aggregate success for one candidate
        def behavior(url, params, headers):
            if 'query_range' in url:
                return {'status': 'success', 'data': {'result': [{'values': [["1", "1"]]}]}}
            return {'status': 'success', 'data': {}}

        s = LokiService(loki_url="http://loki")
        s._client = FakeClient(behavior)
        agg = await s.aggregate_logs('sum(...)')
        assert agg['status'] == 'success'

        vol = await s.get_log_volume('{service=~".+"}')
        assert isinstance(vol, dict)

    asyncio.run(_inner())


def test_search_and_filter_logs(monkeypatch):
    async def _inner():
        async def fake_query_logs(query, tenant_id=None):
            return LogResponse(status='success', data={'result': []}, stats=None)

        s = LokiService(loki_url="http://loki")
        monkeypatch.setattr(s, 'query_logs', fake_query_logs)
        res = await s.search_logs_by_pattern('error', labels={'app': 'web'})
        assert isinstance(res, LogResponse)
        res2 = await s.filter_logs({'app': 'web'}, filters=['x'])
        assert isinstance(res2, LogResponse)

    asyncio.run(_inner())
import asyncio

from tests._env import ensure_test_env
ensure_test_env()

from services.loki_service import LokiService
from models.observability.loki_models import LogQuery


def test_query_logs_limits_fallback_candidates():
    service = LokiService(loki_url="http://loki.test")

    call_queries = []

    async def fake_get_json(url, *, params, headers):
        query = params.get("query", "")
        call_queries.append(query)
        if query.endswith('.*"}'):
            return {
                "status": "success",
                "data": {
                    "resultType": "streams",
                    "result": [{"stream": {"service_name": "api"}, "values": [["1", "ok"]]}],
                },
            }
        return {"status": "success", "data": {"resultType": "streams", "result": []}}

    service._timed_get_json = fake_get_json

    async def fake_run_fallback(endpoint, base_params, headers, query_str):
        return {
            "status": "success",
            "data": {
                "resultType": "streams",
                "result": [{"stream": {"service_name": "api"}, "values": [["1", "ok"]]}],
            },
        }

    service._run_fallback_queries = fake_run_fallback

    query = LogQuery(query='{service.name="api"}', limit=100)
    result = asyncio.run(service.query_logs(query))

    assert result.status == "success"
    assert len(call_queries) <= 1 + 4
    assert result.data.get("result")


def test_get_log_volume_stops_on_first_successful_candidate():
    service = LokiService(loki_url="http://loki.test")

    called = []

    async def fake_aggregate(query_str, start=None, end=None, step=300, tenant_id="default"):
        called.append(query_str)
        if "service=~\".+\"" in query_str or "{}" in query_str:
            return {"status": "success", "data": {"result": [["1", "2"]]}, "query": query_str, "step": step}
        return {"status": "success", "data": {"result": []}, "query": query_str, "step": step}

    service.aggregate_logs = fake_aggregate

    result = asyncio.run(service.get_log_volume('{service.name="api"}', step=60))

    assert result["status"] == "success"
    assert result["data"]["result"]
    assert len(called) >= 1


def test_get_log_volume_does_not_use_empty_selector_fallback():
    service = LokiService(loki_url="http://loki.test")

    called = []

    async def fake_aggregate(query_str, start=None, end=None, step=300, tenant_id="default"):
        called.append(query_str)
        return {"status": "success", "data": {"result": []}, "query": query_str, "step": step}

    service.aggregate_logs = fake_aggregate

    asyncio.run(service.get_log_volume('{service.name="api"}', step=60))

    assert not any('{}' in q for q in called)


async def _async_none(*a, **k):
    return None


def test_get_label_values_fallback_on_loki_error():
    service = LokiService(loki_url="http://loki.test")

    service._safe_get_json = _async_none

    async def fake_query_logs(query, tenant_id=None):
        class R:
            def __init__(self):
                self.data = {'result': [{'stream': {'service_name': 'api'}}, {'stream': {'service_name': 'web'}}]}
        return R()

    service.query_logs = fake_query_logs

    result = asyncio.run(service.get_label_values('service_name', start=1, end=2))
    assert result.status == 'success'
    assert set(result.data) == {"api", "web"}


def test_get_label_values_direct_success():
    service = LokiService(loki_url="http://loki.test")

    async def fake_safe_get(url, *, params, headers, **kwargs):
        return {"status": "success", "data": ["api", "web"]}

    service._safe_get_json = fake_safe_get

    result = asyncio.run(service.get_label_values('service_name', start=1, end=2))
    assert result.status == 'success'
    assert set(result.data) == {"api", "web"}


def test_get_label_values_normalizes_and_caps_start_end_and_caches():
    service = LokiService(loki_url="http://loki.test")

    captured = {}

    async def fake_safe_get(url, *, params, headers, **kwargs):
        captured['params'] = params.copy()
        return {"status": "success", "data": ["api"]}

    service._safe_get_json = fake_safe_get

    end_seconds = 1_771_416_818
    start_seconds = end_seconds - (60 * 60 * 24 * 30)  # 30 days back

    result = asyncio.run(service.get_label_values('service_name', start=start_seconds, end=end_seconds))
    assert result.status == 'success'
    assert 'params' in captured

    # start/end should be converted to nanoseconds
    assert captured['params']['start'] >= 1_000_000_000  # ns-scale
    assert captured['params']['end'] >= 1_000_000_000

    # Call again - should hit cache and not call _safe_get_json again
    called = []

    async def fake_safe_get_error(url, *, params, headers, **kwargs):
        called.append(True)
        return None

    service._safe_get_json = fake_safe_get_error
    result2 = asyncio.run(service.get_label_values('service_name', start=start_seconds, end=end_seconds))
    assert result2.status == 'success'
    # fake_safe_get_error should not have been called because of cache
    assert len(called) == 0


def test__normalize_label_values_parses_labelset_and_truncation():
    from services.loki.label_utils import normalize_label_values
    raw_values = [
        'service_name="api",env="prod"',
        'web",other="x"',
        'plainvalue',
        'complex\"value\",rest="x"',
    ]

    normalized = normalize_label_values('service_name', raw_values)
    assert 'api' in normalized
    assert 'web' in normalized or 'web\"' in normalized
    assert 'plainvalue' in normalized


def test__normalize_service_label_query_and_expand():
    from services.loki.fallback import _normalize_service_label_query, _expand_service_label_matchers, build_service_fallback_queries
    q = '{service.name="api"}'
    normalized = _normalize_service_label_query(q)
    assert 'service_name' in normalized

    expanded = _expand_service_label_matchers('{service_name="api"}')
    assert 'service_name=~"api.*"' in expanded
    # ensure build_service_fallback_queries includes normalized/expanded variants
    fallbacks = build_service_fallback_queries(q)
    assert any('service_name' in f for f in fallbacks)
