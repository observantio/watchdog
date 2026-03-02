"""
Route payload construction and access control utilities for Grafana integration, providing functions to build request payloads for Grafana API operations while enforcing access control based on user permissions and group memberships. This module includes functions to check for title conflicts when creating or updating dashboards, determine accessible dashboard UIDs for a user, build search contexts for optimizing dashboard searches, and construct payloads for dashboard creation and updates while ensuring that users have the necessary permissions to perform these operations. The utilities also handle visibility settings (private, group, tenant) and shared group management to ensure that users can only access and modify dashboards they have permissions for while maintaining consistency with the underlying database records.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.access.auth_models import Role, TokenData
from models.grafana.grafana_dashboard_models import Dashboard, DashboardCreate, DashboardUpdate

VALID_VISIBILITIES = {"private", "group", "tenant"}

def user_group_ids(current_user: TokenData) -> List[str]:
    gids = getattr(current_user, "group_ids", None) or []
    return list(gids)


def is_admin_user(token_data: TokenData) -> bool:
    return bool(getattr(token_data, "is_superuser", False) or token_data.role == Role.ADMIN)


def validate_visibility(visibility: Optional[str]) -> None:
    if visibility is not None and visibility not in VALID_VISIBILITIES:
        raise ValueError("Invalid visibility value")


def _ensure_dict(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Invalid dashboard payload")
    return payload


def _coerce_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "t", "yes", "y", "on"}:
            return True
        if v in {"0", "false", "f", "no", "n", "off"}:
            return False
    return default


def _dashboard_from_payload(payload: Dict[str, Any]) -> Dashboard:
    dash_raw = payload.get("dashboard")
    return Dashboard.model_validate(dash_raw if isinstance(dash_raw, dict) else payload)


def parse_dashboard_create_payload(payload: Dict) -> DashboardCreate:
    p = _ensure_dict(payload)
    dashboard_obj = _dashboard_from_payload(p)
    return DashboardCreate(
        dashboard=dashboard_obj,
        folderId=_coerce_int(p.get("folderId"), 0),
        overwrite=_coerce_bool(p.get("overwrite"), False),
        message=p.get("message"),
    )


def parse_dashboard_update_payload(payload: Dict) -> DashboardUpdate:
    p = _ensure_dict(payload)
    dashboard_obj = _dashboard_from_payload(p)
    return DashboardUpdate(
        dashboard=dashboard_obj,
        folderId=p.get("folderId"),
        overwrite=_coerce_bool(p.get("overwrite"), True),
        message=p.get("message"),
    )