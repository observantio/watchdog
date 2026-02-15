"""AlertManager API router."""
from fastapi import APIRouter, HTTPException, Query, Body, Request, status, Depends
from typing import Optional, List, Dict
import httpx
import logging

from models.alerting.alerts import Alert, AlertGroup, AlertStatus, AlertState
from models.alerting.incidents import AlertIncident, AlertIncidentUpdateRequest
from models.alerting.silences import Silence, SilenceCreate, SilenceCreateRequest, Visibility
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
    enforce_public_endpoint_security,
    enforce_header_token,
)
from middleware.error_handlers import handle_route_errors

logger = logging.getLogger(__name__)

INVALID_FILTER_LABELS_JSON = "Invalid filter_labels JSON"

router = APIRouter(prefix="/api/alertmanager",tags=["alertmanager"])

webhook_router = APIRouter(tags=["alertmanager-webhooks"])

alertmanager_service = AlertManagerService()
notification_service = NotificationService()
storage_service = DatabaseStorageService()


def _user_scope(current_user: TokenData) -> tuple[str, str, List[str]]:
    return (
        current_user.tenant_id,
        current_user.user_id,
        getattr(current_user, "group_ids", []) or [],
    )


def _parse_filter_labels_or_none(filter_labels: Optional[str]) -> Optional[Dict[str, str]]:
    if not filter_labels:
        return None
    return alertmanager_service.parse_filter_labels(filter_labels)


def _enforce_webhook_security(request: Request, *, scope: str) -> None:
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

@webhook_router.post(
    "/alerts/webhook",
    summary="Alert webhook",
    description="Receive alert webhook notifications from AlertManager"
)
@handle_route_errors(bad_request_exceptions=(Exception,), bad_request_detail="Invalid webhook payload")
async def alert_webhook(request: Request) -> dict:
    """Receive alert webhook notifications from AlertManager based on routing configuration."""
    _enforce_webhook_security(request, scope="alertmanager_webhook")
    payload = await request.json()
    alerts = payload.get("alerts", [])
    logger.info("Received webhook payload with %d alerts", len(alerts))
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
    _enforce_webhook_security(request, scope="alertmanager_critical")
    payload = await request.json()
    alerts = payload.get("alerts", [])
    logger.warning("Received %d critical alerts", len(alerts))
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
    _enforce_webhook_security(request, scope="alertmanager_warning")
    payload = await request.json()
    alerts = payload.get("alerts", [])
    logger.info("Received warning alerts payload with %d alerts", len(alerts))
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
    labels = _parse_filter_labels_or_none(filter_labels)
    
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
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_INCIDENTS, "alertmanager")),
):
    return storage_service.list_incidents(current_user.tenant_id, status_filter)


@router.patch("/incidents/{incident_id}", response_model=AlertIncident)
async def patch_incident(
    incident_id: str,
    payload: AlertIncidentUpdateRequest,
    current_user: TokenData = Depends(require_permission_with_scope(Permission.UPDATE_INCIDENTS, "alertmanager")),
):
    updated = storage_service.update_incident(incident_id, current_user.tenant_id, current_user.user_id, payload)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return updated


@router.get("/alerts/groups", response_model=List[AlertGroup])
@handle_route_errors(bad_request_detail=INVALID_FILTER_LABELS_JSON)
async def get_alert_groups(
    filter_labels: Optional[str] = Query(None, description='Label filters as JSON string'),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_ALERTS, "alertmanager"))
):
    """Get alert groups.
    
    Returns alerts grouped by their grouping labels.
    """
    labels = _parse_filter_labels_or_none(filter_labels)
    
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
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_SILENCES, "alertmanager"))
):
    """Get all silences.
    
    Returns all active and expired silences, optionally filtered by labels.
    """
    labels = _parse_filter_labels_or_none(filter_labels)
    
    silences = await alertmanager_service.get_silences(filter_labels=labels)
    visible_silences = []
    for silence in silences:
        silence = alertmanager_service.apply_silence_metadata(silence)
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
    return {"status": "success", "message": f"Silence {silence_id} deleted"}


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
    tenant_id, user_id, group_ids = _user_scope(current_user)
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
    tenant_id, user_id, group_ids = _user_scope(current_user)
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
    tenant_id, user_id, group_ids = _user_scope(current_user)
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
    tenant_id, user_id, group_ids = _user_scope(current_user)
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
    tenant_id, user_id, group_ids = _user_scope(current_user)
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
    tenant_id, user_id, group_ids = _user_scope(current_user)
    channels = storage_service.get_notification_channels(tenant_id, user_id, group_ids)
    return channels


@router.get("/channels/{channel_id}", response_model=NotificationChannel)
async def get_notification_channel(channel_id: str, current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_CHANNELS, "alertmanager"))):
    """Get a specific notification channel by ID.
    
    Returns detailed information about a single notification channel.
    """
    tenant_id, user_id, group_ids = _user_scope(current_user)
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
    tenant_id, user_id, group_ids = _user_scope(current_user)
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
    tenant_id, user_id, group_ids = _user_scope(current_user)
    updated_channel = storage_service.update_notification_channel(channel_id, channel, tenant_id, user_id, group_ids)
    if not updated_channel:
        raise HTTPException(status_code=404, detail=f"Notification channel {channel_id} not found or access denied")
    return updated_channel


@router.delete("/channels/{channel_id}")
async def delete_notification_channel(channel_id: str, current_user: TokenData = Depends(require_permission_with_scope(Permission.DELETE_CHANNELS, "alertmanager"))):
    """Delete a notification channel.
    
    Removes a notification channel from the configuration. Only the owner can delete.
    """
    tenant_id, user_id, group_ids = _user_scope(current_user)
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
    tenant_id, user_id, group_ids = _user_scope(current_user)
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