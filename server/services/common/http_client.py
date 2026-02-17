"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

Shared HTTP client factory for service-layer integrations.
"""

import httpx
from config import config


def create_async_client(timeout_seconds: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds),
        limits=httpx.Limits(
            max_connections=config.HTTP_CLIENT_MAX_CONNECTIONS,
            max_keepalive_connections=config.HTTP_CLIENT_MAX_KEEPALIVE_CONNECTIONS,
            keepalive_expiry=config.HTTP_CLIENT_KEEPALIVE_EXPIRY,
        ),
    )
