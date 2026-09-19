from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CreativePlanType = Literal["main_image", "video_script"]
CreativePlanStatus = Literal["draft", "selected", "archived"]


class CreativePlanGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_type: CreativePlanType
    diagnosis_id: int | None = Field(default=None, ge=1)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class CreativePlanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: dict[str, Any]
    expected_version: int = Field(ge=1)


class CreativePlanStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CreativePlanStatus
    expected_version: int = Field(ge=1)


class CreativePlanResponse(BaseModel):
    id: int
    product_id: int
    plan_type: CreativePlanType
    generation_batch_id: str | None
    title: str
    content: dict[str, Any]
    rationale: str | None
    status: CreativePlanStatus
    input_snapshot: dict[str, Any]
    provider_name: str
    model_name: str
    prompt_version: str
    schema_version: str
    generated_by: int | None
    edited_by: int | None
    edited_at: datetime | None
    version_no: int
    created_at: datetime
    updated_at: datetime


class CreativePlanRevisionResponse(BaseModel):
    id: int
    creative_plan_id: int
    version_no: int
    title: str
    content: dict[str, Any]
    rationale: str | None
    status: CreativePlanStatus
    changed_by: int | None
    created_at: datetime
