"""AlertManager API router."""
from fastapi import APIRouter, HTTPException, Query, Body, Request, Depends, status
from typing import Optional, List, Dict
import logging

from models.alertmanager_models import (
    Alert, AlertGroup, Silence, SilenceCreate,
    AlertManagerStatus, AlertRule, AlertRuleCreate,
    NotificationChannel, NotificationChannelCreate
)
from services.alertmanager_service import AlertManagerService
from services.storage_service import StorageService
from services.notification_service import NotificationService
from middleware.auth import verify_api_key
from config import constants
from models.alertmanager_models import AlertStatus, AlertState
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

INVALID_FILTER_LABELS_JSON = "Invalid filter_labels JSON"

router = APIRouter(
    prefix="/api/alertmanager",
    tags=["alertmanager"],
    dependencies=[Depends(verify_api_key)]
)

webhook_router = APIRouter(tags=["alertmanager-webhooks"])

alertmanager_service = AlertManagerService()
storage_service = StorageService()
notification_service = NotificationService()


@webhook_router.post(
    "/alerts/webhook",
    summary="Alert webhook",
    description="Receive alert webhook notifications from AlertManager"
)
async def alert_webhook(request: Request) -> dict:
    """Receive alert webhook notifications from AlertManager based on routing configuration."""
    try:
        payload = await request.json()
        alerts = payload.get("alerts", [])
        logger.info(f"Received webhook payload with {len(alerts)} alerts")
        
        for alert in alerts:
            alertname = alert.get('labels', {}).get('alertname', 'unknown')
            alert_status = alert.get('status', 'unknown')
            logger.info(f"Alert: {alertname} - {alert_status}")
        
        return {
            "status": constants.STATUS_SUCCESS,
            "count": len(alerts)
        }
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid webhook payload: {str(e)}"
        )


@webhook_router.post(
    "/alerts/critical",
    summary="Critical alerts webhook",
    description="Receive critical severity alerts routed by AlertManager"
)
async def alert_critical(request: Request) -> dict:
    """Receive critical severity alerts routed by AlertManager."""
    try:
        payload = await request.json()
        alerts = payload.get("alerts", [])
        logger.warning(f"Received {len(alerts)} critical alerts")
        
        for alert in alerts:
            alertname = alert.get('labels', {}).get('alertname', 'unknown')
            logger.warning(f"Critical Alert: {alertname}")
        
        return {
            "status": constants.STATUS_SUCCESS,
            "severity": "critical",
            "count": len(alerts)
        }
    except Exception as e:
        logger.error(f"Error processing critical alerts: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid payload: {str(e)}"
        )


@webhook_router.post(
    "/alerts/warning",
    summary="Warning alerts webhook",
    description="Receive warning severity alerts routed by AlertManager"
)
async def alert_warning(request: Request) -> dict:
    """Receive warning severity alerts routed by AlertManager."""
    try:
        payload = await request.json()
        alerts = payload.get("alerts", [])
        print(f"Received warning alerts payload with {len(alerts)} alerts")
        for alert in alerts:
            print(f"Warning Alert: {alert.get('labels', {}).get('alertname', 'unknown')}")
        
        return {"status": "received", "severity": "warning", "count": len(alerts)}
    except Exception as e:
        print(f"Error processing warning alerts: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")


@router.get("/alerts", response_model=List[Alert])
async def get_alerts(
    active: Optional[bool] = Query(None, description="Filter active alerts"),
    silenced: Optional[bool] = Query(None, description="Filter silenced alerts"),
    inhibited: Optional[bool] = Query(None, description="Filter inhibited alerts"),
    filter_labels: Optional[str] = Query(None, description='Label filters as JSON string, e.g. {"severity":"critical"}')
):
    """Get all alerts with optional filters.
    
    Returns all alerts from AlertManager, optionally filtered by state and labels.
    """
    import json
    labels = None
    if filter_labels:
        try:
            labels = json.loads(filter_labels)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail=INVALID_FILTER_LABELS_JSON)
    
    alerts = await alertmanager_service.get_alerts(
        filter_labels=labels,
        active=active,
        silenced=silenced,
        inhibited=inhibited
    )
    return alerts


@router.get("/alerts/groups", response_model=List[AlertGroup])
async def get_alert_groups(
    filter_labels: Optional[str] = Query(None, description='Label filters as JSON string')
):
    """Get alert groups.
    
    Returns alerts grouped by their grouping labels.
    """
    import json
    labels = None
    if filter_labels:
        try:
            labels = json.loads(filter_labels)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail=INVALID_FILTER_LABELS_JSON)
    
    groups = await alertmanager_service.get_alert_groups(filter_labels=labels)
    return groups


@router.post("/alerts")
async def post_alerts(alerts: List[Alert] = Body(..., description="List of alerts to post")):
    """Post new alerts to AlertManager.
    
    Creates or updates alerts in AlertManager. Used for testing or manual alert creation.
    """
    success = await alertmanager_service.post_alerts(alerts)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to post alerts")
    return {"status": "success", "count": len(alerts)}


@router.delete("/alerts")
async def delete_alerts(
    filter_labels: str = Query(..., description='Label filters as JSON string, e.g. {"alertname":"test"}')
):
    """Delete alerts matching the filter.
    
    Creates a short silence to suppress matching alerts (AlertManager doesn't support direct deletion).
    """
    import json
    try:
        labels = json.loads(filter_labels)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail=INVALID_FILTER_LABELS_JSON)
    
    if not labels:
        raise HTTPException(status_code=400, detail="filter_labels cannot be empty")
    
    success = await alertmanager_service.delete_alerts(filter_labels=labels)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete alerts")
    return {"status": "success", "message": "Alerts silenced"}


@router.get("/silences", response_model=List[Silence])
async def get_silences(
    filter_labels: Optional[str] = Query(None, description='Label filters as JSON string')
):
    """Get all silences.
    
    Returns all active and expired silences, optionally filtered by labels.
    """
    import json
    labels = None
    if filter_labels:
        try:
            labels = json.loads(filter_labels)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail=INVALID_FILTER_LABELS_JSON)
    
    silences = await alertmanager_service.get_silences(filter_labels=labels)
    return silences


@router.get("/silences/{silence_id}", response_model=Silence)
async def get_silence(silence_id: str):
    """Get a specific silence by ID.
    
    Returns detailed information about a single silence.
    """
    silence = await alertmanager_service.get_silence(silence_id)
    if not silence:
        raise HTTPException(status_code=404, detail=f"Silence {silence_id} not found")
    return silence


@router.post("/silences", response_model=Dict[str, str])
async def create_silence(silence: SilenceCreate = Body(..., description="Silence configuration")):
    """Create a new silence.
    
    Creates a silence that will suppress alerts matching the specified matchers.
    """
    silence_id = await alertmanager_service.create_silence(silence)
    if not silence_id:
        raise HTTPException(status_code=500, detail="Failed to create silence")
    return {"silenceID": silence_id, "status": "success"}


@router.put("/silences/{silence_id}", response_model=Dict[str, str])
async def update_silence(
    silence_id: str,
    silence: SilenceCreate = Body(..., description="Updated silence configuration")
):
    """Update an existing silence.
    
    Deletes the old silence and creates a new one with the updated configuration.
    """
    new_id = await alertmanager_service.update_silence(silence_id, silence)
    if not new_id:
        raise HTTPException(status_code=500, detail="Failed to update silence")
    return {"silenceID": new_id, "status": "success", "message": "Silence updated"}


@router.delete("/silences/{silence_id}")
async def delete_silence(silence_id: str):
    """Delete a silence.
    
    Immediately expires the specified silence.
    """
    success = await alertmanager_service.delete_silence(silence_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Silence {silence_id} not found or already deleted")
    return {"status": "success", "message": f"Silence {silence_id} deleted"}


@router.get("/status", response_model=AlertManagerStatus)
async def get_status():
    """Get AlertManager status.
    
    Returns AlertManager version, configuration, and cluster information.
    """
    status = await alertmanager_service.get_status()
    if not status:
        raise HTTPException(status_code=500, detail="Failed to fetch AlertManager status")
    return status


@router.get("/receivers", response_model=List[str])
async def get_receivers():
    """Get list of configured receivers.
    
    Returns names of all alert receivers configured in AlertManager.
    """
    receivers = await alertmanager_service.get_receivers()
    return receivers


@router.get("/rules", response_model=List[AlertRule])
async def get_alert_rules():
    """Get all alert rules.
    
    Returns all configured alert rules.
    """
    rules = storage_service.get_alert_rules()
    return rules


@router.get("/rules/{rule_id}", response_model=AlertRule)
async def get_alert_rule(rule_id: str):
    """Get a specific alert rule by ID.
    
    Returns detailed information about a single alert rule.
    """
    rule = storage_service.get_alert_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found")
    return rule


@router.post("/rules", response_model=AlertRule, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(rule: AlertRuleCreate = Body(..., description="Alert rule configuration")):
    """Create a new alert rule.
    
    Creates a new alert rule that will be evaluated by Prometheus.
    """
    created_rule = storage_service.create_alert_rule(rule)
    return created_rule


@router.put("/rules/{rule_id}", response_model=AlertRule)
async def update_alert_rule(
    rule_id: str,
    rule: AlertRuleCreate = Body(..., description="Updated rule configuration")
):
    """Update an existing alert rule.
    
    Updates the configuration of an existing alert rule.
    """
    updated_rule = storage_service.update_alert_rule(rule_id, rule)
    if not updated_rule:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found")
    return updated_rule


@router.post("/rules/{rule_id}/test")
async def test_alert_rule(rule_id: str):
    """Send a test notification for an alert rule to its configured channels.

    This does not require Prometheus evaluation and is meant for validation.
    """
    rule = storage_service.get_alert_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found")

    channels = storage_service.get_notification_channels()
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
        except Exception as e:
            results.append({"channel": channel.name, "ok": False, "error": str(e)})

    return {
        "status": "success" if success_count else "failed",
        "message": f"Test alert sent to {success_count}/{len(channels)} channels",
        "results": results
    }


@router.delete("/rules/{rule_id}")
async def delete_alert_rule(rule_id: str):
    """Delete an alert rule.
    
    Removes an alert rule from the configuration.
    """
    success = storage_service.delete_alert_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found")
    return {"status": "success", "message": f"Alert rule {rule_id} deleted"}


@router.get("/channels", response_model=List[NotificationChannel])
async def get_notification_channels():
    """Get all notification channels.
    
    Returns all configured notification channels.
    """
    channels = storage_service.get_notification_channels()
    return channels


@router.get("/channels/{channel_id}", response_model=NotificationChannel)
async def get_notification_channel(channel_id: str):
    """Get a specific notification channel by ID.
    
    Returns detailed information about a single notification channel.
    """
    channel = storage_service.get_notification_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail=f"Notification channel {channel_id} not found")
    return channel


@router.post("/channels", response_model=NotificationChannel, status_code=status.HTTP_201_CREATED)
async def create_notification_channel(
    channel: NotificationChannelCreate = Body(..., description="Notification channel configuration")
):
    """Create a new notification channel.
    
    Creates a new notification channel for alert delivery.
    """
    created_channel = storage_service.create_notification_channel(channel)
    return created_channel


@router.put("/channels/{channel_id}", response_model=NotificationChannel)
async def update_notification_channel(
    channel_id: str,
    channel: NotificationChannelCreate = Body(..., description="Updated channel configuration")
):
    """Update an existing notification channel.
    
    Updates the configuration of an existing notification channel.
    """
    updated_channel = storage_service.update_notification_channel(channel_id, channel)
    if not updated_channel:
        raise HTTPException(status_code=404, detail=f"Notification channel {channel_id} not found")
    return updated_channel


@router.delete("/channels/{channel_id}")
async def delete_notification_channel(channel_id: str):
    """Delete a notification channel.
    
    Removes a notification channel from the configuration.
    """
    success = storage_service.delete_notification_channel(channel_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Notification channel {channel_id} not found")
    return {"status": "success", "message": f"Notification channel {channel_id} deleted"}


@router.post("/channels/{channel_id}/test")
async def test_notification_channel(channel_id: str):
    """Test a notification channel.
    
    Sends a test notification through the specified channel.
    """
    channel = storage_service.get_notification_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail=f"Notification channel {channel_id} not found")
    
    test_alert = Alert(
        labels={"alertname": "InvokableTestAlert", "severity": "INFO"},
        annotations={"summary": "You have invoked a test alert", "description": "This is a test notification from BeObservant, Please ignore this alert, if you didn't expect it."},
        startsAt=datetime.now().astimezone().isoformat(),
        status={"state": "active", "silencedBy": [], "inhibitedBy": []},
        fingerprint="test"
    )

    try:
        success = await notification_service.send_notification(channel, test_alert, "firing")
        if success:
            return {"status": "success", "message": f"Test notification sent to {channel.name}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to send test notification")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending test notification: {str(e)}")


__all__ = ["router", "webhook_router"]