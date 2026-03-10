"""
Utility functions for alert-related operations, including permission checks, silence handling, and proxying to Be Notified.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
"""

from typing import Optional, Set, List, Callable, Awaitable
import httpx
from fastapi import HTTPException, Request, status
from models.access.auth_models import TokenData, Permission
from config import config
from custom_types.json import JSONDict
from services.benotified_proxy_service import benotified_proxy_service
from json import JSONDecodeError
import json
from middleware.dependencies import enforce_public_endpoint_security, enforce_header_token

SILENCE_META_KEY = "beobservant_meta"

def required_permissions(path: str, method: str) -> Optional[Set[str]]:
    p = f"/{path.strip('/')}" if path else "/"
    m = method.upper()

    if p in {"/alerts", "/alerts/groups", "/status", "/receivers"} and m == "GET":
        return {Permission.READ_ALERTS.value}
    if p == "/alerts" and m == "POST":
        return {Permission.CREATE_ALERTS.value, Permission.WRITE_ALERTS.value}
    if p == "/alerts" and m == "DELETE":
        return {Permission.DELETE_ALERTS.value}

    if p.startswith("/incidents"):
        return {Permission.READ_INCIDENTS.value} if m == "GET" else {Permission.UPDATE_INCIDENTS.value}

    if p.startswith("/silences"):
        if m == "GET":
            return {Permission.READ_SILENCES.value}
        if m == "POST":
            return {Permission.CREATE_SILENCES.value, Permission.WRITE_ALERTS.value}
        if m == "PUT":
            return {Permission.UPDATE_SILENCES.value, Permission.WRITE_ALERTS.value}
        if m == "DELETE":
            return {Permission.DELETE_SILENCES.value}

    if p.startswith("/rules/import") and m == "POST":
        return {Permission.CREATE_RULES.value, Permission.WRITE_ALERTS.value}
    if p.startswith("/rules"):
        if m == "GET":
            return {Permission.READ_RULES.value}
        if m == "POST":
            return {Permission.CREATE_RULES.value, Permission.WRITE_ALERTS.value, Permission.TEST_RULES.value}
        if m == "PUT":
            return {Permission.UPDATE_RULES.value, Permission.WRITE_ALERTS.value}
        if m == "DELETE":
            return {Permission.DELETE_RULES.value}

    if p.startswith("/channels"):
        if m == "GET":
            return {Permission.READ_CHANNELS.value}
        if m == "POST":
            return {Permission.CREATE_CHANNELS.value, Permission.WRITE_CHANNELS.value, Permission.TEST_CHANNELS.value}
        if m == "PUT":
            return {Permission.UPDATE_CHANNELS.value, Permission.WRITE_CHANNELS.value}
        if m == "DELETE":
            return {Permission.DELETE_CHANNELS.value}

    if p.startswith("/jira") or p.startswith("/integrations"):
        if p == "/jira/config":
            return {Permission.MANAGE_TENANTS.value}
        if m == "GET":
            return {Permission.READ_INCIDENTS.value, Permission.UPDATE_INCIDENTS.value, Permission.READ_CHANNELS.value}
        return {Permission.UPDATE_INCIDENTS.value}

    if p == "/metrics/names":
        return {Permission.READ_METRICS.value, Permission.CREATE_RULES.value, Permission.UPDATE_RULES.value, Permission.WRITE_ALERTS.value}

    if p == "/public/rules":
        return set()

    return None


def check_permissions(current_user: TokenData, required: Set[str]) -> None:
    if not required or current_user.is_superuser:
        return
    if not set(current_user.permissions or []).intersection(required):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have permission to communicate with Be Notified. Required permissions: {', '.join(required)}",
        )


def is_mutating(method: str) -> bool:
    return method.upper() in {"POST", "PUT", "PATCH", "DELETE"}


def normalize_group_ids(raw: object) -> List[str]:
    seen: Set[str] = set()
    result: List[str] = []
    for gid in (raw if isinstance(raw, list) else []):
        if gid is None:
            continue
        s = str(gid).strip()
        if s and s not in seen:
            seen.add(s)
            result.append(s)
    return result


def _extract_silence_meta(silence: JSONDict) -> JSONDict:
    def _try_parse(v: object) -> JSONDict:
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, dict) else {}
            except JSONDecodeError:
                return {}
        return {}

    meta = _try_parse(silence.get(SILENCE_META_KEY))
    if meta:
        return meta
    annotations = silence.get("annotations")
    if isinstance(annotations, dict):
        return _try_parse(annotations.get(SILENCE_META_KEY))
    return {}


def validate_and_normalize_silence_payload(payload: JSONDict, current_user: TokenData) -> JSONDict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid silence payload")

    normalized = dict(payload)
    visibility = str(normalized.get("visibility", "private")).strip().lower() or "private"
    if visibility not in {"private", "group", "tenant"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid silence visibility")
    normalized["visibility"] = visibility

    shared_group_ids = normalize_group_ids(normalized.get("sharedGroupIds", normalized.get("shared_group_ids")))

    if visibility == "group":
        if not shared_group_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one group is required when visibility is 'group'")
        if not current_user.is_superuser:
            actor_groups = set(normalize_group_ids(getattr(current_user, "group_ids", [])))
            unauthorized = [gid for gid in shared_group_ids if gid not in actor_groups]
            if unauthorized:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not a member of one or more specified groups")
    else:
        shared_group_ids = []

    normalized["sharedGroupIds"] = shared_group_ids
    normalized["shared_group_ids"] = shared_group_ids
    return normalized


def assert_silence_owner(current_user: TokenData, silence: JSONDict) -> None:
    if current_user.is_superuser:
        return
    meta = _extract_silence_meta(silence)
    creator = (
        silence.get("created_by") or silence.get("createdBy")
        or meta.get("created_by") or meta.get("createdBy")
    )
    creator_id = str(creator).strip() if creator is not None else ""
    if not creator_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Silence ownership metadata is missing; update/delete is denied")

    actor_id = str(getattr(current_user, "user_id", "") or "").strip()
    if not actor_id or creator_id != actor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only update or delete silences that you created")


def extract_silence_id(path: str, payload: Optional[JSONDict]) -> Optional[str]:
    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) >= 2 and parts[0] == "silences":
        return parts[1]
    if isinstance(payload, dict):
        cand = payload.get("id") or payload.get("silenceId") or payload.get("silence_id")
        if cand is not None:
            sid = str(cand).strip()
            if sid:
                return sid
    return None


async def find_silence_for_mutation(
    *, request: Request, current_user: TokenData, silence_id: str
) -> JSONDict:
    service_token = config.get_secret("BENOTIFIED_SERVICE_TOKEN")
    if not service_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="BeNotified service token not configured",
        )

    context_token = benotified_proxy_service._sign_context_token(
        current_user=current_user, api_key_id=None
    )
    headers = {
        "X-Service-Token": service_token,
        "X-Correlation-ID": request.headers.get("X-Request-ID", ""),
        "X-Forwarded-For": request.client.host if request.client else "unknown",
        "Authorization": f"Bearer {context_token}",
    }
    target = f"{benotified_proxy_service.base_url}/internal/v1/api/alertmanager/silences"
    try:
        resp = await benotified_proxy_service._client.request("GET", target, headers=headers)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="BeNotified request timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to contact BeNotified") from exc

    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except ValueError:
            detail = resp.text or "Unable to fetch silence"
        raise HTTPException(status_code=resp.status_code, detail=detail)

    try:
        data = resp.json()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Invalid silence response from BeNotified") from exc

    for item in (data if isinstance(data, list) else []):
        if isinstance(item, dict) and str(item.get("id", "")).strip() == silence_id:
            return item
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Silence not found")


def webhook_route(upstream_suffix: str, audit_action: str, scope: str) -> Callable[[Request], Awaitable[object]]:
    async def handler(request: Request) -> object:
        enforce_public_endpoint_security(
            request,
            scope=scope,
            limit=config.RATE_LIMIT_PUBLIC_PER_MINUTE,
            window_seconds=60,
            allowlist=config.WEBHOOK_IP_ALLOWLIST,
        )
        enforce_header_token(
            request,
            header_name="x-beobservant-webhook-token",
            expected_token=config.INBOUND_WEBHOOK_TOKEN,
            unauthorized_detail="Invalid webhook token",
        )
        return await benotified_proxy_service.forward(
            request=request,
            upstream_path=f"/internal/v1/alertmanager/alerts/{upstream_suffix}",
            current_user=None,
            require_api_key=False,
            audit_action=audit_action,
        )
    return handler
