from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.api.schemas.products import Money

SkuStatus = Literal["active", "inactive"]


def _strip_required(value: str, *, field_label: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_label}不能为空")
    return stripped


def _strip_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_specs(value: dict[str, str] | None) -> dict[str, str] | None:
    if value is None:
        return None
    if len(value) > 20:
        raise ValueError("SKU 规格最多允许 20 项")
    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = _strip_required(raw_key, field_label="规格名称")
        spec_value = _strip_required(raw_value, field_label="规格值")
        if len(key) > 50:
            raise ValueError("规格名称不能超过 50 个字符")
        if len(spec_value) > 100:
            raise ValueError("规格值不能超过 100 个字符")
        if key in normalized:
            raise ValueError("规格名称不能重复")
        normalized[key] = spec_value
    return normalized


class SkuCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku_code: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    sku_name: str = Field(min_length=1, max_length=255)
    specs: dict[str, str] = Field(default_factory=dict)
    price: Money = Decimal("0")
    cost: Money | None = None
    status: SkuStatus = "active"
    platform_sku_id: str | None = Field(default=None, max_length=128)

    @field_validator("sku_code")
    @classmethod
    def normalize_sku_code(cls, value: str) -> str:
        return _strip_required(value, field_label="SKU 编码")

    @field_validator("sku_name")
    @classmethod
    def normalize_sku_name(cls, value: str) -> str:
        return _strip_required(value, field_label="SKU 名称")

    @field_validator("specs")
    @classmethod
    def validate_specs(cls, value: dict[str, str]) -> dict[str, str]:
        return _normalize_specs(value) or {}

    @field_validator("platform_sku_id")
    @classmethod
    def normalize_platform_sku_id(cls, value: str | None) -> str | None:
        return _strip_optional(value)


class SkuUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    sku_name: str | None = Field(default=None, min_length=1, max_length=255)
    specs: dict[str, str] | None = None
    price: Money | None = None
    cost: Money | None = None
    platform_sku_id: str | None = Field(default=None, max_length=128)

    @field_validator("sku_code")
    @classmethod
    def normalize_sku_code(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("SKU 编码不能设为空")
        return _strip_required(value, field_label="SKU 编码")

    @field_validator("sku_name")
    @classmethod
    def normalize_sku_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("SKU 名称不能设为空")
        return _strip_required(value, field_label="SKU 名称")

    @field_validator("price")
    @classmethod
    def reject_null_price(cls, value: Decimal | None) -> Decimal:
        if value is None:
            raise ValueError("SKU 价格不能设为空")
        return value

    @field_validator("specs")
    @classmethod
    def validate_specs(cls, value: dict[str, str] | None) -> dict[str, str]:
        return _normalize_specs(value) or {}

    @field_validator("platform_sku_id")
    @classmethod
    def normalize_platform_sku_id(cls, value: str | None) -> str | None:
        return _strip_optional(value)

    @model_validator(mode="after")
    def contains_change(self) -> "SkuUpdate":
        if not self.model_fields_set:
            raise ValueError("至少需要提供一个待更新字段")
        return self


class SkuStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SkuStatus


class SkuResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    store_id: int
    sku_code: str
    sku_name: str
    specs: dict[str, str]
    price: Decimal
    cost: Decimal | None
    status: SkuStatus
    platform_sku_id: str | None
    created_at: datetime
    updated_at: datetime
