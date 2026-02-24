"""
Pydantic models for BeCertain proxy and RCA job endpoints.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnalyzeRequestPayload(BaseModel):
    tenant_id: Optional[str] = None
    start: int
    end: int
    step: str = "15s"
    services: List[str] = Field(default_factory=list)
    log_query: Optional[str] = None
    metric_queries: Optional[List[str]] = None
    sensitivity: Optional[float] = Field(default=3.0, ge=1.0, le=6.0)
    apdex_threshold_ms: float = 500.0
    slo_target: float = Field(default=0.999, ge=0.0, le=1.0)
    correlation_window_seconds: float = Field(default=60.0, ge=10.0, le=600.0)
    forecast_horizon_seconds: float = Field(default=1800.0, ge=60.0, le=86400.0)

    @model_validator(mode="after")
    def validate_time_range(self) -> "AnalyzeRequestPayload":
        if self.start >= self.end:
            raise ValueError("start must be less than end")
        return self


class AnalyzeProxyPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    tenant_id: Optional[str] = None


class AnalyzeJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DELETED = "deleted"


class AnalyzeJobCreateResponse(BaseModel):
    job_id: str
    report_id: str
    status: AnalyzeJobStatus
    created_at: datetime
    tenant_id: str
    requested_by: str


class AnalyzeJobSummary(BaseModel):
    job_id: str
    report_id: str
    status: AnalyzeJobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    summary_preview: Optional[str] = None
    tenant_id: str
    requested_by: str


class AnalyzeJobListResponse(BaseModel):
    items: List[AnalyzeJobSummary]
    next_cursor: Optional[str] = None


class AnalyzeJobResultResponse(BaseModel):
    job_id: str
    report_id: str
    status: AnalyzeJobStatus
    tenant_id: str
    requested_by: str
    result: Optional[Dict[str, Any]] = None


class AnalyzeReportResponse(BaseModel):
    job_id: str
    report_id: str
    status: AnalyzeJobStatus
    tenant_id: str
    requested_by: str
    result: Optional[Dict[str, Any]] = None


class AnalyzeReportDeleteResponse(BaseModel):
    report_id: str
    status: AnalyzeJobStatus = AnalyzeJobStatus.DELETED
    deleted: bool = True
