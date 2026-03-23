"""
Package for quota service functionality.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import httpx
from typing import Any

from config import config
from database import get_db_session

from .runtime_probe import RuntimeQuotaProbe
from .service import QuotaService


def _config_getter() -> Any:
    return config


def _httpx_getter() -> Any:
    return httpx


def _db_session_factory() -> Any:
    return get_db_session()


_runtime_probe = RuntimeQuotaProbe(
    config_getter=_config_getter,
    httpx_getter=_httpx_getter,
)

quota_service = QuotaService(
    config_getter=_config_getter,
    db_session_factory=_db_session_factory,
    runtime_probe=_runtime_probe,
)

__all__ = [
    "QuotaService",
    "quota_service",
    "config",
    "get_db_session",
    "httpx",
]
