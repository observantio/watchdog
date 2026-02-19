"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
from typing import Dict, List, Optional

from models.access.auth_models import Role, TokenData
from models.grafana.grafana_dashboard_models import Dashboard, DashboardCreate, DashboardUpdate


VALID_VISIBILITIES = {"private", "group", "tenant"}


def user_group_ids(current_user: TokenData) -> List[str]:
    return getattr(current_user, "group_ids", []) or []


def is_admin_user(token_data: TokenData) -> bool:
    return token_data.role == Role.ADMIN or token_data.is_superuser


def validate_visibility(visibility: Optional[str]) -> None:
    if visibility is not None and visibility not in VALID_VISIBILITIES:
        raise ValueError("Invalid visibility value")


def parse_dashboard_create_payload(payload: Dict) -> DashboardCreate:
    if not isinstance(payload, dict):
        raise ValueError("Invalid dashboard payload")
    # Ensure inner `dashboard` is a `Dashboard` instance so constructors are type-safe for mypy
    if payload.get("dashboard"):
        dashboard_obj = Dashboard.parse_obj(payload["dashboard"])
        return DashboardCreate(dashboard=dashboard_obj, folderId=int(payload.get("folderId") or 0), overwrite=bool(payload.get("overwrite", False)), message=payload.get("message"))

    dashboard_obj = Dashboard.parse_obj(payload)
    return DashboardCreate(dashboard=dashboard_obj, folderId=int(payload.get("folderId") or 0), overwrite=bool(payload.get("overwrite", False)), message=payload.get("message"))


def parse_dashboard_update_payload(payload: Dict) -> DashboardUpdate:
    if not isinstance(payload, dict):
        raise ValueError("Invalid dashboard payload")
    if payload.get("dashboard"):
        dashboard_obj = Dashboard.parse_obj(payload["dashboard"])
        return DashboardUpdate(dashboard=dashboard_obj, folderId=payload.get("folderId"), overwrite=payload.get("overwrite", True), message=payload.get("message"))

    dashboard_obj = Dashboard.parse_obj(payload)
    return DashboardUpdate(dashboard=dashboard_obj, folderId=payload.get("folderId"), overwrite=payload.get("overwrite", True), message=payload.get("message"))