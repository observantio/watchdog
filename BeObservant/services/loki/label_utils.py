"""
Loki label utilities for normalizing and expanding service name labels in Loki queries, as well as running fallback queries against a Loki endpoint when the original query does not return results. This module provides functions to transform queries that use the "service.name" label into a normalized form using "service_name", and to expand exact matches on the service name into regex matchers that can match multiple services with similar names. Additionally, it includes an asynchronous function to execute multiple fallback queries concurrently against a Loki endpoint, returning the first successful result that contains data. This is useful for handling cases where the original query may not return results due to differences in label naming or matching behavior in Loki.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import re
from typing import Any, Dict, List, Optional, Tuple

_KEY_RE = re.compile(r"[A-Za-z0-9_.:-]+")


def _parse_pairs(s: str) -> Dict[str, str]:
    pairs: Dict[str, str] = {}
    i = 0
    n = len(s)

    while i < n:
        while i < n and s[i] in ", \t":
            i += 1
        start = i
        while i < n and s[i] not in "=, \t":
            i += 1
        key = s[start:i].strip()
        if not key or not _KEY_RE.fullmatch(key):
            while i < n and s[i] != ",":
                i += 1
            continue

        while i < n and s[i] != "=":
            i += 1
        if i >= n or s[i] != "=":
            break
        i += 1
        if i >= n or s[i] != '"':
            break
        i += 1

        val_chars: List[str] = []
        while i < n:
            ch = s[i]
            if ch == "\\":
                if i + 1 < n:
                    nxt = s[i + 1]
                    if nxt == '"':
                        val_chars.append('"')
                    elif nxt == "\\":
                        val_chars.append("\\")
                    elif nxt == "n":
                        val_chars.append("\n")
                    elif nxt == "r":
                        val_chars.append("\r")
                    elif nxt == "t":
                        val_chars.append("\t")
                    else:
                        val_chars.append(nxt)
                    i += 2
                    continue
                else:
                    val_chars.append("\\")
                    i += 1
                    continue
            if ch == '"':
                i += 1
                break
            val_chars.append(ch)
            i += 1

        pairs[key] = "".join(val_chars)

        while i < n and s[i] in ", \t":
            i += 1

    return pairs


def parse_labelset_value(label_key: str, raw_value: str) -> Optional[Dict[str, str]]:
    if not isinstance(raw_value, str) or '="' not in raw_value:
        return None
    candidate = raw_value if f'{label_key}="' in raw_value else f'{label_key}="{raw_value}'
    pairs = _parse_pairs(candidate)
    return pairs or None


def normalize_label_value(label_key: str, value: Any) -> Tuple[Optional[str], Optional[Dict[str, str]]]:
    if not isinstance(value, str) or '="' not in value or '",' not in value:
        return None, None

    parsed = parse_labelset_value(label_key, value)
    if parsed:
        return parsed.get(label_key, value), parsed

    cut_index = value.find('",')
    return (value[:cut_index], None) if cut_index > 0 else (None, None)


def normalize_label_dict(labels: Dict[str, Any]) -> Dict[str, str]:
    extra: Dict[str, str] = {}
    for key, value in list(labels.items()):
        _, parsed = normalize_label_value(key, value)
        if parsed:
            for k, v in parsed.items():
                if k not in labels:
                    extra[k] = v
    return extra


def normalize_label_values(label: str, values: List[str]) -> List[str]:
    cleaned: List[str] = []
    for value in values:
        if not isinstance(value, str):
            cleaned.append(value)
            continue
        parsed = parse_labelset_value(label, value)
        if parsed and label in parsed:
            cleaned.append(parsed[label])
            continue
        cut_index = value.find('",')
        cleaned.append(value[:cut_index] if cut_index > 0 else value)
    return cleaned