from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

JobKind = Literal["image", "video"]
JobStatus = Literal["pending", "running", "succeeded", "failed", "cancelled", "timeout"]


class GenerationJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    creative_plan_id: int = Field(ge=1)
    creative_plan_version_no: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    size: str | None = Field(default=None, max_length=30)
    duration_seconds: int | None = Field(default=None, ge=1, le=30)

    @field_validator("idempotency_key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip()


class GenerationJobActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else None
        return normalized or None


class GenerationJobResponse(BaseModel):
    id: int
    product_id: int
    creative_plan_id: int
    creative_plan_version_no: int
    job_kind: JobKind
    job_status: JobStatus
    idempotency_key: str
    provider_name: str | None
    external_job_id: str | None
    input_snapshot: dict[str, Any]
    attempts: int
    max_attempts: int
    progress_percent: int
    next_run_at: datetime | None
    result: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    requested_by: int | None
    started_at: datetime | None
    finished_at: datetime | None
    cancelled_at: datetime | None
    cancelled_by: int | None
    version_no: int
    created_at: datetime
    updated_at: datetime


class GenerationJobEventResponse(BaseModel):
    id: int
    job_id: int
    event_type: str
    event_message: str | None
    event_data: dict[str, Any]
    created_at: datetime
