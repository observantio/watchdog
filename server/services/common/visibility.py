"""
Normalization utilities for handling visibility settings on resources, including functions to normalize visibility values from user input and ensure that they conform to expected formats and allowed values. This module provides a common interface for normalizing visibility settings across different resource types, allowing for consistent handling of visibility options such as "public", "private", "tenant", and "group" while also supporting configurable defaults and aliases for certain visibility levels.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import Optional


def normalize_visibility(
    value: Optional[str],
    *,
    default_value: str = "private",
    public_alias: str = "tenant",
    allowed: set[str] | None = None,
) -> str:
    normalized = str(value or default_value).strip().lower()
    allowed_values = allowed or {"tenant", "group", "private"}
    if normalized in allowed_values:
        return normalized
    if normalized == "public":
        return public_alias
    return default_value


def normalize_storage_visibility(value: Optional[str]) -> str:
    normalized = str(value or "public").strip().lower()
    if normalized in {"public", "private", "group"}:
        return normalized
    if normalized == "tenant":
        return "public"
    return "public"
