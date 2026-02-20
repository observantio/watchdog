"""
Configuration values for the gateway auth service.

Reads from the environment on import.  Tests may need to reload the module
if they modify os.environ at runtime, since the values are cached as module
constants.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import os


# rate limiting
RATE_LIMIT_PER_MINUTE: int = int(os.getenv("GATEWAY_RATE_LIMIT_PER_MINUTE", "30000"))
RATE_LIMIT_BACKEND: str = os.getenv("GATEWAY_RATE_LIMIT_BACKEND", "auto").strip().lower()
RATE_LIMIT_REDIS_URL: str = os.getenv("GATEWAY_RATE_LIMIT_REDIS_URL", "").strip()

# IP allowlist
IP_ALLOWLIST: str = os.getenv("GATEWAY_IP_ALLOWLIST", "").strip()
ALLOWLIST_FAIL_OPEN: bool = os.getenv("GATEWAY_ALLOWLIST_FAIL_OPEN", "false").lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# token cache
TOKEN_CACHE_TTL: int = int(os.getenv("GATEWAY_TOKEN_CACHE_TTL", "60"))

# general / startup
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info").upper()
PORT: int = int(os.getenv("GATEWAY_PORT", os.getenv("PORT", "4321")))

GATEWAY_DB_STARTUP_RETRIES: int = int(os.getenv("GATEWAY_DB_STARTUP_RETRIES", "10"))
GATEWAY_DB_STARTUP_BACKOFF: float = float(os.getenv("GATEWAY_DB_STARTUP_BACKOFF", "1.0"))

