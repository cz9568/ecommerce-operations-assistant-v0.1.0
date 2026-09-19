from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from backend.app.api.schemas.products import Money
from backend.app.api.schemas.stores import StorePlatform

CompetitorStatus = Literal["active", "inactive"]
ParseTaskStatus = Literal["pending", "running", "succeeded", "failed", "cancelled", "timeout"]
MonitorStatus = Literal["active", "paused", "failed"]
CompetitorField = Literal[
    "name",
    "url",
    "price",
    "sales_hint",
    "title",
    "main_image",
    "selling_points",
    "review_keywords",
]
_url_adapter = TypeAdapter(AnyHttpUrl)


def _required(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("字段不能为空")
    return stripped


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def _url(value: str | None) -> str | None:
    value = _optional(value)
    return str(_url_adapter.validate_python(value)) if value else None


class CompetitorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    platform: StorePlatform
    url: str | None = Field(default=None, max_length=2048)
    price: Money | None = None
    sales_hint: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=500)
    main_image: str | None = Field(default=None, max_length=2048)
    selling_points: str | None = Field(default=None, max_length=10000)
    review_keywords: str | None = Field(default=None, max_length=10000)
    status: CompetitorStatus = "active"

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _required(value)

    @field_validator("sales_hint", "title", "selling_points", "review_keywords")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        return _optional(value)

    @field_validator("url", "main_image")
    @classmethod
    def validate_urls(cls, value: str | None) -> str | None:
        return _url(value)


class CompetitorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    platform: StorePlatform | None = None
    url: str | None = Field(default=None, max_length=2048)
    price: Money | None = None
    sales_hint: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=500)
    main_image: str | None = Field(default=None, max_length=2048)
    selling_points: str | None = Field(default=None, max_length=10000)
    review_keywords: str | None = Field(default=None, max_length=10000)
    status: CompetitorStatus | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("竞品名称不能设为空")
        return _required(value)

    @field_validator("platform", "status")
    @classmethod
    def validate_required_enum(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("字段不能设为空")
        return value

    @field_validator("sales_hint", "title", "selling_points", "review_keywords")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        return _optional(value)

    @field_validator("url", "main_image")
    @classmethod
    def validate_urls(cls, value: str | None) -> str | None:
        return _url(value)

    @model_validator(mode="after")
    def contains_change(self) -> "CompetitorUpdate":
        if not self.model_fields_set:
            raise ValueError("至少需要提供一个待更新字段")
        return self


class CompetitorResponse(BaseModel):
    id: int
    product_id: int
    name: str
    platform: StorePlatform
    url: str | None
    price: Decimal | None
    sales_hint: str | None
    title: str | None
    main_image: str | None
    selling_points: str | None
    review_keywords: str | None
    status: CompetitorStatus
    field_sources: dict[str, Literal["manual", "parsed", "monitor"]]
    last_parsed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ParseTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_url: str = Field(min_length=1, max_length=2048)
    competitor_id: int | None = Field(default=None, ge=1)

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        return _url(value) or ""


class ParseResult(BaseModel):
    title: str | None = None
    price: Decimal | None = None
    sales_hint: str | None = None
    main_image: str | None = None
    selling_points: str | None = None
    review_keywords: str | None = None


class ParseTaskResponse(BaseModel):
    id: int
    product_id: int
    competitor_id: int | None
    source_url: str
    task_status: ParseTaskStatus
    attempts: int
    max_attempts: int
    result: ParseResult | None
    final_url: str | None
    http_status: int | None
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    applied_at: datetime | None
    applied_by: int | None
    created_at: datetime
    updated_at: datetime


class ParseTaskApply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    competitor_id: int | None = Field(default=None, ge=1)
    fields: list[CompetitorField] = Field(min_length=1, max_length=8)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    platform: StorePlatform | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return _optional(value)

    @field_validator("fields")
    @classmethod
    def unique_fields(cls, value: list[CompetitorField]) -> list[CompetitorField]:
        return list(dict.fromkeys(value))


class MonitorUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")
    monitor_status: Literal["active", "paused"] = "active"
    interval_minutes: int = Field(default=1440, ge=60, le=10080)


class MonitorResponse(BaseModel):
    id: int
    competitor_id: int
    monitor_status: MonitorStatus
    interval_minutes: int
    next_run_at: datetime | None
    last_error: str | None
    last_error_code: str | None
    consecutive_failures: int
    last_run_at: datetime | None
    last_success_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MonitorSnapshotResponse(BaseModel):
    id: int
    monitor_id: int
    price: Decimal | None
    sales_hint: str | None
    title: str | None
    main_image: str | None
    selling_points: str | None
    review_keywords: str | None
    source_url: str | None
    changed_fields: list[str]
    is_success: bool
    error_code: str | None
    error_message: str | None
    created_at: datetime


class MonitorRunSummary(BaseModel):
    due_count: int = Field(ge=0)
    claimed_count: int = Field(ge=0)
    succeeded_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)


class SnapshotApply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[CompetitorField] = Field(min_length=1, max_length=8)

    @field_validator("fields")
    @classmethod
    def unique_fields(cls, value: list[CompetitorField]) -> list[CompetitorField]:
        return list(dict.fromkeys(value))
