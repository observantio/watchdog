"""
Shared components and utilities for Be Observant Grafana proxy router.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from custom_types.json import JSONDict
from models.access.auth_models import TokenData
from models.observability.grafana_request_models import GrafanaDashboardPayloadRequest
from services.database_auth_service import DatabaseAuthService
from services.grafana.route_payloads import is_admin_user, user_group_ids
from services.grafana_proxy_service import GrafanaProxyService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/grafana", tags=["grafana"])
rtp = run_in_threadpool

proxy = GrafanaProxyService()
auth_service = DatabaseAuthService()


def scope_context(current_user: TokenData) -> tuple[str, str, List[str], bool]:
    return (
        current_user.user_id,
        current_user.tenant_id,
        user_group_ids(current_user),
        is_admin_user(current_user),
    )


def hidden_toggle_context(current_user: TokenData) -> tuple[str, str]:
    user_id, tenant_id, _, _ = scope_context(current_user)
    return user_id, tenant_id


def dashboard_payload(payload: GrafanaDashboardPayloadRequest) -> JSONDict:
    raw = payload.model_dump(exclude_none=True)
    return raw if isinstance(raw, dict) else {}


def dashboard_uid(raw: JSONDict) -> str:
    dashboard = raw.get("dashboard")
    if not isinstance(dashboard, dict):
        return ""
    return str(dashboard.get("uid") or "").strip()
