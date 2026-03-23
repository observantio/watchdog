"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import pytest

from tests._env import ensure_test_env

ensure_test_env()

from models.access.auth_models import Role, TokenData
from models.access.quota_models import ApiKeyQuota, QuotasResponse, RuntimeQuota
from routers.platform import system_router


@pytest.mark.asyncio
async def test_get_system_quotas_uses_quota_service(monkeypatch):
    expected = QuotasResponse(
        api_keys=ApiKeyQuota(current=1, max=10, remaining=9, status="ok"),
        loki=RuntimeQuota(
            service="loki",
            tenant_id="org-1",
            limit=100,
            used=40,
            remaining=60,
            source="native",
            status="ok",
            updated_at="2026-01-01T00:00:00Z",
        ),
        tempo=RuntimeQuota(
            service="tempo",
            tenant_id="org-1",
            limit=100,
            used=50,
            remaining=50,
            source="prometheus",
            status="degraded",
            updated_at="2026-01-01T00:00:00Z",
            message="fallback",
        ),
    )

    async def fake_get_quotas(current_user, tenant_scope=None):
        return expected

    monkeypatch.setattr(system_router.quota_service, "get_quotas", fake_get_quotas)

    token = TokenData(
        user_id="u1",
        username="u1",
        tenant_id="t1",
        org_id="org-1",
        role=Role.USER,
        permissions=[],
    )
    out = await system_router.get_system_quotas(current_user=token)
    assert out == expected
