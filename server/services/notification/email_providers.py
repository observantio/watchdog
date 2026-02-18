"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from email.message import EmailMessage
from typing import List, Optional

import httpx

from . import transport


def build_smtp_message(subject: str, body: str, smtp_from: str, recipients: List[str]) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)
    return msg


async def send_via_sendgrid(client: httpx.AsyncClient, api_key: str, subject: str, body: str, recipients: List[str], smtp_from: str) -> bool:
    payload = {
        "personalizations": [{"to": [{"email": recipient} for recipient in recipients]}],
        "from": {"email": smtp_from},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        await transport.post_with_retry(client, "https://api.sendgrid.com/v3/mail/send", json=payload, headers=headers)
        return True
    except Exception:
        return False


async def send_via_resend(client: httpx.AsyncClient, api_key: str, subject: str, body: str, recipients: List[str], smtp_from: str) -> bool:
    payload = {"from": smtp_from, "to": recipients, "subject": subject, "text": body}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        await transport.post_with_retry(client, "https://api.resend.com/emails", json=payload, headers=headers)
        return True
    except Exception:
        return False


async def send_via_smtp(message, hostname: str, port: int, username: Optional[str], password: Optional[str], start_tls: bool, use_tls: bool, timeout: Optional[int] = None) -> bool:
    try:
        await transport.send_smtp_with_retry(message, hostname=hostname, port=port, username=username, password=password, start_tls=start_tls, use_tls=use_tls, timeout=timeout)
        return True
    except Exception:
        return False
