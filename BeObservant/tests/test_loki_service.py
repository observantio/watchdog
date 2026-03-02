"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import os
import asyncio
import httpx

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost/testdb')
os.environ.setdefault('CORS_ALLOW_CREDENTIALS', 'False')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost')

from tests._env import ensure_test_env
ensure_test_env()

from models.observability.loki_models import LogQuery
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
        self._behavior = behavior

    async def get(self, url, params=None, headers=None):
        result = self._behavior(url, params or {}, headers or {})
        if isinstance(result, Exception):
            raise result
        return FakeResponse(result)


def test_escape_and_build_label_selector():
    s = LokiService(loki_url="http://example")
    assert s._escape_logql('a"b\\c\n') == 'a\\\"b\\\\c\\n'
    assert s._label_selector({}) == "{}"
    assert s._label_selector({"app": 'my"app'}) == '{app="my\\\"app"}'


def test_normalize_and_expand_service_labels():
    from services.loki.fallback import _normalize_service_label, _expand_exact_to_prefix, build_service_fallback_queries
    q = '{service.name="myservice"}'
    assert 'service_name' in _normalize_service_label(q)
    assert '=~"myservice.*"' in _expand_exact_to_prefix(q)
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
    assert stats is not None
   
    assert stats.total_entries == 3
    assert stats.total_bytes == len('a') + len('bb') + len('ccc')

