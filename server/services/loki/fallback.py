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

    for task in asyncio.as_completed([_query(c) for c in candidates]):
        _, payload = await task
        if isinstance(payload, dict) and payload.get("data", {}).get("result"):
            return payload
    return None
