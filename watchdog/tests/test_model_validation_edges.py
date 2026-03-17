from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from tests._env import ensure_test_env

ensure_test_env()

from models.access.user_models import (
    LoginRequest,
    RegisterRequest,
    TempPasswordResetResponse,
    UserCreate,
    UserUpdate,
    _normalize_username,
    _normalize_username_input,
)
from models.observability.resolver_models import (
    AnalyzeJobCreateResponse,
    AnalyzeJobStatus,
    AnalyzeRequestPayload,
)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (None, "username is required"),
        (123, "username must be a string"),
        ("bad name", "username must not contain spaces"),
        ("UP", "username must be 3-50 chars"),
    ],
)
def test_username_normalization_rejects_invalid_values(value, message):
    with pytest.raises(ValueError, match=message):
        _normalize_username(value)  # type: ignore[arg-type]


def test_username_input_normalization_and_model_validators():
    assert _normalize_username_input(" User.Name ", full_check=True) == "user.name"
    assert LoginRequest(username=" User ", password="password123").username == "user"
    assert UserCreate(username=" User.Name ", email="user@example.com", password="password123").username == "user.name"
    assert UserUpdate(username=None).username is None

    with pytest.raises(ValueError, match="username must be a string"):
        _normalize_username_input(1, full_check=False)

    with pytest.raises(ValidationError, match="username must not contain spaces"):
        RegisterRequest(username="Bad Name", email="user@example.com", password="password123")


def test_misc_model_payloads_cover_status_aliases_and_time_validation():
    response = TempPasswordResetResponse(
        temporary_password="TempPassword123!",
        email_sent=True,
        message="sent",
    )
    assert response.email_sent is True

    with pytest.raises(ValidationError, match="start must be less than end"):
        AnalyzeRequestPayload(start=10, end=10)

    created = AnalyzeJobCreateResponse(
        job_id="job-1",
        report_id="report-1",
        status="success",
        created_at=datetime.now(timezone.utc),
        tenant_id="tenant-a",
        requested_by="user-1",
    )
    assert created.status is AnalyzeJobStatus.COMPLETED
    assert AnalyzeJobStatus("completed") is AnalyzeJobStatus.COMPLETED
    assert AnalyzeJobStatus(" completed ") is AnalyzeJobStatus.COMPLETED
    assert AnalyzeJobStatus("error") is AnalyzeJobStatus.FAILED
    assert AnalyzeJobStatus(" started ") is AnalyzeJobStatus.RUNNING
    assert AnalyzeJobStatus("unknown-status") is AnalyzeJobStatus.PENDING
    assert AnalyzeJobStatus._missing_(object()) is AnalyzeJobStatus.PENDING