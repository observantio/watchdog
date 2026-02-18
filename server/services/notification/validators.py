"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import re
from typing import Dict, List, Any
from services.common.url_utils import is_safe_http_url

def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def validate_channel_config(channel_type: str, channel_config: Dict[str, Any] | None) -> List[str]:
    cfg = channel_config or {}
    normalized_type = str(channel_type or "").strip().lower()
    errors: List[str] = []

    if normalized_type == "email":
        to_field = cfg.get('to') or cfg.get('recipient')
        recipients = [r.strip() for r in re.split(r"[,;\s]+", str(to_field or "")) if r.strip()]
        if not recipients:
            errors.append("Email channel requires at least one recipient in 'to'")

        provider = (cfg.get('email_provider') or cfg.get('emailProvider') or 'smtp').strip().lower()
        if provider == 'smtp':
            smtp_host = cfg.get('smtp_host') or cfg.get('smtpHost')
            if not str(smtp_host or "").strip():
                errors.append("SMTP email channel requires 'smtp_host'")
        elif provider == 'sendgrid':
            api_key = cfg.get('sendgrid_api_key') or cfg.get('sendgridApiKey') or cfg.get('api_key') or cfg.get('apiKey')
            if not str(api_key or "").strip():
                errors.append("SendGrid email channel requires 'sendgrid_api_key'")
        elif provider == 'resend':
            api_key = cfg.get('resend_api_key') or cfg.get('resendApiKey') or cfg.get('api_key') or cfg.get('apiKey')
            if not str(api_key or "").strip():
                errors.append("Resend email channel requires 'resend_api_key'")
        else:
            errors.append(f"Unsupported email provider '{provider}'")

    elif normalized_type == "slack":
        webhook_url = cfg.get('webhook_url') or cfg.get('webhookUrl')
        if not is_safe_http_url(webhook_url):
            errors.append("Slack channel requires a valid 'webhook_url'")

    elif normalized_type == "teams":
        webhook_url = cfg.get('webhook_url') or cfg.get('webhookUrl')
        if not is_safe_http_url(webhook_url):
            errors.append("Teams channel requires a valid 'webhook_url'")

    elif normalized_type == "webhook":
        webhook_url = cfg.get('url') or cfg.get('webhook_url') or cfg.get('webhookUrl')
        if not is_safe_http_url(webhook_url):
            errors.append("Webhook channel requires a valid URL")

    elif normalized_type == "pagerduty":
        routing_key = cfg.get('routing_key') or cfg.get('integrationKey')
        if not str(routing_key or "").strip():
            errors.append("PagerDuty channel requires 'routing_key'")

    return errors
