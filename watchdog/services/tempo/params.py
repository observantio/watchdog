"""
Tempo query parameter construction logic, providing functions to build query parameters
for Tempo search based on TraceQuery conditions.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import TypeAlias

from models.observability.tempo_models import TraceQuery

QueryParamValue: TypeAlias = str | int | float | bool


def _format_tag(key: str, value: object) -> str:
    s = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'{key}="{s}"' if " " in s else f"{key}={s}"


def build_search_params(query: TraceQuery) -> dict[str, QueryParamValue]:
    params: dict[str, QueryParamValue] = {"limit": query.limit}

    tags: dict[str, object] = {}
    if query.service:
        tags["service.name"] = query.service
    if query.operation:
        tags["name"] = query.operation
    if query.tags:
        tags.update(query.tags)
    if tags:
        params["tags"] = " ".join(_format_tag(k, v) for k, v in tags.items())

    if query.start:
        params["start"] = int(query.start) // 1_000_000
    if query.end:
        params["end"] = int(query.end) // 1_000_000
    if query.min_duration:
        params["minDuration"] = query.min_duration
    if query.max_duration:
        params["maxDuration"] = query.max_duration

    return params
