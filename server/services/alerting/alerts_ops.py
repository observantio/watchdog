"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


"""Alert-focused operations for AlertManagerService."""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import httpx

from models.alerting.alerts import Alert, AlertGroup
from models.alerting.silences import Matcher, SilenceCreate


async def list_metric_names(service, org_id: str) -> List[str]:
    response = await service._mimir_client.get(
        f"{service.config.MIMIR_URL.rstrip('/')}/prometheus/api/v1/label/__name__/values",
        headers={"X-Scope-OrgID": org_id},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "success":
        raise httpx.HTTPStatusError(
            "Mimir returned non-success status",
            request=response.request,
            response=response,
        )
    metrics = payload.get("data") or []
    if not isinstance(metrics, list):
        return []
    return metrics


async def get_alerts(
    service,
    filter_labels: Optional[Dict[str, str]] = None,
    active: Optional[bool] = None,
    silenced: Optional[bool] = None,
    inhibited: Optional[bool] = None,
) -> List[Alert]:
    params = {}

    filters = []
    if filter_labels:
        for key, value in filter_labels.items():
            filters.append(f'{key}="{value}"')

    if active is not None:
        filters.append(f'active={str(active).lower()}')
    if silenced is not None:
        filters.append(f'silenced={str(silenced).lower()}')
    if inhibited is not None:
        filters.append(f'inhibited={str(inhibited).lower()}')

    if filters:
        params["filter"] = filters

    try:
        response = await service._client.get(
            f"{service.alertmanager_url}/api/v2/alerts",
            params=params,
        )
        response.raise_for_status()
        return [Alert(**alert) for alert in response.json()]
    except httpx.HTTPError as exc:
        service.logger.error("Error fetching alerts: %s", exc)
        return []


async def get_alert_groups(service, filter_labels: Optional[Dict[str, str]] = None) -> List[AlertGroup]:
    params = {}
    if filter_labels:
        filters = [f'{key}="{value}"' for key, value in filter_labels.items()]
        params["filter"] = filters

    try:
        response = await service._client.get(
            f"{service.alertmanager_url}/api/v2/alerts/groups",
            params=params,
        )
        response.raise_for_status()
        return [AlertGroup(**group) for group in response.json()]
    except httpx.HTTPError as exc:
        service.logger.error("Error fetching alert groups: %s", exc)
        return []


async def post_alerts(service, alerts: List[Alert]) -> bool:
    try:
        alert_data = [alert.model_dump(by_alias=True) for alert in alerts]
        response = await service._client.post(
            f"{service.alertmanager_url}/api/v2/alerts",
            json=alert_data,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        service.logger.error("Error posting alerts: %s", exc)
        return False


async def delete_alerts(service, filter_labels: Optional[Dict[str, str]] = None) -> bool:
    if not filter_labels:
        service.logger.warning("Cannot delete all alerts without filter")
        return False

    matchers = [
        Matcher(name=key, value=value, isRegex=False, isEqual=True)
        for key, value in filter_labels.items()
    ]

    now = datetime.now(timezone.utc)
    end = now + timedelta(seconds=60)

    starts_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    ends_at = end.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    silence = SilenceCreate(
        matchers=matchers,
        startsAt=starts_at,
        endsAt=ends_at,
        createdBy="beobservant",
        comment="Alert deletion via API",
    )

    silence_id = await service.create_silence(silence)
    return silence_id is not None
