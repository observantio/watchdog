"""
Resolver models for Watchdog observability analysis.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from custom_types.json import JSONDict

class AnalyzeRequestPayload(BaseModel):
    tenant_id: Optional[str] = None
    start: int
    end: int
    step: str = "15s"
    config_yaml: Optional[str] = None
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
    PENDING = "pending"
    ACCEPTED = "accepted"
    PROCESSING = "processing"
    SUBMITTED = "submitted"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DELETED = "deleted"

    @classmethod
    def _missing_(cls, value: object) -> "AnalyzeJobStatus":
        if isinstance(value, str):
            normalized = value.strip().lower()
            aliases = {
                "success": cls.COMPLETED,
                "succeeded": cls.COMPLETED,
                "done": cls.COMPLETED,
                "finished": cls.COMPLETED,
                "complete": cls.COMPLETED,
                "in_progress": cls.RUNNING,
                "started": cls.RUNNING,
                "error": cls.FAILED,
            }
            aliased = aliases.get(normalized)
            if aliased is not None:
                return aliased
            for member in cls:
                if member.value == normalized:
                    return member
        return cls.PENDING

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

class AnalysisQualityPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    anomaly_density: Dict[str, float] = Field(default_factory=dict)
    suppression_counts: Dict[str, int] = Field(default_factory=dict)
    gating_profile: Optional[str] = None
    confidence_calibration_version: Optional[str] = None

class ServiceLatencyPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    service: Optional[str] = None
    operation: Optional[str] = None
    window_start: Optional[float] = None
    window_end: Optional[float] = None

class RootCausePayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    hypothesis: Optional[str] = None
    corroboration_summary: Optional[str] = None
    suppression_diagnostics: JSONDict = Field(default_factory=dict)
    selection_score_components: Dict[str, float] = Field(default_factory=dict)

class AnalyzeResultPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    quality: Optional[AnalysisQualityPayload] = None
    service_latency: List[ServiceLatencyPayload] = Field(default_factory=list)
    root_causes: List[RootCausePayload] = Field(default_factory=list)

class AnalyzeJobResultResponse(BaseModel):
    job_id: str
    report_id: str
    status: AnalyzeJobStatus
    tenant_id: str
    requested_by: str
    result: Optional[AnalyzeResultPayload | JSONDict] = None

class AnalyzeReportResponse(BaseModel):
    job_id: str
    report_id: str
    status: AnalyzeJobStatus
    tenant_id: str
    requested_by: str
    result: Optional[AnalyzeResultPayload | JSONDict] = None

class AnalyzeReportDeleteResponse(BaseModel):
    report_id: str
    status: AnalyzeJobStatus = AnalyzeJobStatus.DELETED
    deleted: bool = True

class AnalyzeConfigTemplateResponse(BaseModel):
    version: int
    defaults: JSONDict
    template_yaml: str
    file_name: str
