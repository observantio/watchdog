"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


"""Thin helper functions used by Grafana router endpoints."""
from typing import Dict, List, Optional

from models.access.auth_models import Role, TokenData
from models.grafana.grafana_dashboard_models import DashboardCreate, DashboardUpdate


VALID_VISIBILITIES = {"private", "group", "tenant"}


def user_group_ids(current_user: TokenData) -> List[str]:
    return getattr(current_user, "group_ids", []) or []


def is_admin_user(token_data: TokenData) -> bool:
    return token_data.role == Role.ADMIN or token_data.is_superuser


def validate_visibility(visibility: Optional[str]) -> None:
    if visibility is not None and visibility not in VALID_VISIBILITIES:
        raise ValueError("Invalid visibility value")


def parse_dashboard_create_payload(payload: Dict) -> DashboardCreate:
    if isinstance(payload, dict) and payload.get("dashboard"):
        return DashboardCreate(**payload)
    if isinstance(payload, dict):
        return DashboardCreate(
            dashboard=payload,
            folder_id=int(payload.get("folderId", 0)) if payload.get("folderId") is not None else 0,
            overwrite=bool(payload.get("overwrite", False)),
        )
    raise ValueError("Invalid dashboard payload")


def parse_dashboard_update_payload(payload: Dict) -> DashboardUpdate:
    if isinstance(payload, dict) and payload.get("dashboard"):
        return DashboardUpdate(**payload)
    if isinstance(payload, dict):
        return DashboardUpdate(dashboard=payload, overwrite=payload.get("overwrite", True))
    raise ValueError("Invalid dashboard payload")
