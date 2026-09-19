from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DiagnosisGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_review_report_id: int | None = Field(default=None, ge=1)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class DiagnosisUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    positioning: str | None = Field(default=None, min_length=1, max_length=4000)
    price_band: str | None = Field(default=None, min_length=1, max_length=4000)
    audience_insights: str | None = Field(default=None, min_length=1, max_length=4000)
    pain_points: str | None = Field(default=None, min_length=1, max_length=4000)
    selling_point_analysis: str | None = Field(default=None, min_length=1, max_length=4000)
    risks: str | None = Field(default=None, min_length=1, max_length=4000)
    recommendations: str | None = Field(default=None, min_length=1, max_length=4000)
    expected_version: int = Field(ge=1)

    @field_validator(
        "positioning",
        "price_band",
        "audience_insights",
        "pain_points",
        "selling_point_analysis",
        "risks",
        "recommendations",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("诊断字段不能设为空")
        stripped = value.strip()
        if not stripped:
            raise ValueError("诊断字段不能为空")
        return stripped

    @model_validator(mode="after")
    def contains_content_change(self) -> "DiagnosisUpdate":
        if not (set(self.model_fields_set) - {"expected_version"}):
            raise ValueError("至少需要提供一个待更新的诊断字段")
        return self


class DiagnosisResponse(BaseModel):
    id: int
    product_id: int
    source_type: str
    source_review_report_id: int | None
    positioning: str
    price_band: str
    audience_insights: str
    pain_points: str
    selling_point_analysis: str
    risks: str
    recommendations: str
    input_snapshot: dict[str, Any]
    model_name: str
    provider_name: str
    prompt_version: str
    schema_version: str
    generated_by: int | None
    edited_by: int | None
    edited_at: datetime | None
    version_no: int
    created_at: datetime
    updated_at: datetime
