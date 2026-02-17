"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


import asyncio

from tests._env import ensure_test_env
ensure_test_env()

from services.loki_service import LokiService
from models.observability.loki_models import LogResponse


def test_build_label_selector_escapes_special_chars():
    s = LokiService(loki_url="http://example")
    selector = s._build_label_selector({'app': 'nginx"evil', 'env': 'prod\\dev'})
    assert 'app="nginx\\"evil"' in selector or 'app="nginx\"evil"' in selector
    assert 'env="prod\\\\dev"' in selector or 'env="prod\\dev"' in selector


def test_search_logs_by_pattern_escapes_pattern():
    s = LokiService(loki_url="http://example")
    captured = {}

    async def fake_query_logs(query, tenant_id='default'):
        captured['query'] = query.query
        return LogResponse(status='success', data={'result': []}, stats=None)

    s.query_logs = fake_query_logs
    asyncio.run(s.search_logs_by_pattern(pattern='bad "quote" and \\back', labels={'app': 'x'}))

    assert '\\"quote\\"' in captured['query'] or '\\"quote\"' in captured['query']
    assert '\\\\back' in captured['query'] or '\\back' in captured['query']


def test_filter_logs_escapes_filters():
    s = LokiService(loki_url="http://example")
    captured = {}

    async def fake_query_logs(query, tenant_id='default'):
        captured['query'] = query.query
        return LogResponse(status='success', data={'result': []}, stats=None)

    s.query_logs = fake_query_logs
    asyncio.run(s.filter_logs(labels={'app': 'x'}, filters=['err "x"', 'path\\to'], limit=1))

    assert '\\"x\\"' in captured['query'] or '\\"x\"' in captured['query']
    assert '\\\\to' in captured['query'] or '\\to' in captured['query']
