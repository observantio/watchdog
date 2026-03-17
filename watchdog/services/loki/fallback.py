"""
Loki Fallback HTTP client with integrated Prometheus metrics observation.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import asyncio
import re
from typing import Dict, List, Optional, Protocol

import httpx

from custom_types.json import JSONDict
from services.loki.http_client import QueryParams

SERVICE_NAME_LABEL = "service.name"
SERVICE_NAME_ALIAS = "service_name"
EXACT_LABEL_RE = re.compile(r'(?P<label>service_name|service\.name)\s*=\s*"(?P<value>[^"]+)"')


def _normalize_service_label(query: str) -> str:
    if SERVICE_NAME_LABEL not in query:
        return query

    def _replace_selector(m: re.Match[str]) -> str:
        content = re.sub(
            rf"(?<![\w.]){re.escape(SERVICE_NAME_LABEL)}(?=\s*=~?)",
            SERVICE_NAME_ALIAS,
            m.group(1),
        )
        return "{" + content + "}"

    return re.sub(r"\{([^}]*)\}", _replace_selector, query)


def _expand_exact_to_prefix(query: str) -> str:
    return EXACT_LABEL_RE.sub(
        lambda m: f'{m.group("label")}=~"{re.escape(m.group("value"))}.*"', query
    )


def build_service_fallback_queries(query: str) -> List[str]:
    seen = {query}
    candidates: List[str] = []

    for transform in (
        _normalize_service_label,
        _expand_exact_to_prefix,
        lambda q: _expand_exact_to_prefix(_normalize_service_label(q)),
    ):
        result = transform(query)
        if result not in seen:
            seen.add(result)
            candidates.append(result)

    return candidates


def build_volume_fallback_queries(query: str, max_candidates: int = 6) -> List[str]:
    seen: set[str] = set()
    candidates: List[str] = []

    def _add(q: str) -> None:
        if q not in seen:
            seen.add(q)
            candidates.append(q)

    _add(query)
    for variant in build_service_fallback_queries(query):
        _add(variant)

    if "service_name" in query or "service.name" in query:
        _add(query.replace("service_name", "service"))
        _add('{service=~".+"}')

    return candidates[: max(1, max_candidates)]


class _LokiHttpClientLike(Protocol):
    async def safe_get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: QueryParams,
        headers: Dict[str, str],
        quiet: bool = False,
    ) -> Optional[JSONDict]: ...


async def run_fallback_queries(
    endpoint: str,
    base_params: QueryParams,
    headers: Dict[str, str],
    query_str: str,
    client: httpx.AsyncClient,
    http_client: _LokiHttpClientLike,
    max_fallbacks: int = 4,
    concurrency: int = 4,
) -> Optional[JSONDict]:
    candidates = build_service_fallback_queries(query_str)[:max(0, max_fallbacks)]
    if not candidates:
        return None

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _query(candidate: str) -> Optional[JSONDict]:
        async with semaphore:
            payload = await http_client.safe_get_json(
                client,
                endpoint,
                params={**base_params, "query": candidate},
                headers=headers,
                quiet=True,
            )
            return payload if isinstance(payload, dict) or payload is None else None

    tasks = [asyncio.create_task(_query(c)) for c in candidates]
    result: Optional[JSONDict] = None
    try:
        for coro in asyncio.as_completed(tasks):
            payload = await coro
            if isinstance(payload, dict):
                data = payload.get("data")
                if isinstance(data, dict) and data.get("result"):
                    result = payload
                    break
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    return result
