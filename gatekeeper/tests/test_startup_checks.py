"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import asyncio
import pytest
import main as gateway_main
from models.exceptions import DatabaseUnavailable

@pytest.mark.asyncio
async def test_startup_warn_mode_uses_synthetic_probe_token(monkeypatch):
    captured: list[str] = []

    monkeypatch.setattr(gateway_main.gw_config, "AUTH_API_URL", "https://watchdog:4319/api/internal/otlp/validate")
    monkeypatch.setattr(gateway_main.gw_config, "GATEWAY_STATUS_OTLP_TOKEN", "")
    monkeypatch.setattr(gateway_main.gw_config, "GATEWAY_STARTUP_CHECK_MODE", "warn")
    monkeypatch.setattr(gateway_main.gw_config, "GATEWAY_STARTUP_RETRIES", 1)
    monkeypatch.setattr(gateway_main.gw_config, "GATEWAY_STARTUP_BACKOFF", 0.01)
    service_cls = type(gateway_main.service)
    monkeypatch.setattr(service_cls, "_fetch_org_from_api", lambda self, token: captured.append(token))

    async with gateway_main.lifespan(gateway_main.app):
        await asyncio.sleep(0)

    assert captured == ["__gateway_startup_probe__"]


@pytest.mark.asyncio
async def test_startup_strict_mode_requires_status_token(monkeypatch):
    monkeypatch.setattr(gateway_main.gw_config, "AUTH_API_URL", "https://watchdog:4319/api/internal/otlp/validate")
    monkeypatch.setattr(gateway_main.gw_config, "GATEWAY_STATUS_OTLP_TOKEN", "")
    monkeypatch.setattr(gateway_main.gw_config, "GATEWAY_STARTUP_CHECK_MODE", "strict")
    monkeypatch.setattr(gateway_main.gw_config, "GATEWAY_STARTUP_RETRIES", 1)
    monkeypatch.setattr(gateway_main.gw_config, "GATEWAY_STARTUP_BACKOFF", 0.01)

    with pytest.raises(RuntimeError):
        async with gateway_main.lifespan(gateway_main.app):
            await asyncio.sleep(0)  # pragma: no cover


@pytest.mark.asyncio
async def test_startup_warn_mode_continues_when_auth_api_unavailable(monkeypatch):
    attempts: list[str] = []

    monkeypatch.setattr(gateway_main.gw_config, "AUTH_API_URL", "http://watchdog:4319/api/internal/otlp/validate")
    monkeypatch.setattr(gateway_main.gw_config, "GATEWAY_STATUS_OTLP_TOKEN", "probe-token")
    monkeypatch.setattr(gateway_main.gw_config, "GATEWAY_STARTUP_CHECK_MODE", "warn")
    monkeypatch.setattr(gateway_main.gw_config, "GATEWAY_STARTUP_RETRIES", 2)
    monkeypatch.setattr(gateway_main.gw_config, "GATEWAY_STARTUP_BACKOFF", 0.01)

    def fail_probe(self, token):
        attempts.append(token)
        raise DatabaseUnavailable("auth api unavailable")

    service_cls = type(gateway_main.service)
    monkeypatch.setattr(service_cls, "_fetch_org_from_api", fail_probe)

    async with gateway_main.lifespan(gateway_main.app):
        await asyncio.sleep(0)

    assert attempts == ["probe-token", "probe-token"]


@pytest.mark.asyncio
async def test_startup_strict_mode_raises_when_auth_api_unavailable(monkeypatch):
    monkeypatch.setattr(gateway_main.gw_config, "AUTH_API_URL", "http://watchdog:4319/api/internal/otlp/validate")
    monkeypatch.setattr(gateway_main.gw_config, "GATEWAY_STATUS_OTLP_TOKEN", "probe-token")
    monkeypatch.setattr(gateway_main.gw_config, "GATEWAY_STARTUP_CHECK_MODE", "strict")
    monkeypatch.setattr(gateway_main.gw_config, "GATEWAY_STARTUP_RETRIES", 1)
    monkeypatch.setattr(gateway_main.gw_config, "GATEWAY_STARTUP_BACKOFF", 0.01)

    service_cls = type(gateway_main.service)
    monkeypatch.setattr(
        service_cls,
        "_fetch_org_from_api",
        lambda self, token: (_ for _ in ()).throw(DatabaseUnavailable("auth api unavailable")),
    )

    with pytest.raises(DatabaseUnavailable):
        async with gateway_main.lifespan(gateway_main.app):
            await asyncio.sleep(0)  # pragma: no cover
