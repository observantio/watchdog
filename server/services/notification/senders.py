"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import Dict, Any

import httpx

from . import payloads, transport
from services.common.url_utils import is_safe_http_url


async def send_slack(client: httpx.AsyncClient, channel_config: Dict[str, Any], alert, action: str) -> bool:
    webhook_url = channel_config.get('webhook_url') or channel_config.get('webhookUrl')
    if not is_safe_http_url(webhook_url):
        return False
    payload = payloads.build_slack_payload(alert, action)
    try:
        await transport.post_with_retry(client, webhook_url, json=payload)
        return True
    except httpx.HTTPStatusError as exc:
        return False
    except Exception:
        return False


async def send_teams(client: httpx.AsyncClient, channel_config: Dict[str, Any], alert, action: str) -> bool:
    webhook_url = channel_config.get('webhook_url') or channel_config.get('webhookUrl')
    if not is_safe_http_url(webhook_url):
        return False
    payload = payloads.build_teams_payload(alert, action)
    try:
        await transport.post_with_retry(client, webhook_url, json=payload)
        return True
    except httpx.HTTPStatusError:
        return False
    except Exception:
        return False


async def send_webhook(client: httpx.AsyncClient, channel_config: Dict[str, Any], alert, action: str) -> bool:
    webhook_url = channel_config.get('url') or channel_config.get('webhook_url') or channel_config.get('webhookUrl')
    if not is_safe_http_url(webhook_url):
        return False
    payload = {"action": action, "alert": {"labels": alert.labels, "annotations": alert.annotations, "startsAt": alert.starts_at, "endsAt": alert.ends_at, "fingerprint": alert.fingerprint}}
    headers = channel_config.get('headers', {})
    try:
        await transport.post_with_retry(client, webhook_url, json=payload, headers=headers)
        return True
    except httpx.HTTPStatusError:
        return False
    except Exception:
        return False


async def send_pagerduty(client: httpx.AsyncClient, channel_config: Dict[str, Any], alert, action: str) -> bool:
    routing_key = channel_config.get('routing_key') or channel_config.get('integrationKey')
    if not routing_key:
        return False
    payload = payloads.build_pagerduty_payload(alert, action, routing_key)
    try:
        await transport.post_with_retry(client, "https://events.pagerduty.com/v2/enqueue", json=payload)
        return True
    except httpx.HTTPStatusError:
        return False
    except Exception:
        return False
