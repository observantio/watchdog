"""
Tempo parsers for processing trace responses from Tempo, providing functions to extract
and normalize trace and span data into application models.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import Any, Dict, List, Optional

from models.observability.tempo_models import Span, SpanAttribute, Trace

SERVICE_NAME_KEY = "service.name"
SERVICE_ALIAS_KEY = "service"
OTLP_VALUE_TYPES = ("stringValue", "intValue", "boolValue", "doubleValue")


def parse_attributes(attrs: List[Dict[str, Any]]) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {}
    for attr in attrs or []:
        key = attr.get("key", "")
        if not key:
            continue
        value = attr.get("value", {})
        for val_type in OTLP_VALUE_TYPES:
            if val_type in value:
                parsed[key] = value[val_type]
                break
    return parsed


def parse_span(
    span_data: Dict[str, Any],
    trace_id: str,
    process_id: str,
    service_name: Optional[str],
    resource_attrs: Optional[Dict[str, Any]] = None,
) -> Span:
    attr_map = parse_attributes(span_data.get("attributes", []))
    tags = [SpanAttribute(key=k, value=v) for k, v in attr_map.items()]

    if service_name and SERVICE_NAME_KEY not in attr_map:
        attr_map[SERVICE_NAME_KEY] = service_name
        tags.append(SpanAttribute(key=SERVICE_NAME_KEY, value=service_name))

    if resource_attrs:
        for k, v in resource_attrs.items():
            attr_map.setdefault(k, v)

    start_time = int(span_data.get("startTimeUnixNano") or 0) // 1000
    end_time = int(span_data.get("endTimeUnixNano") or 0) // 1000
    parent_span_id = span_data.get("parentSpanId") or None

    return Span.model_validate({
        "spanID": span_data.get("spanId", ""),
        "traceID": trace_id,
        "parentSpanID": parent_span_id,
        "operationName": span_data.get("name", ""),
        "startTime": start_time,
        "duration": end_time - start_time,
        "tags": [{"key": t.key, "value": t.value} for t in tags],
        "serviceName": service_name,
        "attributes": attr_map,
        "processID": process_id,
        "warnings": None,
    })


def parse_tempo_trace(trace_id: str, data: Dict[str, Any]) -> Trace:
    spans: List[Span] = []
    processes: Dict[str, Any] = {}

    for batch in data.get("batches") or []:
        resource_attrs = parse_attributes(batch.get("resource", {}).get("attributes", []))
        service_name = (
            resource_attrs.get(SERVICE_NAME_KEY)
            or resource_attrs.get(SERVICE_ALIAS_KEY)
            or resource_attrs.get("serviceName")
            or "unknown"
        )
        process_id = str(service_name)
        processes[process_id] = {
            "serviceName": service_name,
            "resource": batch.get("resource", {}),
            "attributes": resource_attrs,
        }
        for scope in batch.get("scopeSpans") or []:
            spans.extend(
                parse_span(s, trace_id, process_id, service_name, resource_attrs)
                for s in scope.get("spans") or []
            )

    return Trace.model_validate({"traceID": trace_id, "spans": spans, "processes": processes})


def build_summary_trace(trace_data: Dict[str, Any]) -> Optional[Trace]:
    trace_id = trace_data.get("traceID")
    if not trace_id:
        return None

    try:
        start_ns = int(trace_data["startTimeUnixNano"]) if trace_data.get("startTimeUnixNano") else None
    except (TypeError, ValueError):
        start_ns = None

    try:
        duration_ms = int(trace_data["durationMs"]) if trace_data.get("durationMs") is not None else None
    except (TypeError, ValueError):
        duration_ms = None

    service_name = trace_data.get("rootServiceName") or trace_data.get("rootService") or "unknown"

    summary_span = {
        "spanID": "root",
        "traceID": trace_id,
        "parentSpanID": None,
        "operationName": trace_data.get("rootTraceName") or "",
        "startTime": int(start_ns // 1000) if start_ns else 0,
        "duration": int(duration_ms * 1000) if duration_ms is not None else 0,
        "tags": [],
        "serviceName": service_name,
        "attributes": {},
        "processID": service_name,
        "warnings": ["Trace summary only"],
    }

    return Trace.model_validate({
        "traceID": trace_id,
        "spans": [summary_span],
        "processes": {},
        "warnings": ["Trace summary only"],
    })