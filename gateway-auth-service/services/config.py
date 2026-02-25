"""
Configuration values for the gateway auth service.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations
import os

RATE_LIMIT_PER_MINUTE: int = int(os.getenv("GATEWAY_RATE_LIMIT_PER_MINUTE", "30000"))
RATE_LIMIT_BACKEND: str = os.getenv("GATEWAY_RATE_LIMIT_BACKEND", "auto").strip().lower()
RATE_LIMIT_REDIS_URL: str = os.getenv("GATEWAY_RATE_LIMIT_REDIS_URL", "").strip()
GATEWAY_RATE_LIMIT_STRICT: bool = os.getenv("GATEWAY_RATE_LIMIT_STRICT", "false").lower() in ("1", "true", "yes")

IP_ALLOWLIST: str = os.getenv("GATEWAY_IP_ALLOWLIST", "").strip()
ALLOWLIST_FAIL_OPEN: bool = os.getenv("GATEWAY_ALLOWLIST_FAIL_OPEN", "false").lower() in ("1", "true", "yes", "on")
TRUST_PROXY_HEADERS: bool = os.getenv("GATEWAY_TRUST_PROXY_HEADERS", "false").lower() in ("1", "true", "yes", "on")
TRUSTED_PROXY_CIDRS: list[str] = [
    entry.strip()
    for entry in os.getenv("GATEWAY_TRUSTED_PROXY_CIDRS", "").split(",")
    if entry.strip()
]

TOKEN_CACHE_TTL: int = int(os.getenv("GATEWAY_TOKEN_CACHE_TTL", "60"))
TOKEN_CACHE_REDIS_URL: str = os.getenv("GATEWAY_TOKEN_CACHE_REDIS_URL", "").strip()

AUTH_API_URL: str = os.getenv(
    "GATEWAY_AUTH_API_URL",
    "https://beobservant:4319/api/internal/otlp/validate",
).strip()

INTERNAL_SERVICE_TOKEN: str = os.getenv("GATEWAY_INTERNAL_SERVICE_TOKEN", "").strip()

SSL_VERIFY: bool = os.getenv("GATEWAY_SSL_VERIFY", "true").lower() not in ("0", "false", "no")
SSL_CA_CERTS: str = os.getenv("GATEWAY_SSL_CA_CERTS", "").strip()
SSL_KEYFILE: str = os.getenv("GATEWAY_SSL_KEYFILE", "").strip()
SSL_CERTFILE: str = os.getenv("GATEWAY_SSL_CERTFILE", "").strip()

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info").upper()
PORT: int = int(os.getenv("GATEWAY_PORT", os.getenv("PORT", "4321")))

GATEWAY_STARTUP_RETRIES: int = int(os.getenv("GATEWAY_STARTUP_RETRIES", os.getenv("GATEWAY_DB_STARTUP_RETRIES", "10")))
GATEWAY_STARTUP_BACKOFF: float = float(os.getenv("GATEWAY_STARTUP_BACKOFF", os.getenv("GATEWAY_DB_STARTUP_BACKOFF", "1.0")))
GATEWAY_STATUS_OTLP_TOKEN   = os.getenv("GATEWAY_STATUS_OTLP_TOKEN", "").strip()
