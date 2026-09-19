from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RecordStatus = Literal["active", "voided"]


class PerformanceRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    creative_plan_id: int | None = Field(default=None, ge=1)
    generated_asset_id: int | None = Field(default=None, ge=1)
    promotion_link_id: int | None = Field(default=None, ge=1)
    experiment_id: int | None = Field(default=None, ge=1)
    period_start: date
    period_end: date
    impressions: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    conversions: int = Field(default=0, ge=0)
    spend: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    revenue: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else None
        return normalized or None

    @model_validator(mode="after")
    def validate_metrics(self) -> "PerformanceRecordCreate":
        if self.period_end < self.period_start:
            raise ValueError("周期结束日期不能早于开始日期")
        if self.clicks > self.impressions:
            raise ValueError("点击数不能超过曝光数")
        if self.conversions > self.clicks:
            raise ValueError("转化数不能超过点击数")
        return self


class PerformanceRecordUpdate(PerformanceRecordCreate):
    expected_version: int = Field(ge=1)


class PerformanceRecordResponse(BaseModel):
    id: int
    product_id: int
    creative_plan_id: int | None
    generated_asset_id: int | None
    promotion_link_id: int | None
    experiment_id: int | None
    period_start: date
    period_end: date
    impressions: int
    clicks: int
    ctr: Decimal | None
    conversions: int
    conversion_rate: Decimal | None
    spend: Decimal
    revenue: Decimal
    roi: Decimal | None
    notes: str | None
    record_status: RecordStatus
    version_no: int
    created_by: int | None
    updated_by: int | None
    voided_by: int | None
    voided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PerformanceSummary(BaseModel):
    period_start: date | None
    period_end: date | None
    record_count: int
    impressions: int
    clicks: int
    ctr: Decimal | None
    conversions: int
    conversion_rate: Decimal | None
    spend: Decimal
    revenue: Decimal
    roi: Decimal | None


class ReviewReportGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_start: date
    period_end: date
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else None
        return normalized or None

    @model_validator(mode="after")
    def validate_period(self) -> "ReviewReportGenerateRequest":
        if self.period_end < self.period_start:
            raise ValueError("周期结束日期不能早于开始日期")
        if (self.period_end - self.period_start).days > 366:
            raise ValueError("单次复盘周期不能超过 366 天")
        return self


class ReviewReportUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    summary: str | None = Field(default=None, min_length=1, max_length=4000)
    core_insights: str | None = Field(default=None, min_length=1, max_length=4000)
    problem_assessment: str | None = Field(default=None, min_length=1, max_length=4000)
    next_actions: str | None = Field(default=None, min_length=1, max_length=4000)

    @field_validator("summary", "core_insights", "problem_assessment", "next_actions")
    @classmethod
    def normalize_content(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else None
        if normalized is None:
            raise ValueError("复盘内容不能为空")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> "ReviewReportUpdate":
        if not (set(self.model_fields_set) - {"expected_version"}):
            raise ValueError("至少提供一个需要更新的字段")
        return self


class FollowUpDiagnosis(BaseModel):
    id: int
    version_no: int
    created_at: datetime


class ReviewReportResponse(BaseModel):
    id: int
    product_id: int
    period_start: date
    period_end: date
    summary: str
    core_insights: list[str]
    problem_assessment: list[str]
    next_actions: list[str]
    input_snapshot: dict
    provider_name: str
    model_name: str
    prompt_version: str
    schema_version: str
    generated_by: int | None
    edited_by: int | None
    edited_at: datetime | None
    version_no: int
    follow_up_diagnoses: list[FollowUpDiagnosis]
    created_at: datetime
    updated_at: datetime


class ReviewReportRevisionResponse(BaseModel):
    id: int
    review_report_id: int
    version_no: int
    summary: str
    core_insights: list[str]
    problem_assessment: list[str]
    next_actions: list[str]
    changed_by: int | None
    created_at: datetime
