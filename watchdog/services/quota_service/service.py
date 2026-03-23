"""
Quota service orchestration and API key quota logic.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import Any, Callable, Literal, Optional

from db_models import UserApiKey
from models.access.auth_models import TokenData
from models.access.quota_models import ApiKeyQuota, QuotasResponse, RuntimeQuota

from .parsing import compute_remaining, now_utc
from .runtime_probe import RuntimeQuotaProbe


ConfigGetter = Callable[[], Any]
DbSessionFactory = Callable[[], Any]
RuntimeService = Literal["loki", "tempo"]
RuntimeSource = Literal["native", "prometheus", "none"]


class QuotaService:
    def __init__(
        self,
        *,
        config_getter: ConfigGetter,
        db_session_factory: DbSessionFactory,
        runtime_probe: RuntimeQuotaProbe,
    ) -> None:
        self._get_config = config_getter
        self._db_session_factory = db_session_factory
        self._runtime_probe = runtime_probe

    async def _resolve_runtime_quota(
        self,
        *,
        service_name: RuntimeService,
        base_url: str,
        native_path: str,
        native_limit_field: str,
        native_used_field: str,
        prom_limit_query: str,
        prom_used_query: str,
        tenant_id: str,
    ) -> RuntimeQuota:
        messages: list[str] = []

        native = await self._runtime_probe.fetch_native_quota(
            service_name=service_name,
            base_url=base_url,
            path_template=native_path,
            tenant_id=tenant_id,
            limit_field=native_limit_field,
            used_field=native_used_field,
        )
        if native.message:
            messages.append(native.message)
        if native.complete():
            return RuntimeQuota(
                service=service_name,
                tenant_id=tenant_id,
                limit=native.limit,
                used=native.used,
                remaining=compute_remaining(native.limit, native.used),
                source="native",
                status="ok",
                updated_at=now_utc(),
                message=None,
            )

        prom = await self._runtime_probe.fetch_prometheus_quota(
            service_name=service_name,
            tenant_id=tenant_id,
            limit_query=prom_limit_query,
            used_query=prom_used_query,
        )
        if prom.message:
            messages.append(prom.message)
        if prom.complete():
            return RuntimeQuota(
                service=service_name,
                tenant_id=tenant_id,
                limit=prom.limit,
                used=prom.used,
                remaining=compute_remaining(prom.limit, prom.used),
                source="prometheus",
                status="ok",
                updated_at=now_utc(),
                message=None,
            )

        final_limit = native.limit if native.limit is not None else prom.limit
        final_used = native.used if native.used is not None else prom.used
        has_any_value = final_limit is not None or final_used is not None
        source: RuntimeSource = (
            "native" if native.any_value() else ("prometheus" if prom.any_value() else "none")
        )

        if has_any_value:
            if messages:
                final_message = "; ".join(messages)
            elif final_limit is None and final_used is not None:
                final_message = (
                    f"{service_name.capitalize()} usage is available, but upstream did not return a limit"
                )
            elif final_limit is not None and final_used is None:
                final_message = (
                    f"{service_name.capitalize()} limit is available, but upstream did not return usage"
                )
            else:
                final_message = "Partial quota data available from upstream"
        else:
            final_message = "Runtime quota data is currently unavailable for this scope"

        return RuntimeQuota(
            service=service_name,
            tenant_id=tenant_id,
            limit=final_limit,
            used=final_used,
            remaining=compute_remaining(final_limit, final_used),
            source=source,
            status="degraded" if has_any_value else "unavailable",
            updated_at=now_utc(),
            message=final_message,
        )

    def _api_key_quota(self, user_id: str, tenant_id: str) -> ApiKeyQuota:
        cfg = self._get_config()
        with self._db_session_factory() as db:
            current = (
                db.query(UserApiKey)
                .filter(UserApiKey.user_id == user_id, UserApiKey.tenant_id == tenant_id)
                .count()
            )
        max_keys = int(cfg.MAX_API_KEYS_PER_USER)
        return ApiKeyQuota(
            current=int(current),
            max=max_keys,
            remaining=max(0, max_keys - int(current)),
            status="ok",
        )

    async def get_quotas(
        self,
        current_user: TokenData,
        tenant_scope: Optional[str] = None,
    ) -> QuotasResponse:
        cfg = self._get_config()
        resolved_scope = str(
            tenant_scope or current_user.org_id or current_user.tenant_id or cfg.DEFAULT_ORG_ID
        )
        return QuotasResponse(
            api_keys=self._api_key_quota(current_user.user_id, current_user.tenant_id),
            loki=await self._resolve_runtime_quota(
                service_name="loki",
                base_url=cfg.LOKI_URL,
                native_path=cfg.LOKI_QUOTA_NATIVE_PATH,
                native_limit_field=cfg.LOKI_QUOTA_NATIVE_LIMIT_FIELD,
                native_used_field=cfg.LOKI_QUOTA_NATIVE_USED_FIELD,
                prom_limit_query=cfg.LOKI_QUOTA_PROM_LIMIT_QUERY,
                prom_used_query=cfg.LOKI_QUOTA_PROM_USED_QUERY,
                tenant_id=resolved_scope,
            ),
            tempo=await self._resolve_runtime_quota(
                service_name="tempo",
                base_url=cfg.TEMPO_URL,
                native_path=cfg.TEMPO_QUOTA_NATIVE_PATH,
                native_limit_field=cfg.TEMPO_QUOTA_NATIVE_LIMIT_FIELD,
                native_used_field=cfg.TEMPO_QUOTA_NATIVE_USED_FIELD,
                prom_limit_query=cfg.TEMPO_QUOTA_PROM_LIMIT_QUERY,
                prom_used_query=cfg.TEMPO_QUOTA_PROM_USED_QUERY,
                tenant_id=resolved_scope,
            ),
        )
