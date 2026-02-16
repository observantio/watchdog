"""AlertManager API router."""
from fastapi import APIRouter, HTTPException, Query, Body, Request, status, Depends
from typing import Optional, List, Dict
import httpx
import logging
import json
import uuid

from models.alerting.alerts import Alert, AlertGroup, AlertStatus, AlertState
from models.alerting.incidents import AlertIncident, AlertIncidentUpdateRequest
from models.alerting.silences import Silence, SilenceCreate, SilenceCreateRequest, Visibility
from pydantic import BaseModel, Field
from services.jira_service import jira_service, JiraError
from models.alerting.receivers import AlertManagerStatus
from models.alerting.rules import AlertRule, AlertRuleCreate
from models.alerting.channels import NotificationChannel, NotificationChannelCreate
from services.alertmanager_service import AlertManagerService
from services.storage_db_service import DatabaseStorageService
from services.notification_service import NotificationService
from config import config, constants
from datetime import datetime, timezone
from models.access.auth_models import TokenData, Permission

from middleware.dependencies import (
    require_permission_with_scope,
    require_any_permission_with_scope,
    auth_service,
)
from middleware.error_handlers import handle_route_errors
from services.alerting.rule_import_service import parse_rules_yaml, RuleImportError
from services.alerting.integration_security_service import (
    _tenant_id_from_scope_header,
    _encrypt_tenant_secret,
    _decrypt_tenant_secret,
    _load_tenant_jira_config,
    _save_tenant_jira_config,
    _get_effective_jira_credentials,
    _jira_is_enabled_for_tenant,
    _allowed_channel_types,
    _normalize_visibility,
    _validate_shared_group_ids_for_user,
    _load_tenant_jira_integrations,
    _save_tenant_jira_integrations,
    _jira_integration_has_access,
    _mask_jira_integration,
    _resolve_jira_integration,
    _jira_integration_credentials,
    _integration_is_usable,
    _sync_jira_comments_to_incident_notes,
    _normalize_jira_auth_mode,
    _validate_jira_credentials,
)

logger = logging.getLogger(__name__)

INVALID_FILTER_LABELS_JSON = "Invalid filter_labels JSON"

router = APIRouter(prefix="/api/alertmanager",tags=["alertmanager"])

webhook_router = APIRouter(tags=["alertmanager-webhooks"])

alertmanager_service = AlertManagerService()
notification_service = NotificationService()
storage_service = DatabaseStorageService()
@webhook_router.post(
    "/alerts/webhook",
    summary="Alert webhook",
    description="Receive alert webhook notifications from AlertManager"
)
@handle_route_errors(bad_request_exceptions=(Exception,), bad_request_detail="Invalid webhook payload")
async def alert_webhook(request: Request) -> dict:
    """Receive alert webhook notifications from AlertManager based on routing configuration."""
    alertmanager_service.enforce_webhook_security(request, scope="alertmanager_webhook")
    payload = await request.json()
    alerts = payload.get("alerts", [])
    logger.info("Received webhook payload with %d alerts", len(alerts))
    try:
        scoped_header = request.headers.get("x-scope-orgid") or request.headers.get("X-Scope-OrgID")
        tenant_id = _tenant_id_from_scope_header(scoped_header)
        storage_service.sync_incidents_from_alerts(tenant_id, alerts, resolve_missing=False)
    except Exception as exc:
        logger.warning("Incident sync from webhook skipped: %s", exc)

    await alertmanager_service.notify_for_alerts(alerts, storage_service, notification_service)

    return {
        "status": constants.STATUS_SUCCESS,
        "count": len(alerts)
    }


@webhook_router.post(
    "/alerts/critical",
    summary="Critical alerts webhook",
    description="Receive critical severity alerts routed by AlertManager"
)
@handle_route_errors(bad_request_exceptions=(Exception,), bad_request_detail="Invalid payload")
async def alert_critical(request: Request) -> dict:
    """Receive critical severity alerts routed by AlertManager."""
    alertmanager_service.enforce_webhook_security(request, scope="alertmanager_critical")
    payload = await request.json()
    alerts = payload.get("alerts", [])
    logger.warning("Received %d critical alerts", len(alerts))
    try:
        scoped_header = request.headers.get("x-scope-orgid") or request.headers.get("X-Scope-OrgID")
        tenant_id = _tenant_id_from_scope_header(scoped_header)
        storage_service.sync_incidents_from_alerts(tenant_id, alerts, resolve_missing=False)
    except Exception as exc:
        logger.warning("Incident sync from webhook skipped: %s", exc)
    await alertmanager_service.notify_for_alerts(alerts, storage_service, notification_service)
    return {
        "status": constants.STATUS_SUCCESS,
        "severity": "critical",
        "count": len(alerts)
    }


@webhook_router.post(
    "/alerts/warning",
    summary="Warning alerts webhook",
    description="Receive warning severity alerts routed by AlertManager"
)
@handle_route_errors(bad_request_exceptions=(Exception,), bad_request_detail="Invalid payload")
async def alert_warning(request: Request) -> dict:
    """Receive warning severity alerts routed by AlertManager."""
    alertmanager_service.enforce_webhook_security(request, scope="alertmanager_warning")
    payload = await request.json()
    alerts = payload.get("alerts", [])
    logger.info("Received warning alerts payload with %d alerts", len(alerts))
    try:
        scoped_header = request.headers.get("x-scope-orgid") or request.headers.get("X-Scope-OrgID")
        tenant_id = _tenant_id_from_scope_header(scoped_header)
        storage_service.sync_incidents_from_alerts(tenant_id, alerts, resolve_missing=False)
    except Exception as exc:
        logger.warning("Incident sync from webhook skipped: %s", exc)
    await alertmanager_service.notify_for_alerts(alerts, storage_service, notification_service)
    return {"status": "received", "severity": "warning", "count": len(alerts)}


@router.get("/alerts", response_model=List[Alert])
@handle_route_errors(bad_request_detail=INVALID_FILTER_LABELS_JSON)
async def get_alerts(
    active: Optional[bool] = Query(None, description="Filter active alerts"),
    silenced: Optional[bool] = Query(None, description="Filter silenced alerts"),
    inhibited: Optional[bool] = Query(None, description="Filter inhibited alerts"),
    filter_labels: Optional[str] = Query(None, description='Label filters as JSON string, e.g. {"severity":"critical"}'),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_ALERTS, "alertmanager"))
):
    """Get all alerts with optional filters.
    
    Returns all alerts from AlertManager, optionally filtered by state and labels.
    """
    labels = alertmanager_service.parse_filter_labels_or_none(filter_labels)
    
    alerts = await alertmanager_service.get_alerts(
        filter_labels=labels,
        active=active,
        silenced=silenced,
        inhibited=inhibited
    )
    try:
        storage_service.sync_incidents_from_alerts(
            current_user.tenant_id,
            [alert.model_dump(by_alias=True) for alert in alerts],
        )
    except Exception as exc:
        logger.warning("Incident sync skipped due to error: %s", exc)
    return alerts


@router.get("/incidents", response_model=List[AlertIncident])
async def get_incidents(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by incident status: open|resolved"),
    visibility_filter: Optional[str] = Query(None, alias="visibility", description="Filter by incident visibility: public|private|group"),
    group_id_filter: Optional[str] = Query(None, alias="group_id", description="Filter by specific group ID when visibility is group"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_INCIDENTS, "alertmanager")),
):
    return storage_service.list_incidents(
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        group_ids=getattr(current_user, "group_ids", []) or [],
        status=status_filter,
        visibility=visibility_filter,
        group_id=group_id_filter,
    )


@router.patch("/incidents/{incident_id}", response_model=AlertIncident)
async def patch_incident(
    incident_id: str,
    payload: AlertIncidentUpdateRequest,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_INCIDENTS, "alertmanager")),
):
    existing = storage_service.get_incident_for_user(
        incident_id,
        current_user.tenant_id,
        current_user.user_id,
        getattr(current_user, "group_ids", []) or [],
    )
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    # If client attempts to mark incident as resolved, ensure the underlying alert is not active
    try:
        status_value = payload.status
    except Exception:
        status_value = None

    if status_value is not None:
        # normalize to string
        status_str = status_value.value if hasattr(status_value, "value") else str(status_value)
        if status_str.lower() == "resolved":
            # check AlertManager for active alerts matching this incident's fingerprint
            fingerprint = existing.fingerprint
            try:
                active_alerts = await alertmanager_service.get_alerts(filter_labels={"fingerprint": fingerprint}, active=True)
            except Exception:
                active_alerts = []
            if active_alerts:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot mark resolved: underlying alert is still active")

    # perform the update
    try:
        logger.debug(
            "patch_incident called for %s by user %s: note=%s assignee=%s status=%s",
            incident_id,
            current_user.user_id,
            getattr(payload, 'note', None),
            getattr(payload, 'assignee', None),
            getattr(payload, 'status', None),
        )
    except Exception:
        pass
    updated = storage_service.update_incident(incident_id, current_user.tenant_id, current_user.user_id, payload)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    previous_assignee = existing.assignee if existing else None
    new_assignee = updated.assignee
    if new_assignee and new_assignee != previous_assignee:
        assignee_user = None
        try:
            assignee_user = auth_service.get_user_by_id(new_assignee)
            if assignee_user and getattr(assignee_user, "email", None):
                await notification_service.send_incident_assignment_email(
                    recipient_email=assignee_user.email,
                    incident_title=updated.alert_name,
                    incident_status=str(updated.status),
                    incident_severity=updated.severity,
                    actor=current_user.username,
                )
        except Exception as exc:
            logger.warning("Incident assignment email skipped: %s", exc)

        # Append a note recording the assignment (who assigned, target assignee with email if available)
        try:
            assignee_label = alertmanager_service.display_user_label(assignee_user, new_assignee)
            assigner_user = auth_service.get_user_by_id(current_user.user_id)
            assigner_label = alertmanager_service.display_user_label(assigner_user, current_user.username)
            note_text = f"Assigned to {assignee_label} by {assigner_label}"
            # Use a lightweight update to append note
            try:
                from models.alerting.incidents import AlertIncidentUpdateRequest as _Req
                storage_service.update_incident(incident_id, current_user.tenant_id, current_user.user_id, _Req(note=note_text))
            except Exception:
                # if pydantic import or update fails silently continue
                logger.warning("Failed to append assignment note for incident %s", incident_id)
        except Exception:
            logger.exception("Failed to record assignment note")

    if payload.note and updated.jira_ticket_key:
        try:
            if updated.jira_integration_id:
                integration = _resolve_jira_integration(current_user.tenant_id, updated.jira_integration_id, current_user, require_write=True)
                credentials = _jira_integration_credentials(integration)
            else:
                credentials = _get_effective_jira_credentials(current_user.tenant_id)
            await jira_service.add_comment(
                updated.jira_ticket_key,
                f"[{current_user.username}] {payload.note}",
                credentials=credentials,
            )
        except Exception as exc:
            logger.warning("Failed to sync incident note to Jira for incident %s: %s", incident_id, exc)

    return updated


class JiraCreateRequest(BaseModel):
    integrationId: str
    projectKey: str
    issueType: str | None = "Task"
    summary: str | None = None
    description: str | None = None


class JiraConfigRequest(BaseModel):
    enabled: bool = True
    baseUrl: str
    email: str | None = None
    apiToken: str | None = None
    bearerToken: str | None = None


class RuleImportRequest(BaseModel):
    yamlContent: str
    dryRun: bool = False
    defaults: Dict[str, object] | None = None


class JiraIntegrationCreateRequest(BaseModel):
    name: str
    visibility: str = "private"
    sharedGroupIds: List[str] = Field(default_factory=list)
    enabled: bool = True
    baseUrl: Optional[str] = None
    email: Optional[str] = None
    apiToken: Optional[str] = None
    bearerToken: Optional[str] = None
    authMode: Optional[str] = "api_token"
    supportsSso: bool = False


class JiraIntegrationUpdateRequest(BaseModel):
    name: Optional[str] = None
    visibility: Optional[str] = None
    sharedGroupIds: Optional[List[str]] = None
    enabled: Optional[bool] = None
    baseUrl: Optional[str] = None
    email: Optional[str] = None
    apiToken: Optional[str] = None
    bearerToken: Optional[str] = None
    authMode: Optional[str] = None
    supportsSso: Optional[bool] = None


@router.post("/rules/import")
async def import_alert_rules(
    payload: RuleImportRequest,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.CREATE_RULES, Permission.WRITE_ALERTS], "alertmanager")
    ),
):
    tenant_id, user_id, group_ids = alertmanager_service.user_scope(current_user)
    try:
        parsed_rules = parse_rules_yaml(payload.yamlContent, payload.defaults or {})
    except RuleImportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if payload.dryRun:
        return {
            "status": "preview",
            "count": len(parsed_rules),
            "rules": [rule.model_dump(by_alias=True) for rule in parsed_rules],
        }

    existing_rules = storage_service.get_alert_rules(tenant_id, user_id, group_ids)
    existing_index = {
        (rule.name, rule.group, rule.org_id or ""): rule
        for rule in existing_rules
    }

    created = 0
    updated = 0
    imported_rules: List[AlertRule] = []
    for rule in parsed_rules:
        key = (rule.name, rule.group, rule.org_id or "")
        current = existing_index.get(key)
        if current:
            updated_rule = storage_service.update_alert_rule(current.id, rule, tenant_id, user_id, group_ids)
            if updated_rule:
                updated += 1
                imported_rules.append(updated_rule)
            continue

        new_rule = storage_service.create_alert_rule(rule, tenant_id, user_id, group_ids)
        created += 1
        imported_rules.append(new_rule)
        existing_index[(new_rule.name, new_rule.group, new_rule.org_id or "")] = new_rule

    sync_org_ids = {rule.org_id for rule in imported_rules if rule.org_id}
    for org_id in sync_org_ids:
        rules_for_org = storage_service.get_alert_rules_for_org(tenant_id, org_id)
        await alertmanager_service.sync_mimir_rules_for_org(org_id, rules_for_org)

    return {
        "status": "success",
        "count": len(imported_rules),
        "created": created,
        "updated": updated,
        "rules": [rule.model_dump(by_alias=True) for rule in imported_rules],
    }


@router.get("/jira/config")
async def get_jira_config(
    current_user: TokenData = Depends(require_permission_with_scope(Permission.MANAGE_TENANTS, "alertmanager")),
):
    cfg = _load_tenant_jira_config(current_user.tenant_id)
    return {
        "enabled": bool(cfg.get("enabled")),
        "baseUrl": cfg.get("base_url"),
        "email": cfg.get("email"),
        "hasApiToken": bool(cfg.get("api_token")),
        "hasBearerToken": bool(cfg.get("bearer")),
    }


@router.put("/jira/config")
async def put_jira_config(
    payload: JiraConfigRequest,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.MANAGE_TENANTS, "alertmanager")),
):
    return _save_tenant_jira_config(
        current_user.tenant_id,
        enabled=payload.enabled,
        base_url=payload.baseUrl,
        email=payload.email,
        api_token=payload.apiToken,
        bearer=payload.bearerToken,
    )


@router.get("/integrations/channel-types")
async def get_allowed_channel_types(
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_CHANNELS, "alertmanager")),
):
    return {"allowedTypes": _allowed_channel_types()}


@router.get("/integrations/jira")
async def list_jira_integrations(
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_INCIDENTS, "alertmanager")),
):
    integrations = _load_tenant_jira_integrations(current_user.tenant_id)
    visible_items = [
        _mask_jira_integration(item, current_user)
        for item in integrations
        if _jira_integration_has_access(item, current_user, write=False)
    ]
    return {"items": visible_items}


@router.post("/integrations/jira")
async def create_jira_integration(
    payload: JiraIntegrationCreateRequest,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_INCIDENTS, "alertmanager")),
):
    integrations = _load_tenant_jira_integrations(current_user.tenant_id)
    visibility = _normalize_visibility(payload.visibility, "private")
    shared_group_ids = payload.sharedGroupIds or []
    if visibility != "group":
        shared_group_ids = []
    else:
        shared_group_ids = _validate_shared_group_ids_for_user(
            current_user.tenant_id,
            shared_group_ids,
            current_user,
        )

    auth_mode = _normalize_jira_auth_mode(payload.authMode)
    _validate_jira_credentials(
        base_url=payload.baseUrl,
        auth_mode=auth_mode,
        email=payload.email,
        api_token=payload.apiToken,
        bearer_token=payload.bearerToken,
    )

    item = {
        "id": str(uuid.uuid4()),
        "name": (payload.name or "Jira").strip() or "Jira",
        "createdBy": current_user.user_id,
        "enabled": bool(payload.enabled),
        "visibility": visibility,
        "sharedGroupIds": [str(group_id).strip() for group_id in shared_group_ids if str(group_id).strip()],
        "baseUrl": (payload.baseUrl or "").strip() or None,
        "email": (payload.email or "").strip() or None,
        "apiToken": _encrypt_tenant_secret((payload.apiToken or "").strip() or None),
        "bearerToken": _encrypt_tenant_secret((payload.bearerToken or "").strip() or None),
        "authMode": auth_mode,
        "supportsSso": auth_mode == "sso",
    }
    integrations.append(item)
    _save_tenant_jira_integrations(current_user.tenant_id, integrations)
    return _mask_jira_integration(item, current_user)


@router.put("/integrations/jira/{integration_id}")
async def update_jira_integration(
    integration_id: str,
    payload: JiraIntegrationUpdateRequest,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_INCIDENTS, "alertmanager")),
):
    integrations = _load_tenant_jira_integrations(current_user.tenant_id)
    index = next((idx for idx, item in enumerate(integrations) if str(item.get("id")) == integration_id), None)
    if index is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jira integration not found")

    current = integrations[index]
    if str(current.get("createdBy") or "") != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only integration owner can update this integration")

    if payload.name is not None:
        current["name"] = (payload.name or "").strip() or current.get("name") or "Jira"
    if payload.enabled is not None:
        current["enabled"] = bool(payload.enabled)
    if payload.visibility is not None:
        current["visibility"] = _normalize_visibility(payload.visibility, "private")
    if payload.sharedGroupIds is not None:
        current["sharedGroupIds"] = [str(group_id).strip() for group_id in payload.sharedGroupIds if str(group_id).strip()]
    if current.get("visibility") != "group":
        current["sharedGroupIds"] = []
    else:
        current["sharedGroupIds"] = _validate_shared_group_ids_for_user(
            current_user.tenant_id,
            current.get("sharedGroupIds") or [],
            current_user,
        )
    if payload.baseUrl is not None:
        current["baseUrl"] = (payload.baseUrl or "").strip() or None
    if payload.email is not None:
        current["email"] = (payload.email or "").strip() or None
    if payload.apiToken is not None:
        current["apiToken"] = _encrypt_tenant_secret((payload.apiToken or "").strip() or None)
    if payload.bearerToken is not None:
        current["bearerToken"] = _encrypt_tenant_secret((payload.bearerToken or "").strip() or None)
    if payload.authMode is not None:
        current["authMode"] = (payload.authMode or "api_token").strip() or "api_token"
    if payload.supportsSso is not None:
        current["supportsSso"] = bool(payload.supportsSso)

    next_auth_mode = _normalize_jira_auth_mode(current.get("authMode"))
    _validate_jira_credentials(
        base_url=current.get("baseUrl"),
        auth_mode=next_auth_mode,
        email=current.get("email"),
        api_token=_decrypt_tenant_secret(current.get("apiToken")) if current.get("apiToken") else None,
        bearer_token=_decrypt_tenant_secret(current.get("bearerToken")) if current.get("bearerToken") else None,
    )
    current["authMode"] = next_auth_mode
    current["supportsSso"] = next_auth_mode == "sso"

    integrations[index] = current
    _save_tenant_jira_integrations(current_user.tenant_id, integrations)
    return _mask_jira_integration(current, current_user)


@router.delete("/integrations/jira/{integration_id}")
async def delete_jira_integration(
    integration_id: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_INCIDENTS, "alertmanager")),
):
    integrations = _load_tenant_jira_integrations(current_user.tenant_id)
    index = next((idx for idx, item in enumerate(integrations) if str(item.get("id")) == integration_id), None)
    if index is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jira integration not found")
    current = integrations[index]
    if str(current.get("createdBy") or "") != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only integration owner can delete this integration")
    integrations.pop(index)
    _save_tenant_jira_integrations(current_user.tenant_id, integrations)
    return {"status": "success"}


@router.get("/integrations/jira/{integration_id}/projects")
async def list_jira_projects_by_integration(
    integration_id: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_INCIDENTS, "alertmanager")),
):
    integration = _resolve_jira_integration(current_user.tenant_id, integration_id, current_user, require_write=False)
    if not _integration_is_usable(integration):
        return {"enabled": False, "projects": []}
    credentials = _jira_integration_credentials(integration)
    try:
        projects = await jira_service.list_projects(credentials=credentials)
    except JiraError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return {"enabled": True, "projects": projects}


@router.get("/integrations/jira/{integration_id}/projects/{project_key}/issue-types")
async def list_jira_issue_types_by_integration(
    integration_id: str,
    project_key: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_INCIDENTS, "alertmanager")),
):
    integration = _resolve_jira_integration(current_user.tenant_id, integration_id, current_user, require_write=False)
    if not _integration_is_usable(integration):
        return {"enabled": False, "issueTypes": []}
    credentials = _jira_integration_credentials(integration)
    try:
        issue_types = await jira_service.list_issue_types(project_key=project_key, credentials=credentials)
    except JiraError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return {"enabled": True, "issueTypes": issue_types}


@router.get("/jira/projects")
async def list_jira_projects(
    integration_id: Optional[str] = Query(None, alias="integrationId"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_INCIDENTS, "alertmanager")),
):
    if integration_id:
        integration = _resolve_jira_integration(current_user.tenant_id, integration_id, current_user, require_write=False)
        if not _integration_is_usable(integration):
            return {"enabled": False, "projects": []}
        credentials = _jira_integration_credentials(integration)
        try:
            projects = await jira_service.list_projects(credentials=credentials)
        except JiraError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
        return {"enabled": True, "projects": projects}

    if not _jira_is_enabled_for_tenant(current_user.tenant_id):
        return {"enabled": False, "projects": []}
    credentials = _get_effective_jira_credentials(current_user.tenant_id)
    try:
        projects = await jira_service.list_projects(credentials=credentials)
    except JiraError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return {"enabled": True, "projects": projects}


@router.get("/jira/projects/{project_key}/issue-types")
async def list_jira_issue_types(
    project_key: str,
    integration_id: Optional[str] = Query(None, alias="integrationId"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_INCIDENTS, "alertmanager")),
):
    if integration_id:
        integration = _resolve_jira_integration(current_user.tenant_id, integration_id, current_user, require_write=False)
        if not _integration_is_usable(integration):
            return {"enabled": False, "issueTypes": []}
        credentials = _jira_integration_credentials(integration)
        try:
            issue_types = await jira_service.list_issue_types(project_key=project_key, credentials=credentials)
        except JiraError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
        return {"enabled": True, "issueTypes": issue_types}

    if not _jira_is_enabled_for_tenant(current_user.tenant_id):
        return {"enabled": False, "issueTypes": []}
    credentials = _get_effective_jira_credentials(current_user.tenant_id)
    try:
        issue_types = await jira_service.list_issue_types(project_key=project_key, credentials=credentials)
    except JiraError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return {"enabled": True, "issueTypes": issue_types}


@router.post("/incidents/{incident_id}/jira", response_model=AlertIncident)
async def create_incident_jira(
    incident_id: str,
    payload: JiraCreateRequest,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_INCIDENTS, "alertmanager")),
):
    """Create a Jira issue for the incident and persist the ticket key/URL.

    Requires `update:incidents` permission. Server reads Jira credentials from
    environment variables (JIRA_BASE_URL + JIRA_EMAIL/JIRA_API_TOKEN or JIRA_BEARER_TOKEN).
    """
    incident = storage_service.get_incident_for_user(
        incident_id,
        current_user.tenant_id,
        current_user.user_id,
        getattr(current_user, "group_ids", []) or [],
    )
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    if not payload.integrationId:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="integrationId is required")

    integration = _resolve_jira_integration(current_user.tenant_id, payload.integrationId, current_user, require_write=True)
    if not _integration_is_usable(integration):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected Jira integration is not enabled or incomplete")

    project = (payload.projectKey or "").strip()
    if not project:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="projectKey is required")

    summary = (payload.summary or incident.alert_name or "Incident").strip()
    description = payload.description or f"Incident: {incident.alert_name}\n\nLabels: {incident.labels or {}}\nAnnotations: {incident.annotations or {}}"
    issue_type = (payload.issueType or "Task").strip()
    credentials = _jira_integration_credentials(integration)

    try:
        res = await jira_service.create_issue(
            project_key=project,
            summary=summary,
            description=description,
            issue_type=issue_type,
            credentials=credentials,
        )
    except JiraError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    except Exception:
        logger.exception("Unexpected error creating Jira issue")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create Jira issue")

    key = res.get('key')
    url = res.get('url')

    update_payload = AlertIncidentUpdateRequest(
        jira_ticket_key=key or None,
        jira_ticket_url=url or None,
        jira_integration_id=payload.integrationId,
    )
    updated = storage_service.update_incident(incident_id, current_user.tenant_id, current_user.user_id, update_payload)
    if not updated:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to persist Jira metadata")

    logger.info("Created Jira issue %s for incident %s", key, incident_id)
    return updated


class JiraCommentRequest(BaseModel):
    text: str


@router.get("/incidents/{incident_id}/jira/comments")
async def list_incident_jira_comments(
    incident_id: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_INCIDENTS, "alertmanager")),
):
    incident = storage_service.get_incident_for_user(
        incident_id,
        current_user.tenant_id,
        current_user.user_id,
        getattr(current_user, "group_ids", []) or [],
    )
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    if not incident.jira_ticket_key:
        return {"comments": []}
    integration_id = incident.jira_integration_id
    if integration_id:
        integration = _resolve_jira_integration(current_user.tenant_id, integration_id, current_user, require_write=True)
        if not _integration_is_usable(integration):
            return {"comments": []}
        credentials = _jira_integration_credentials(integration)
    else:
        if not _jira_is_enabled_for_tenant(current_user.tenant_id):
            return {"comments": []}
        credentials = _get_effective_jira_credentials(current_user.tenant_id)
    try:
        comments = await jira_service.list_comments(incident.jira_ticket_key, credentials=credentials)
    except JiraError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    _sync_jira_comments_to_incident_notes(incident_id, current_user.tenant_id, comments)
    return {"comments": comments}


@router.post("/incidents/{incident_id}/jira/sync-comments")
async def sync_incident_jira_comments(
    incident_id: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_INCIDENTS, "alertmanager")),
):
    incident = storage_service.get_incident_for_user(
        incident_id,
        current_user.tenant_id,
        current_user.user_id,
        getattr(current_user, "group_ids", []) or [],
    )
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    if not incident.jira_ticket_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incident has no Jira ticket key")
    integration_id = incident.jira_integration_id
    if integration_id:
        integration = _resolve_jira_integration(current_user.tenant_id, integration_id, current_user, require_write=True)
        if not _integration_is_usable(integration):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected Jira integration is not enabled or incomplete")
        credentials = _jira_integration_credentials(integration)
    else:
        if not _jira_is_enabled_for_tenant(current_user.tenant_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Jira integration is not enabled for this tenant")
        credentials = _get_effective_jira_credentials(current_user.tenant_id)
    try:
        comments = await jira_service.list_comments(incident.jira_ticket_key, credentials=credentials)
    except JiraError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    appended = _sync_jira_comments_to_incident_notes(incident_id, current_user.tenant_id, comments)
    return {"status": "success", "synced": appended, "count": len(comments)}


@router.post("/incidents/{incident_id}/jira/comments")
async def create_incident_jira_comment(
    incident_id: str,
    payload: JiraCommentRequest,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_INCIDENTS, "alertmanager")),
):
    incident = storage_service.get_incident_for_user(
        incident_id,
        current_user.tenant_id,
        current_user.user_id,
        getattr(current_user, "group_ids", []) or [],
    )
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    if not incident.jira_ticket_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incident has no Jira ticket key")
    integration_id = incident.jira_integration_id
    if integration_id:
        integration = _resolve_jira_integration(current_user.tenant_id, integration_id, current_user, require_write=True)
        if not _integration_is_usable(integration):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected Jira integration is not enabled or incomplete")
        credentials = _jira_integration_credentials(integration)
    else:
        if not _jira_is_enabled_for_tenant(current_user.tenant_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Jira integration is not enabled for this tenant")
        credentials = _get_effective_jira_credentials(current_user.tenant_id)

    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Comment text is required")

    try:
        comment = await jira_service.add_comment(incident.jira_ticket_key, text, credentials=credentials)
    except JiraError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    try:
        _sync_jira_comments_to_incident_notes(incident_id, current_user.tenant_id, [comment])
    except Exception:
        logger.warning("Failed to persist Jira comment into incident notes for incident %s", incident_id)

    return {"status": "success", "comment": comment}


@router.get("/alerts/groups", response_model=List[AlertGroup])
@handle_route_errors(bad_request_detail=INVALID_FILTER_LABELS_JSON)
async def get_alert_groups(
    filter_labels: Optional[str] = Query(None, description='Label filters as JSON string'),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_ALERTS, "alertmanager"))
):
    """Get alert groups.
    
    Returns alerts grouped by their grouping labels.
    """
    labels = alertmanager_service.parse_filter_labels_or_none(filter_labels)
    
    groups = await alertmanager_service.get_alert_groups(filter_labels=labels)
    return groups


@router.post("/alerts")
async def post_alerts(
    alerts: List[Alert] = Body(..., description="List of alerts to post"),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.CREATE_ALERTS, Permission.WRITE_ALERTS], "alertmanager")
    )
):
    """Post new alerts to AlertManager.
    
    Creates or updates alerts in AlertManager. Used for testing or manual alert creation.
    """
    success = await alertmanager_service.post_alerts(alerts)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to post alerts")
    return {"status": "success", "count": len(alerts)}


@router.delete("/alerts")
@handle_route_errors(bad_request_detail=INVALID_FILTER_LABELS_JSON)
async def delete_alerts(
    filter_labels: str = Query(..., description='Label filters as JSON string, e.g. {"alertname":"test"}'),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.DELETE_ALERTS, "alertmanager"))
):
    """Delete alerts matching the filter.
    
    Creates a short silence to suppress matching alerts (AlertManager doesn't support direct deletion).
    """
    labels = alertmanager_service.parse_filter_labels(filter_labels)
    
    if not labels:
        raise HTTPException(status_code=400, detail="filter_labels cannot be empty")
    
    success = await alertmanager_service.delete_alerts(filter_labels=labels)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete alerts")
    return {"status": "success", "message": "Alerts silenced"}


@router.get("/silences", response_model=List[Silence])
@handle_route_errors(bad_request_detail=INVALID_FILTER_LABELS_JSON)
async def get_silences(
    filter_labels: Optional[str] = Query(None, description='Label filters as JSON string'),
    include_expired: bool = Query(False, description="Include expired silences in the result"),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_SILENCES, "alertmanager"))
):
    """Get silences.

    By default this endpoint returns *active* silences only. Set
    `include_expired=true` to include expired silences in the response.
    Optionally filter by label selectors.
    """
    labels = alertmanager_service.parse_filter_labels_or_none(filter_labels)

    silences = await alertmanager_service.get_silences(filter_labels=labels)
    visible_silences = []
    for silence in silences:
        silence = alertmanager_service.apply_silence_metadata(silence)
        # hide expired silences by default (router-level policy)
        state = (silence.status or {}).get("state") if silence.status else None
        if not include_expired and state and str(state).lower() == "expired":
            continue
        if alertmanager_service.silence_accessible(silence, current_user):
            visible_silences.append(silence)
    return visible_silences


@router.get("/silences/{silence_id}", response_model=Silence)
async def get_silence(
    silence_id: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_SILENCES, "alertmanager"))
):
    """Get a specific silence by ID.
    
    Returns detailed information about a single silence.
    """
    silence = await alertmanager_service.get_silence(silence_id)
    if not silence:
        raise HTTPException(status_code=404, detail=f"Silence {silence_id} not found")
    silence = alertmanager_service.apply_silence_metadata(silence)
    if not alertmanager_service.silence_accessible(silence, current_user):
        raise HTTPException(status_code=404, detail=f"Silence {silence_id} not found")
    return silence


@router.post("/silences", response_model=Dict[str, str])
@handle_route_errors()
async def create_silence(
    silence: SilenceCreateRequest = Body(..., description="Silence configuration"),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.CREATE_SILENCES, Permission.WRITE_ALERTS], "alertmanager")
    )
):
    """Create a new silence.
    
    Creates a silence that will suppress alerts matching the specified matchers.
    """
    visibility = alertmanager_service.normalize_visibility(silence.visibility)
    shared_group_ids = silence.shared_group_ids if visibility == Visibility.GROUP.value else []
    comment = alertmanager_service.encode_silence_comment(silence.comment, visibility, shared_group_ids)
    created_by = current_user.username or current_user.user_id

    payload = SilenceCreate(
        matchers=silence.matchers,
        starts_at=silence.starts_at,
        ends_at=silence.ends_at,
        created_by=created_by,
        comment=comment
    )

    silence_id = await alertmanager_service.create_silence(payload)
    if not silence_id:
        raise HTTPException(status_code=500, detail="Failed to create silence")
    return {"silenceID": silence_id, "status": "success"}


@router.put("/silences/{silence_id}", response_model=Dict[str, str])
@handle_route_errors()
async def update_silence(
    silence_id: str,
    silence: SilenceCreateRequest = Body(..., description="Updated silence configuration"),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_SILENCES, Permission.WRITE_ALERTS], "alertmanager")
    )
):
    """Update an existing silence.
    
    Deletes the old silence and creates a new one with the updated configuration.
    """
    existing = await alertmanager_service.get_silence(silence_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Silence {silence_id} not found")
    existing = alertmanager_service.apply_silence_metadata(existing)
    if not alertmanager_service.silence_accessible(existing, current_user):
        raise HTTPException(status_code=404, detail=f"Silence {silence_id} not found")

    visibility = alertmanager_service.normalize_visibility(silence.visibility)
    shared_group_ids = silence.shared_group_ids if visibility == Visibility.GROUP.value else []
    comment = alertmanager_service.encode_silence_comment(silence.comment, visibility, shared_group_ids)
    created_by = current_user.username or current_user.user_id

    payload = SilenceCreate(
        matchers=silence.matchers,
        starts_at=silence.starts_at,
        ends_at=silence.ends_at,
        created_by=created_by,
        comment=comment
    )

    new_id = await alertmanager_service.update_silence(silence_id, payload)
    if not new_id:
        raise HTTPException(status_code=500, detail="Failed to update silence")
    return {"silenceID": new_id, "status": "success", "message": "Silence updated"}


@router.delete("/silences/{silence_id}")
async def delete_silence(
    silence_id: str,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.DELETE_SILENCES, "alertmanager"))
):
    """Delete a silence.
    
    Immediately expires the specified silence.
    """
    existing = await alertmanager_service.get_silence(silence_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Silence {silence_id} not found or already deleted")
    existing = alertmanager_service.apply_silence_metadata(existing)
    if not alertmanager_service.silence_accessible(existing, current_user):
        raise HTTPException(status_code=404, detail=f"Silence {silence_id} not found or already deleted")

    success = await alertmanager_service.delete_silence(silence_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Silence {silence_id} not found or already deleted")
    # service.delete_silence persists a purge marker so the silence will be
    # omitted from subsequent API/UI responses — surface that fact to clients.
    return {"status": "success", "message": f"Silence {silence_id} deleted", "purged": True}


@router.get("/status", response_model=AlertManagerStatus)
async def get_status(current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_ALERTS, "alertmanager"))):
    """Get AlertManager status.
    
    Returns AlertManager version, configuration, and cluster information.
    """
    status = await alertmanager_service.get_status()
    if not status:
        raise HTTPException(status_code=500, detail="Failed to fetch AlertManager status")
    return status


@router.get("/receivers", response_model=List[str])
async def get_receivers(current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_ALERTS, "alertmanager"))):
    """Get list of configured receivers.
    
    Returns names of all alert receivers configured in AlertManager.
    """
    receivers = await alertmanager_service.get_receivers()
    return receivers


@router.get("/rules", response_model=List[AlertRule])
async def get_alert_rules(current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RULES, "alertmanager"))):
    """Get all alert rules.
    
    Returns all configured alert rules accessible to the user.
    """
    tenant_id = current_user.tenant_id
    user_id = current_user.user_id
    group_ids = getattr(current_user, 'group_ids', []) or []
    rules_with_owner = storage_service.get_alert_rules_with_owner(tenant_id, user_id, group_ids)

    result: List[AlertRule] = []
    for rule, owner in rules_with_owner:
        if owner != current_user.user_id and not getattr(current_user, 'is_superuser', False):
            rule.org_id = None
        result.append(rule)

    return result


@router.get("/public/rules", response_model=List[AlertRule])
async def get_public_alert_rules(request: Request):
    """Public endpoint that returns only rules marked with visibility='public'."""
    enforce_public_endpoint_security(
        request,
        scope="alertmanager_public_rules",
        limit=config.RATE_LIMIT_PUBLIC_PER_MINUTE,
        window_seconds=60,
        allowlist=config.AUTH_PUBLIC_IP_ALLOWLIST,
    )
    tenant_id = config.DEFAULT_ADMIN_TENANT
    from database import get_db_session
    from db_models import Tenant

    with get_db_session() as db:
        tenant = db.query(Tenant).filter_by(name=config.DEFAULT_ADMIN_TENANT).first()
        if not tenant:
            return []
        tenant_id = tenant.id

    return storage_service.get_public_alert_rules(tenant_id)


@router.get("/metrics/names")
@handle_route_errors(bad_gateway_detail="Failed to fetch metrics from Mimir")
async def list_metric_names(
    org_id: Optional[str] = Query(
        None,
        alias="orgId",
        description=(
            "API key value / org_id to scope metrics to. "
            "If omitted, falls back to the current user's org_id."
        ),
    ),
    current_user: TokenData = Depends(
        require_any_permission_with_scope(
            [Permission.READ_METRICS, Permission.CREATE_RULES, Permission.UPDATE_RULES, Permission.WRITE_ALERTS],
            "alertmanager",
        )
    ),
):
    """List metric names from Mimir for assisted rule creation.

    Uses the configured Mimir Prometheus-compatible API and scopes the
    query via ``X-Scope-OrgID`` so that each product / API key only sees
    its own metrics.
    """
    tenant_org_id = org_id or getattr(current_user, "org_id", None)
    if not tenant_org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No org_id available to query metrics. Set a product / API key first.",
        )

    metrics = await alertmanager_service.list_metric_names(tenant_org_id)

    return {"orgId": tenant_org_id, "metrics": metrics}


@router.get("/rules/{rule_id}", response_model=AlertRule)
async def get_alert_rule(rule_id: str, current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_RULES, "alertmanager"))):
    """Get a specific alert rule by ID.
    
    Returns detailed information about a single alert rule.
    """
    tenant_id, user_id, group_ids = alertmanager_service.user_scope(current_user)
    rule = storage_service.get_alert_rule(rule_id, tenant_id, user_id, group_ids)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found")

    raw = storage_service.get_alert_rule_raw(rule_id, tenant_id)
    if raw and raw.created_by != current_user.user_id and not getattr(current_user, 'is_superuser', False):
        rule.org_id = None

    return rule


@router.post("/rules", response_model=AlertRule, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    rule: AlertRuleCreate = Body(..., description="Alert rule configuration"),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.CREATE_RULES, Permission.WRITE_ALERTS], "alertmanager")
    )
):
    """Create a new alert rule.
    
    Creates a new alert rule that will be evaluated by Prometheus.
    Supports visibility settings: private, group, or tenant.
    """
    tenant_id, user_id, group_ids = alertmanager_service.user_scope(current_user)
    resolved_org_id = alertmanager_service.resolve_rule_org_id(rule.org_id, current_user)
    if rule.org_id != resolved_org_id:
        rule = rule.model_copy(update={"org_id": resolved_org_id})
    created_rule = storage_service.create_alert_rule(rule, tenant_id, user_id, group_ids)
    org_to_sync = created_rule.org_id or resolved_org_id
    rules = storage_service.get_alert_rules_for_org(tenant_id, org_to_sync)
    await alertmanager_service.sync_mimir_rules_for_org(org_to_sync, rules)
    return created_rule


@router.put("/rules/{rule_id}", response_model=AlertRule)
async def update_alert_rule(
    rule_id: str,
    rule: AlertRuleCreate = Body(..., description="Updated rule configuration"),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_RULES, Permission.WRITE_ALERTS], "alertmanager")
    )
):
    """Update an existing alert rule.
    
    Updates the configuration of an existing alert rule.
    Can update visibility settings and shared groups.
    """
    tenant_id, user_id, group_ids = alertmanager_service.user_scope(current_user)
    existing_rule = storage_service.get_alert_rule(rule_id, tenant_id, user_id, group_ids)
    if not existing_rule:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found or access denied")

    resolved_org_id = alertmanager_service.resolve_rule_org_id(rule.org_id, current_user)
    if rule.org_id != resolved_org_id:
        rule = rule.model_copy(update={"org_id": resolved_org_id})

    updated_rule = storage_service.update_alert_rule(rule_id, rule, tenant_id, user_id, group_ids)
    if not updated_rule:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found or access denied")

    updated_org_id = updated_rule.org_id or resolved_org_id
    updated_rules = storage_service.get_alert_rules_for_org(tenant_id, updated_org_id)
    await alertmanager_service.sync_mimir_rules_for_org(updated_org_id, updated_rules)
    if existing_rule.org_id and existing_rule.org_id != updated_rule.org_id:
        previous_rules = storage_service.get_alert_rules_for_org(tenant_id, existing_rule.org_id)
        await alertmanager_service.sync_mimir_rules_for_org(existing_rule.org_id, previous_rules)

    return updated_rule


@router.post("/rules/{rule_id}/test")
async def test_alert_rule(
    rule_id: str,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.TEST_RULES, Permission.WRITE_ALERTS], "alertmanager")
    ),
):
    """Send a test notification for an alert rule to its configured channels.

    This does not require Prometheus evaluation and is meant for validation.
    """
    tenant_id, user_id, group_ids = alertmanager_service.user_scope(current_user)
    rule = storage_service.get_alert_rule(rule_id, tenant_id, user_id, group_ids)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found")

    channels = storage_service.get_notification_channels(tenant_id, user_id, group_ids)
    if rule.notification_channels:
        channels = [c for c in channels if c.id in rule.notification_channels]

    if not channels:
        raise HTTPException(status_code=400, detail="No notification channels configured for this rule")

    alert = Alert(
        labels={
            "alertname": rule.name,
            "severity": rule.severity,
            **(rule.labels or {})
        },
        annotations={
            "summary": rule.annotations.get("summary", f"Test alert for {rule.name}"),
            "description": rule.annotations.get("description", rule.expr),
            **(rule.annotations or {})
        },
        startsAt=datetime.now(timezone.utc).isoformat(),
        status=AlertStatus(state=AlertState.ACTIVE, silencedBy=[], inhibitedBy=[]),
        fingerprint=f"test-{rule.id}"
    )

    results = []
    success_count = 0
    for channel in channels:
        try:
            ok = await notification_service.send_notification(channel, alert, "firing")
            results.append({"channel": channel.name, "ok": ok})
            if ok:
                success_count += 1
        except Exception as exc:
            logger.warning(
                "Test notification failed for channel %s on rule %s: %s",
                channel.name,
                rule_id,
                exc,
            )
            results.append({"channel": channel.name, "ok": False, "error": str(exc) or "delivery_error"})

    return {
        "status": "success" if success_count else "failed",
        "message": f"Test alert sent to {success_count}/{len(channels)} channels",
        "results": results
    }


@router.delete("/rules/{rule_id}")
async def delete_alert_rule(rule_id: str, current_user: TokenData = Depends(require_permission_with_scope(Permission.DELETE_RULES, "alertmanager"))):
    """Delete an alert rule.
    
    Removes an alert rule from the configuration. Only the owner can delete.
    """
    tenant_id, user_id, group_ids = alertmanager_service.user_scope(current_user)
    existing_rule = storage_service.get_alert_rule(rule_id, tenant_id, user_id, group_ids)
    if not existing_rule:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found or access denied")

    success = storage_service.delete_alert_rule(rule_id, tenant_id, user_id, group_ids)
    if not success:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found or access denied")

    resolved_org_id = alertmanager_service.resolve_rule_org_id(existing_rule.org_id, current_user)
    rules = storage_service.get_alert_rules_for_org(tenant_id, resolved_org_id)
    await alertmanager_service.sync_mimir_rules_for_org(resolved_org_id, rules)
    return {"status": "success", "message": f"Alert rule {rule_id} deleted"}


@router.get("/channels", response_model=List[NotificationChannel])
async def get_notification_channels(current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_CHANNELS, "alertmanager"))):
    """Get all notification channels.
    
    Returns all configured notification channels accessible to the user.
    """
    tenant_id, user_id, group_ids = alertmanager_service.user_scope(current_user)
    channels = storage_service.get_notification_channels(tenant_id, user_id, group_ids)
    return channels


@router.get("/channels/{channel_id}", response_model=NotificationChannel)
async def get_notification_channel(channel_id: str, current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_CHANNELS, "alertmanager"))):
    """Get a specific notification channel by ID.
    
    Returns detailed information about a single notification channel.
    """
    tenant_id, user_id, group_ids = alertmanager_service.user_scope(current_user)
    channel = storage_service.get_notification_channel(channel_id, tenant_id, user_id, group_ids)
    if not channel:
        raise HTTPException(status_code=404, detail=f"Notification channel {channel_id} not found")
    return channel


@router.post("/channels", response_model=NotificationChannel, status_code=status.HTTP_201_CREATED)
async def create_notification_channel(
    channel: NotificationChannelCreate = Body(..., description="Notification channel configuration"),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.CREATE_CHANNELS, Permission.WRITE_CHANNELS], "alertmanager")
    )
):
    """Create a new notification channel.
    
    Creates a new notification channel for alert delivery.
    Supports visibility settings: private, group, or tenant.
    """
    tenant_id, user_id, group_ids = alertmanager_service.user_scope(current_user)
    allowed_types = _allowed_channel_types()
    requested_type = str(channel.type or "").strip().lower()
    if requested_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Channel type '{requested_type}' is disabled by organization policy",
        )
    validation_errors = notification_service.validate_channel_config(requested_type, channel.config)
    if validation_errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": validation_errors})
    created_channel = storage_service.create_notification_channel(channel, tenant_id, user_id, group_ids)
    return created_channel


@router.put("/channels/{channel_id}", response_model=NotificationChannel)
async def update_notification_channel(
    channel_id: str,
    channel: NotificationChannelCreate = Body(..., description="Updated channel configuration"),
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.UPDATE_CHANNELS, Permission.WRITE_CHANNELS], "alertmanager")
    )
):
    """Update an existing notification channel.
    
    Updates the configuration of an existing notification channel.
    Can update visibility settings and shared groups.
    """
    tenant_id, user_id, group_ids = alertmanager_service.user_scope(current_user)
    allowed_types = _allowed_channel_types()
    requested_type = str(channel.type or "").strip().lower()
    if requested_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Channel type '{requested_type}' is disabled by organization policy",
        )
    validation_errors = notification_service.validate_channel_config(requested_type, channel.config)
    if validation_errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": validation_errors})
    updated_channel = storage_service.update_notification_channel(channel_id, channel, tenant_id, user_id, group_ids)
    if not updated_channel:
        raise HTTPException(status_code=404, detail=f"Notification channel {channel_id} not found or access denied")
    return updated_channel


@router.delete("/channels/{channel_id}")
async def delete_notification_channel(channel_id: str, current_user: TokenData = Depends(require_permission_with_scope(Permission.DELETE_CHANNELS, "alertmanager"))):
    """Delete a notification channel.
    
    Removes a notification channel from the configuration. Only the owner can delete.
    """
    tenant_id, user_id, group_ids = alertmanager_service.user_scope(current_user)
    success = storage_service.delete_notification_channel(channel_id, tenant_id, user_id, group_ids)
    if not success:
        raise HTTPException(status_code=404, detail=f"Notification channel {channel_id} not found or access denied")
    return {"status": "success", "message": f"Notification channel {channel_id} deleted"}


@router.post("/channels/{channel_id}/test")
@handle_route_errors(internal_detail="Failed to send test notification")
async def test_notification_channel(
    channel_id: str,
    current_user: TokenData = Depends(
        require_any_permission_with_scope([Permission.TEST_CHANNELS, Permission.WRITE_CHANNELS], "alertmanager")
    ),
):
    """Test a notification channel.
    
    Sends a test notification through the specified channel.
    """
    tenant_id, user_id, group_ids = alertmanager_service.user_scope(current_user)
    if not storage_service.is_notification_channel_owner(channel_id, tenant_id, user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only channel owner can test this channel")
    channel = storage_service.get_notification_channel(channel_id, tenant_id, user_id, group_ids)
    if not channel:
        raise HTTPException(status_code=404, detail=f"Notification channel {channel_id} not found")
    
    test_alert = Alert(
        labels={"alertname": "InvokableTestAlert", "severity": "INFO"},
        annotations={"summary": "You have invoked a test alert", "description": "This is a test notification from BeObservant, Please ignore this alert, if you didn't expect it."},
        startsAt=datetime.now().astimezone().isoformat(),
        status={"state": "active", "silencedBy": [], "inhibitedBy": []},
        fingerprint="test"
    )

    success = await notification_service.send_notification(channel, test_alert, "firing")
    if success:
        return {"status": "success", "message": f"Test notification sent to {channel.name}"}
    raise HTTPException(status_code=500, detail="Failed to send test notification")


__all__ = ["router", "webhook_router"]