from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LinkStatus = Literal["active", "inactive"]
RecommendationStatus = Literal["pending", "confirmed", "rejected"]
ExperimentStatus = Literal["draft", "confirmed", "running", "finished", "cancelled"]


def _optional_text(value: str | None) -> str | None:
    normalized = value.strip() if value else None
    return normalized or None


class PromotionLinkSuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_url: str | None = Field(default=None, max_length=2048)

    _normalize_target = field_validator("target_url")(_optional_text)


class PromotionLinkSuggestion(BaseModel):
    link_name: str
    target_url: str
    scene_text: str
    utm: dict[str, str]


class PromotionLinkSuggestionResponse(BaseModel):
    suggestions: list[PromotionLinkSuggestion]


class PromotionLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_name: str = Field(min_length=1, max_length=255)
    target_url: str = Field(min_length=1, max_length=2048)
    utm: dict[str, str] = Field(default_factory=dict)
    scene_text: str | None = Field(default=None, max_length=255)

    @field_validator("link_name", "target_url")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空")
        return normalized

    _normalize_scene = field_validator("scene_text")(_optional_text)


class PromotionLinkUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    link_name: str | None = Field(default=None, min_length=1, max_length=255)
    target_url: str | None = Field(default=None, min_length=1, max_length=2048)
    utm: dict[str, str] | None = None
    scene_text: str | None = Field(default=None, max_length=255)
    status: LinkStatus | None = None

    @field_validator("link_name", "target_url")
    @classmethod
    def normalize_optional_required(cls, value: str | None) -> str | None:
        normalized = _optional_text(value)
        if normalized is None:
            raise ValueError("字段不能为空")
        return normalized

    _normalize_scene = field_validator("scene_text")(_optional_text)

    @model_validator(mode="after")
    def require_change(self) -> "PromotionLinkUpdate":
        if not (set(self.model_fields_set) - {"expected_version"}):
            raise ValueError("至少提供一个需要更新的字段")
        return self


class PromotionLinkResponse(BaseModel):
    id: int
    product_id: int
    link_name: str
    target_url: str
    redirect_path: str
    tracking_code: str
    utm: dict[str, str]
    status: LinkStatus
    click_count: int
    scene_text: str | None
    lock_version: int
    created_at: datetime
    updated_at: datetime


class PromotionClickDay(BaseModel):
    day: date
    counted_clicks: int
    filtered_clicks: int
    unique_visitors: int


class PromotionLinkStatistics(BaseModel):
    promotion_link_id: int
    period_start: date
    period_end: date
    counted_clicks: int
    filtered_clicks: int
    unique_visitors: int
    daily: list[PromotionClickDay]


class AdRecommendationGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_ids: list[int] = Field(min_length=1, max_length=20)
    link_ids: list[int] = Field(min_length=1, max_length=20)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("asset_ids", "link_ids")
    @classmethod
    def unique_ids(cls, value: list[int]) -> list[int]:
        if any(item < 1 for item in value):
            raise ValueError("ID 必须为正整数")
        return list(dict.fromkeys(value))

    _normalize_notes = field_validator("notes")(_optional_text)


class AdRecommendationConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    confirm_status: Literal["confirmed", "rejected"]
    remark: str | None = Field(default=None, max_length=2000)

    _normalize_remark = field_validator("remark")(_optional_text)


class AdRecommendationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    strategy_summary: str | None = Field(default=None, min_length=1, max_length=4000)
    objective: str | None = Field(default=None, min_length=1, max_length=2000)
    target_audience: str | None = Field(default=None, min_length=1, max_length=4000)
    budget_plan: str | None = Field(default=None, min_length=1, max_length=4000)
    creative_test_plan: str | None = Field(default=None, min_length=1, max_length=4000)
    bidding_strategy: str | None = Field(default=None, min_length=1, max_length=4000)
    risks: str | None = Field(default=None, min_length=1, max_length=4000)
    next_actions: str | None = Field(default=None, min_length=1, max_length=4000)

    @field_validator(
        "strategy_summary",
        "objective",
        "target_audience",
        "budget_plan",
        "creative_test_plan",
        "bidding_strategy",
        "risks",
        "next_actions",
    )
    @classmethod
    def normalize_content(cls, value: str | None) -> str | None:
        normalized = _optional_text(value)
        if normalized is None:
            raise ValueError("建议内容不能为空")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> "AdRecommendationUpdate":
        if not (set(self.model_fields_set) - {"expected_version"}):
            raise ValueError("至少提供一个需要更新的字段")
        return self


class AdRecommendationResponse(BaseModel):
    id: int
    product_id: int
    summary_text: str
    objective_text: str
    audience_segments: list[dict[str, Any]]
    budget_plan: dict[str, Any]
    creative_tests: list[dict[str, Any]]
    bid_strategy: dict[str, Any]
    risk_controls: list[str]
    next_steps: list[str]
    confirm_status: RecommendationStatus
    confirmed_by: int | None
    confirmed_at: datetime | None
    confirm_remark: str | None
    input_snapshot: dict[str, Any]
    provider_name: str
    model_name: str
    prompt_version: str
    schema_version: str
    generated_by: int | None
    version_no: int
    created_at: datetime
    updated_at: datetime


class AdExperimentGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_id: int = Field(ge=1)
    related_asset_id: int = Field(ge=1)
    related_link_id: int = Field(ge=1)
    experiment_name: str | None = Field(default=None, max_length=255)
    budget_amount: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)

    _normalize_name = field_validator("experiment_name")(_optional_text)


class AdExperimentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    experiment_name: str | None = Field(default=None, min_length=1, max_length=255)
    target_text: str | None = Field(default=None, max_length=4000)
    audience_text: str | None = Field(default=None, max_length=4000)
    budget_amount: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    success_metric_text: str | None = Field(default=None, max_length=4000)
    hypothesis_text: str | None = Field(default=None, max_length=4000)
    experiment_status: ExperimentStatus | None = None

    @field_validator(
        "experiment_name",
        "target_text",
        "audience_text",
        "success_metric_text",
        "hypothesis_text",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return _optional_text(value)

    @field_validator("experiment_name")
    @classmethod
    def require_experiment_name(cls, value: str | None) -> str | None:
        normalized = _optional_text(value)
        if normalized is None:
            raise ValueError("实验名称不能为空")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> "AdExperimentUpdate":
        if not (set(self.model_fields_set) - {"expected_version"}):
            raise ValueError("至少提供一个需要更新的字段")
        return self


class AdExperimentResponse(BaseModel):
    id: int
    product_id: int
    recommendation_id: int | None
    related_asset_id: int | None
    related_link_id: int | None
    experiment_name: str
    target_text: str | None
    audience_text: str | None
    budget_amount: Decimal
    success_metric_text: str | None
    hypothesis_text: str | None
    experiment_status: ExperimentStatus
    version_no: int
    created_at: datetime
    updated_at: datetime
