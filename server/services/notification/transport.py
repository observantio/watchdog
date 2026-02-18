"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import logging
from typing import Optional, Dict, Any

import httpx
import aiosmtplib
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, retry_if_exception

from config import config

logger = logging.getLogger(__name__)


def is_transient_http_exception(exc) -> bool:
    if isinstance(exc, httpx.RequestError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else 0
        return 500 <= status < 600
    return False


@retry(
    retry=retry_if_exception(is_transient_http_exception),
    stop=stop_after_attempt(config.MAX_RETRIES),
    wait=wait_exponential(multiplier=config.RETRY_BACKOFF),
    reraise=True,
)
async def post_with_retry(client: httpx.AsyncClient, url: str, json: Dict[str, Any] | None = None, headers: Dict[str, str] | None = None, params: Dict[str, Any] | None = None) -> httpx.Response:
    resp = await client.post(url, json=json, headers=headers, params=params)
    resp.raise_for_status()
    return resp


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(config.MAX_RETRIES),
    wait=wait_exponential(multiplier=config.RETRY_BACKOFF),
    reraise=True,
)
async def send_smtp_with_retry(message, hostname: str, port: int, username: str | None = None, password: str | None = None, start_tls: bool = False, use_tls: bool = False, timeout: Optional[int] = None):
    return await aiosmtplib.send(
        message=message,
        hostname=hostname,
        port=port,
        username=username,
        password=password,
        start_tls=start_tls,
        timeout=timeout or config.DEFAULT_TIMEOUT,
        use_tls=use_tls,
    )
