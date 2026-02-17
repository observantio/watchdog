"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


"""Silence metadata helpers used by AlertManager service."""

import json
from typing import Dict, List, Optional

from models.alerting.silences import Visibility


SILENCE_META_PREFIX = "[beobservant-meta]"


def normalize_visibility(value: Optional[str]) -> str:
    if isinstance(value, Visibility):
        value = value.value
    if not value:
        return Visibility.PRIVATE.value
    normalized = str(value).lower()
    if normalized not in {Visibility.PRIVATE.value, Visibility.GROUP.value, Visibility.TENANT.value, Visibility.PUBLIC.value}:
        raise ValueError("Invalid visibility value")
    return normalized


def encode_silence_comment(comment: str, visibility: str, shared_group_ids: List[str]) -> str:
    meta = {
        "visibility": visibility,
        "shared_group_ids": shared_group_ids or [],
    }
    payload = json.dumps(meta, separators=(",", ":"))
    return f"{SILENCE_META_PREFIX}{payload}\n{comment}"


def decode_silence_comment(comment: Optional[str]) -> Dict[str, object]:
    if not comment or not comment.startswith(SILENCE_META_PREFIX):
        return {
            "comment": comment or "",
            "visibility": Visibility.TENANT.value,
            "shared_group_ids": [],
        }

    raw = comment[len(SILENCE_META_PREFIX):]
    if "\n" in raw:
        meta_str, comment_text = raw.split("\n", 1)
    else:
        meta_str, comment_text = raw, ""

    try:
        meta = json.loads(meta_str)
    except json.JSONDecodeError:
        return {
            "comment": comment,
            "visibility": Visibility.TENANT.value,
            "shared_group_ids": [],
        }

    visibility = normalize_visibility(meta.get("visibility") or Visibility.TENANT.value)
    shared_group_ids = meta.get("shared_group_ids") or []
    if not isinstance(shared_group_ids, list):
        shared_group_ids = []

    return {
        "comment": comment_text,
        "visibility": visibility,
        "shared_group_ids": shared_group_ids,
    }
