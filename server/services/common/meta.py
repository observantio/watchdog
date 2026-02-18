"""Shared incident / silence meta helpers."""
from typing import Any, Dict, List
import json
from json import JSONDecodeError

INCIDENT_META_KEY = "beobservant_meta"


def _parse_meta(annotations: Any) -> Dict[str, Any]:
    if not isinstance(annotations, dict):
        return {}
    raw = annotations.get(INCIDENT_META_KEY)
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except JSONDecodeError:
            return {}
    return {}


def _safe_group_ids(meta: Dict[str, Any]) -> List[str]:
    return [str(g) for g in (meta.get("shared_group_ids") or []) if isinstance(g, str) and g.strip()]
