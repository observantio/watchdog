"""
Loki Fallback service for handling operations related to Loki datasources that may not be fully supported or accessible through the Grafana API, providing utility functions to manage datasource references in query payloads, enforce access control for datasources in Loki queries, and build contexts for datasource listings. This module serves as a fallback layer to ensure that operations involving Loki datasources can still function correctly even when certain Grafana API features are limited or unavailable, allowing for consistent handling of datasource access and metadata while maintaining security and performance considerations.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
import asyncio
import re
from typing import Any, Dict, List, Optional

_SERVICE_NAME_LABEL = "service.name"
_SERVICE_NAME_ALIAS = "service_name"
_SERVICE_LABEL_EXACT_RE = re.compile(r'(?P<label>service_name|service\.name)\s*=\s*"(?P<value>[^\"]+)"')


def _normalize_service_label_query(query_str: str) -> str:
    if _SERVICE_NAME_LABEL not in query_str and _SERVICE_NAME_ALIAS not in query_str:
        return query_str

    def replace_in_selector(match: re.Match) -> str:
        content = re.sub(rf"(?<![\w.]){_SERVICE_NAME_LABEL}(?=\s*(=|=~))", _SERVICE_NAME_ALIAS, match.group(1))
        return "{" + content + "}"

    return re.sub(r"\{([^}]*)\}", replace_in_selector, query_str)


def _expand_service_label_matchers(query_str: str) -> str:
    return _SERVICE_LABEL_EXACT_RE.sub(lambda m: f'{m.group("label")}=~"{m.group("value")}.*"', query_str)


def build_service_fallback_queries(query_str: str) -> List[str]:
    candidates: List[str] = []
    normalized = _normalize_service_label_query(query_str)
    if normalized != query_str:
        candidates.append(normalized)
    expanded_original = _expand_service_label_matchers(query_str)
    if expanded_original != query_str:
        candidates.append(expanded_original)
    expanded_normalized = _expand_service_label_matchers(normalized)
    if expanded_normalized not in (query_str, expanded_original):
        candidates.append(expanded_normalized)
    return candidates


async def run_fallback_queries(
    endpoint: str,
    base_params: Dict[str, Any],
    headers: Dict[str, str],
    query_str: str,
    client,
    http_client,
    max_fallbacks: int = 4,
    concurrency: int = 4,
) -> Optional[Dict[str, Any]]:
    candidates = build_service_fallback_queries(query_str)[: max(0, max_fallbacks)]
    if not candidates:
        return None

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _query(candidate: str):
        async with semaphore:
            return candidate, await http_client.safe_get_json(
                client, endpoint, params={**base_params, "query": candidate}, headers=headers
            )

    tasks = [asyncio.create_task(_query(candidate)) for candidate in candidates]
    try:
        for task in asyncio.as_completed(tasks):
            _, payload = await task
            if isinstance(payload, dict) and payload.get("data", {}).get("result"):
                for pending in tasks:
                    if pending is not task and not pending.done():
                        pending.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                return payload
        return None
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
