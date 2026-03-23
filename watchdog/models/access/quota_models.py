"""
Quota response models for tenant/runtime limit visibility.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


QuotaSource = Literal["native", "prometheus", "computed", "none"]
QuotaStatus = Literal["ok", "degraded", "unavailable"]


class RuntimeQuota(BaseModel):
    service: Literal["loki", "tempo"]
    tenant_id: str
    limit: Optional[float] = None
    used: Optional[float] = None
    remaining: Optional[float] = None
    source: QuotaSource = "none"
    status: QuotaStatus = "unavailable"
    updated_at: datetime
    message: Optional[str] = None


class ApiKeyQuota(BaseModel):
    current: int
    max: int
    remaining: int
    status: QuotaStatus = "ok"


class QuotasResponse(BaseModel):
    api_keys: ApiKeyQuota
    loki: RuntimeQuota
    tempo: RuntimeQuota
