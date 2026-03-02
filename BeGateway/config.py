"""
Configuration values for the gateway auth service.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations
import os
from urllib.parse import urlparse

from services.secrets.provider import  SecretProvider, EnvSecretProvider

def _env_name() -> str:
    return (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "development").strip().lower()

def _is_production_env() -> bool:
    return _env_name() in {"prod", "production"}

def _to_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")

def _is_weak_secret(value: str | None) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return True
    weak_markers = ("changeme", "replace_with", "example", "default", "secret", "password")
    return any(marker in normalized for marker in weak_markers)


def build_secret_provider() -> SecretProvider:
    vault_addr = os.getenv("VAULT_ADDR", "").strip()
    if not vault_addr:
        return EnvSecretProvider()

    from vault import VaultClientError, VaultSecretProvider

    token = os.getenv("VAULT_TOKEN", "").strip() or None
    role_id = os.getenv("VAULT_ROLE_ID", "").strip() or None
    secret_id_file = os.getenv("VAULT_SECRET_ID_FILE", "").strip() or None
    secret_id = os.getenv("VAULT_SECRET_ID", "").strip() or None

    secret_id_fn = None
    if role_id:
        if secret_id_file:
            def secret_id_fn() -> str:
                with open(secret_id_file) as f:
                    return f.read().strip()
        elif secret_id:
            secret_id_fn = lambda: secret_id
        else:
            raise VaultClientError(
                "VAULT_ROLE_ID set but neither VAULT_SECRET_ID nor VAULT_SECRET_ID_FILE provided"
            )

    return VaultSecretProvider(
        address=vault_addr,
        token=token,
        role_id=role_id,
        secret_id_fn=secret_id_fn,
        prefix=os.getenv("VAULT_PREFIX", "secret").strip(),
        kv_version=int(os.getenv("VAULT_KV_VERSION", "2")),
        timeout=float(os.getenv("VAULT_TIMEOUT", "2.0")),
        cacert=os.getenv("VAULT_CACERT", "").strip() or None,
        cache_ttl=float(os.getenv("VAULT_CACHE_TTL", "30.0")),
    )

secrets = build_secret_provider()
APP_ENV: str = _env_name()
IS_PRODUCTION: bool = _is_production_env()

RATE_LIMIT_PER_MINUTE: int = int(os.getenv("GATEWAY_RATE_LIMIT_PER_MINUTE", "30000"))
RATE_LIMIT_BACKEND: str = os.getenv("GATEWAY_RATE_LIMIT_BACKEND", "auto").strip().lower()
RATE_LIMIT_REDIS_URL: str = secrets.get("GATEWAY_RATE_LIMIT_REDIS_URL") or ""
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
TOKEN_CACHE_REDIS_URL: str = secrets.get("GATEWAY_TOKEN_CACHE_REDIS_URL") or ""

AUTH_API_URL: str = os.getenv(
    "GATEWAY_AUTH_API_URL",
    "https://beobservant:4319/api/internal/otlp/validate",
).strip()

INTERNAL_SERVICE_TOKEN: str =   secrets.get("GATEWAY_INTERNAL_SERVICE_TOKEN") or ""

SSL_VERIFY: bool = os.getenv("GATEWAY_SSL_VERIFY", "true").lower() not in ("0", "false", "no")
SSL_CA_CERTS: str = os.getenv("GATEWAY_SSL_CA_CERTS", "").strip()
SSL_KEYFILE: str = os.getenv("GATEWAY_SSL_KEYFILE", "").strip()
SSL_CERTFILE: str = os.getenv("GATEWAY_SSL_CERTFILE", "").strip()
HOST: str = os.getenv("GATEWAY_HOST", os.getenv("HOST", "127.0.0.1")).strip()
ENABLE_API_DOCS: bool = _to_bool(os.getenv("ENABLE_API_DOCS"), default=not IS_PRODUCTION)

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info").upper()
PORT: int = int(os.getenv("GATEWAY_PORT", os.getenv("PORT", "4321")))

GATEWAY_STARTUP_RETRIES: int = int(os.getenv("GATEWAY_STARTUP_RETRIES", os.getenv("GATEWAY_DB_STARTUP_RETRIES", "10")))
GATEWAY_STARTUP_BACKOFF: float = float(os.getenv("GATEWAY_STARTUP_BACKOFF", os.getenv("GATEWAY_DB_STARTUP_BACKOFF", "1.0")))
GATEWAY_STATUS_OTLP_TOKEN: str = secrets.get("GATEWAY_STATUS_OTLP_TOKEN") or ""
GATEWAY_STARTUP_CHECK_MODE: str = os.getenv(
    "GATEWAY_STARTUP_CHECK_MODE",
    "strict" if IS_PRODUCTION else "warn",
).strip().lower()

if GATEWAY_STARTUP_CHECK_MODE not in {"strict", "warn"}:
    raise ValueError("GATEWAY_STARTUP_CHECK_MODE must be either 'strict' or 'warn'")

_parsed_auth_url = urlparse(AUTH_API_URL)
if _parsed_auth_url.scheme not in {"http", "https"}:
    raise ValueError("GATEWAY_AUTH_API_URL must use http or https")
if IS_PRODUCTION:
    if _parsed_auth_url.scheme != "https":
        raise ValueError("GATEWAY_AUTH_API_URL must use https in production")
    if not SSL_VERIFY:
        raise ValueError("GATEWAY_SSL_VERIFY must be true in production")
    if ALLOWLIST_FAIL_OPEN:
        raise ValueError("GATEWAY_ALLOWLIST_FAIL_OPEN must be false in production")
    if _is_weak_secret(INTERNAL_SERVICE_TOKEN):
        raise ValueError("GATEWAY_INTERNAL_SERVICE_TOKEN must be a strong non-placeholder secret in production")
    if GATEWAY_STARTUP_CHECK_MODE == "strict" and not GATEWAY_STATUS_OTLP_TOKEN:
        raise ValueError("GATEWAY_STATUS_OTLP_TOKEN is required in production when GATEWAY_STARTUP_CHECK_MODE=strict")
    
