"""
Alertmanager API proxy router for Be Observant, forwarding requests to the internal Benotified Proxy Service which handles authentication, authorization, and forwarding to the Alertmanager API.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Request, status
import httpx

from config import config
from middleware.dependencies import (
    apply_scoped_rate_limit,
    enforce_header_token,
    enforce_public_endpoint_security,
    get_current_user_or_mfa_setup
)
from models.access.auth_models import Permission, TokenData
from services.benotified_proxy_service import benotified_proxy_service

router = APIRouter(prefix="/api/alertmanager", tags=["alertmanager"])
webhook_router = APIRouter(tags=["alertmanager-webhooks"])

alertmanager_service = benotified_proxy_service
notification_service = None
_SILENCE_META_KEY = "beobservant_meta"


def _required_permissions(path: str, method: str) -> Optional[Set[str]]:
    p = f"/{path.strip('/')}" if path else "/"
    m = method.upper()

    if p in {"/alerts", "/alerts/groups", "/status", "/receivers"} and m == "GET":
        return {Permission.READ_ALERTS.value}
    if p == "/alerts" and m == "POST":
        return {Permission.CREATE_ALERTS.value, Permission.WRITE_ALERTS.value}
    if p == "/alerts" and m == "DELETE":
        return {Permission.DELETE_ALERTS.value}

    if p.startswith("/incidents"):
        if m == "GET":
            return {Permission.READ_INCIDENTS.value}
        return {Permission.UPDATE_INCIDENTS.value}

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
        return {
            Permission.READ_METRICS.value,
            Permission.CREATE_RULES.value,
            Permission.UPDATE_RULES.value,
            Permission.WRITE_ALERTS.value,
        }

    if p == "/public/rules":
        return set()

    return None


def _check_permissions(current_user: TokenData, required: Set[str]) -> None:
    if not required:
        return
    if current_user.is_superuser:
        return
    perms = set(current_user.permissions or [])
    if perms.intersection(required):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to perform this action")


def _is_mutating(method: str) -> bool:
    return method.upper() in {"POST", "PUT", "PATCH", "DELETE"}


def _normalize_group_ids(raw: Any) -> List[str]:
    values = raw if isinstance(raw, list) else []
    normalized: List[str] = []
    seen: Set[str] = set()
    for gid in values:
        if gid is None:
            continue
        s = str(gid).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        normalized.append(s)
    return normalized


def _extract_silence_meta(silence: Dict[str, Any]) -> Dict[str, Any]:
    meta = silence.get(_SILENCE_META_KEY)
    if isinstance(meta, dict):
        return meta
    if isinstance(meta, str):
        try:
            parsed = json.loads(meta)
        except JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    annotations = silence.get("annotations")
    if isinstance(annotations, dict):
        raw = annotations.get(_SILENCE_META_KEY)
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
    return {}


def _validate_and_normalize_silence_payload(payload: Dict[str, Any], current_user: TokenData) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid silence payload")

    normalized = dict(payload)
    visibility = str(normalized.get("visibility", "private")).strip().lower() or "private"
    if visibility not in {"private", "group", "tenant"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid silence visibility")
    normalized["visibility"] = visibility

    shared_group_ids = _normalize_group_ids(
        normalized.get("sharedGroupIds", normalized.get("shared_group_ids"))
    )

    if visibility == "group":
        if not shared_group_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one group is required when visibility is 'group'",
            )
        if not current_user.is_superuser:
            actor_groups = set(_normalize_group_ids(getattr(current_user, "group_ids", [])))
            unauthorized = [gid for gid in shared_group_ids if gid not in actor_groups]
            if unauthorized:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User is not a member of one or more specified groups",
                )
    else:
        shared_group_ids = []

    normalized["sharedGroupIds"] = shared_group_ids
    normalized["shared_group_ids"] = shared_group_ids
    return normalized


def _assert_silence_owner(current_user: TokenData, silence: Dict[str, Any]) -> None:
    if current_user.is_superuser:
        return
    meta = _extract_silence_meta(silence)
    creator = (
        silence.get("created_by")
        or silence.get("createdBy")
        or meta.get("created_by")
        or meta.get("createdBy")
    )
    creator_id = str(creator).strip() if creator is not None else ""
    if not creator_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Silence ownership metadata is missing; update/delete is denied",
        )
    if creator_id != str(current_user.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update or delete silences that you created",
        )


def _extract_silence_id(path: str, payload: Optional[Dict[str, Any]]) -> Optional[str]:
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


async def _find_silence_for_mutation(
    *,
    request: Request,
    current_user: TokenData,
    silence_id: str,
) -> Dict[str, Any]:
    service_token = config.get_secret("BENOTIFIED_SERVICE_TOKEN")
    if not service_token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="BeNotified service token not configured")

    context_token = benotified_proxy_service._sign_context_token(current_user=current_user, api_key_id=None)
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

    silences = data if isinstance(data, list) else []
    for item in silences:
        if isinstance(item, dict) and str(item.get("id", "")).strip() == silence_id:
            return item
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Silence not found")


@webhook_router.post("/alerts/webhook")
async def alert_webhook(request: Request):
    enforce_public_endpoint_security(
        request,
        scope="alertmanager_webhook",
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
        upstream_path="/internal/v1/alertmanager/alerts/webhook",
        current_user=None,
        require_api_key=False,
        audit_action="alertmanager.webhook",
    )


@webhook_router.post("/alerts/critical")
async def alert_critical(request: Request):
    enforce_public_endpoint_security(
        request,
        scope="alertmanager_critical",
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
        upstream_path="/internal/v1/alertmanager/alerts/critical",
        current_user=None,
        require_api_key=False,
        audit_action="alertmanager.webhook.critical",
    )


@webhook_router.post("/alerts/warning")
async def alert_warning(request: Request):
    enforce_public_endpoint_security(
        request,
        scope="alertmanager_warning",
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
        upstream_path="/internal/v1/alertmanager/alerts/warning",
        current_user=None,
        require_api_key=False,
        audit_action="alertmanager.webhook.warning",
    )


@router.get("/public/rules")
async def public_rules_proxy(request: Request):
    enforce_public_endpoint_security(
        request,
        scope="alertmanager_public_rules",
        limit=config.RATE_LIMIT_PUBLIC_PER_MINUTE,
        window_seconds=60,
        allowlist=config.AUTH_PUBLIC_IP_ALLOWLIST,
    )
    return await benotified_proxy_service.forward(
        request=request,
        upstream_path="/internal/v1/api/alertmanager/public/rules",
        current_user=None,
        require_api_key=False,
        audit_action="alertmanager.public_rules.proxy",
    )


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def alertmanager_proxy(
    path: str,
    request: Request,
    current_user: TokenData = Depends(get_current_user_or_mfa_setup),
):
    required = _required_permissions(path, request.method)
    if required is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Route is not authorized")
    _check_permissions(current_user, required)
    method = request.method.upper()
    payload: Optional[Dict[str, Any]] = None

    if path.strip("/").startswith("silences") and method in {"POST", "PUT"}:
        try:
            payload_raw = await request.json()
        except JSONDecodeError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body") from exc
        payload = _validate_and_normalize_silence_payload(payload_raw, current_user)
        request._body = json.dumps(payload).encode("utf-8")

    if path.strip("/").startswith("silences") and method in {"PUT", "DELETE"}:
        silence_id = _extract_silence_id(path, payload)
        if not silence_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Silence id is required")
        existing_silence = await _find_silence_for_mutation(
            request=request,
            current_user=current_user,
            silence_id=silence_id,
        )
        _assert_silence_owner(current_user, existing_silence)

    apply_scoped_rate_limit(current_user, "alertmanager")

    return await benotified_proxy_service.forward(
        request=request,
        upstream_path=f"/internal/v1/api/alertmanager/{path}",
        current_user=current_user,
        require_api_key=_is_mutating(request.method),
        audit_action="alertmanager.proxy",
    )


__all__ = ["router", "webhook_router", "alertmanager_service", "notification_service"]
