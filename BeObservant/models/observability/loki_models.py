"""
Module defines Pydantic models for Loki-related data structures used in the API layer.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from enum import Enum

from custom_types.json import JSONDict

MAX_LOG_ENTRIES_DESC = "Maximum number of log entries to return"
TIME_NS_START_DESC = "Start time in nanoseconds"
TIME_NS_END_DESC = "End time in nanoseconds"
RESPONSE_STATUS_DESC = "Response status"

class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    FATAL = "fatal"

class LogDirection(str, Enum):
    FORWARD = "forward"
    BACKWARD = "backward"

class LogEntry(BaseModel):
    timestamp: str = Field(..., description="Timestamp of the log entry")
    line: str = Field(..., description="Content of the log line")
    labels: Optional[Dict[str, str]] = Field(default_factory=dict, description="Labels associated with the log entry")

class LogStream(BaseModel):
    stream: Dict[str, str] = Field(..., description="Labels that identify this stream")
    values: List[List[str]] = Field(..., description="List of [timestamp, line] pairs")

class LogQuery(BaseModel):
    query: str = Field(..., description="LogQL query string")
    limit: int = Field(100, ge=1, le=5000, description=MAX_LOG_ENTRIES_DESC)
    start: Optional[int] = Field(None, description=TIME_NS_START_DESC)
    end: Optional[int] = Field(None, description=TIME_NS_END_DESC)
    direction: LogDirection = Field(LogDirection.BACKWARD, description="Direction to search logs")
    step: Optional[int] = Field(None, description="Query resolution step in seconds")

class LogStatsResponse(BaseModel):
    total_entries: int = Field(..., description="Total number of log entries")
    total_bytes: int = Field(..., description="Total size of log data in bytes")
    streams: int = Field(..., description="Number of log streams")
    chunks: int = Field(..., description="Number of log chunks")

class LogResponse(BaseModel):
    status: str = Field(..., description=RESPONSE_STATUS_DESC)
    data: JSONDict = Field(..., description="Log data containing streams and statistics")
    stats: Optional[LogStatsResponse] = None

class LogLabelsResponse(BaseModel):
    status: str = Field(..., description=RESPONSE_STATUS_DESC)
    data: List[str] = Field(..., description="List of available label names")

class LogLabelValuesResponse(BaseModel):
    status: str = Field(..., description=RESPONSE_STATUS_DESC)
    data: List[str] = Field(..., description="List of values for the label")

class LogFilterRequest(BaseModel):
    labels: Dict[str, str] = Field(..., description="Labels to filter logs by")
    filters: Optional[List[str]] = Field(None, description="Additional filter expressions")
    start: Optional[int] = Field(None, description=TIME_NS_START_DESC)
    end: Optional[int] = Field(None, description=TIME_NS_END_DESC)
    limit: int = Field(100, ge=1, le=5000, description=MAX_LOG_ENTRIES_DESC)

class LogSearchRequest(BaseModel):
    pattern: str = Field(..., description="Search pattern or LogQL query")
    labels: Optional[Dict[str, str]] = Field(None, description="Labels to filter search results")
    start: Optional[int] = Field(None, description=TIME_NS_START_DESC)
    end: Optional[int] = Field(None, description=TIME_NS_END_DESC)
    limit: int = Field(100, ge=1, le=5000, description=MAX_LOG_ENTRIES_DESC)
