"""
Transport utilities for notification services, providing functions to perform HTTP requests with retry logic for transient failures and to send emails using SMTP with similar retry mechanisms. This module includes error handling to determine whether exceptions are transient and should be retried, as well as logging of failures to facilitate troubleshooting. The transport utilities ensure that notification sending operations are resilient to temporary issues such as network errors or service unavailability, while also integrating with the overall notification system to provide reliable delivery of alerts and messages.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


import logging
from typing import Optional, Dict, Any

import httpx
import aiosmtplib
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
    retry_if_exception_type,
)

from config import config

logger = logging.getLogger(__name__)


def is_transient_http_exception(exc: Exception) -> bool:
    if isinstance(exc, httpx.RequestError):
        return True

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response else 0
        return 500 <= status < 600

    return False


@retry(
    retry=retry_if_exception(is_transient_http_exception),
    stop=stop_after_attempt(config.MAX_RETRIES),
    wait=wait_exponential(multiplier=config.RETRY_BACKOFF),
    reraise=True,
)
async def post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    json: Dict[str, Any] | None = None,
    headers: Dict[str, str] | None = None,
    params: Dict[str, Any] | None = None,
) -> httpx.Response:
    try:
        resp = await client.post(
            url,
            json=json,
            headers=headers,
            params=params,
            timeout=config.DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        return resp

    except Exception as exc:
        logger.warning("HTTP POST failed, retrying: %s", url, exc_info=exc)
        raise

def is_transient_smtp_exception(exc: Exception) -> bool:
    if isinstance(exc, aiosmtplib.errors.SMTPException):
        code = getattr(exc, "code", None)
        return code is None or 400 <= code < 500
    return False


@retry(
    retry=retry_if_exception(is_transient_smtp_exception),
    stop=stop_after_attempt(config.MAX_RETRIES),
    wait=wait_exponential(multiplier=config.RETRY_BACKOFF),
    reraise=True,
)
async def send_smtp_with_retry(
    message,
    hostname: str,
    port: int,
    username: str | None = None,
    password: str | None = None,
    start_tls: bool = False,
    use_tls: bool = False,
    timeout: Optional[int] = None,
):
    try:
        return await aiosmtplib.send(
            message=message,
            hostname=hostname,
            port=port,
            username=username,
            password=password,
            start_tls=start_tls,
            use_tls=use_tls,
            timeout=timeout or config.DEFAULT_TIMEOUT,
        )

    except Exception as exc:
        logger.warning(
            "SMTP send failed, retrying: %s:%s",
            hostname,
            port,
            exc_info=exc,
        )
        raise