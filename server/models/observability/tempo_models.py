"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


"""Tempo/Tracing related models."""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime

class SpanAttribute(BaseModel):
    """Span attribute key-value pair."""
    key: str = Field(..., description="Attribute key")
    value: Any = Field(..., description="Attribute value")

class Span(BaseModel):
    """Trace span representation."""
    span_id: str = Field(..., alias="spanID", description="Unique identifier for the span")
    trace_id: str = Field(..., alias="traceID", description="Identifier of the trace this span belongs to")
    parent_span_id: Optional[str] = Field(None, alias="parentSpanID", description="Parent span ID if this is a child span")
    operation_name: str = Field(..., alias="operationName", description="Name of the operation this span represents")
    start_time: int = Field(..., alias="startTime", description="Start time of the span in microseconds")
    duration: int = Field(..., description="Duration of the span in microseconds")
    tags: List[SpanAttribute] = Field(default_factory=list, description="Tags associated with the span")
    service_name: Optional[str] = Field(None, alias="serviceName", description="Service name that emitted this span")
    attributes: Optional[Dict[str, Any]] = Field(None, description="Span attributes as a key-value map")
    process_id: Optional[str] = Field(None, alias="processID", description="Identifier of the process that created this span")
    warnings: Optional[List[str]] = Field(None, description="Warnings related to this span")
    
    class Config:
        populate_by_name = True

class Trace(BaseModel):
    """Full trace with all spans."""
    trace_id: str = Field(..., alias="traceID", description="Unique identifier for the trace")
    spans: List[Span] = Field(..., description="List of spans in this trace")
    processes: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Process information for spans in this trace")
    warnings: Optional[List[str]] = Field(None, description="Warnings related to this trace")
    
    class Config:
        populate_by_name = True

class TraceQuery(BaseModel):
    """Query parameters for trace search."""
    service: Optional[str] = Field(None, description="Service name to filter traces")
    operation: Optional[str] = Field(None, description="Operation name to filter spans")
    tags: Optional[Dict[str, str]] = Field(None, description="Tags to filter traces")
    start: Optional[int] = Field(None, description="Start time in microseconds")
    end: Optional[int] = Field(None, description="End time in microseconds")
    min_duration: Optional[str] = Field(None, alias="minDuration", description="Minimum duration filter (e.g., '0ms')")
    max_duration: Optional[str] = Field(None, alias="maxDuration", description="Maximum duration filter (e.g., '1s')")
    limit: int = Field(100, ge=1, le=1000, description="Maximum number of traces to return")
    
    class Config:
        populate_by_name = True

class TraceResponse(BaseModel):
    """Response containing multiple traces."""
    data: List[Trace] = Field(..., description="List of traces matching the query")
    total: int = Field(..., description="Total number of traces available")
    limit: int = Field(..., description="Maximum number of traces requested")
    offset: int = Field(0, description="Offset for pagination")
    errors: Optional[List[str]] = Field(None, description="Any errors that occurred during the query")
