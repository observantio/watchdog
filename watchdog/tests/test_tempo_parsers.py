"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from tests._env import ensure_test_env
ensure_test_env()
from services.tempo import parsers as tempo_parsers
from models.observability.tempo_models import Span, Trace


def test_parse_attributes_and_span_and_trace():
    attrs = [
        {"key": "k1", "value": {"stringValue": "v1"}},
        {"key": "k2", "value": {"intValue": 42}},
    ]
    parsed = tempo_parsers.parse_attributes(attrs)
    assert parsed["k1"] == "v1"
    assert parsed["k2"] == 42

    span_data = {
        "spanId": "s1",
        "name": "op",
        "startTimeUnixNano": "1000000",
        "endTimeUnixNano": "2000000",
        "attributes": [{"key": "k1", "value": {"stringValue": "v1"}}],
    }
    span = tempo_parsers.parse_span(span_data, "t1", "proc", "svc", {"res": "x"})
    assert isinstance(span, Span)
    assert span.span_id == "s1"
    assert span.trace_id == "t1"
    assert span.service_name == "svc"
    assert span.attributes.get("k1") == "v1"

    trace_data = {
        "batches": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "svcA"}}]},
                "scopeSpans": [{"spans": [span_data]}],
            }
        ]
    }
    trace = tempo_parsers.parse_tempo_trace("t1", trace_data)
    assert isinstance(trace, Trace)
    assert len(trace.spans) == 1
    assert list(trace.processes.keys())[0] == "svcA"


def test_build_summary_trace_returns_trace_or_none():
    t = tempo_parsers.build_summary_trace({})
    assert t is None

    td = {"traceID": "tx", "startTimeUnixNano": "1000000", "durationMs": 5, "rootTraceName": "r", "rootServiceName": "svc"}
    s = tempo_parsers.build_summary_trace(td)
    assert isinstance(s, Trace)
    assert s.spans[0].operation_name == "r"
