from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

StorePlatform = Literal[
    "taobao",
    "tmall",
    "jd",
    "pinduoduo",
    "douyin",
    "kuaishou",
    "xiaohongshu",
    "wechat",
    "other",
]
StoreStatus = Literal["active", "inactive"]


def _strip_required(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("字段不能为空")
    return stripped


def _strip_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class StoreCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_name: str = Field(min_length=1, max_length=150)
    platform: StorePlatform
    external_store_id: str | None = Field(default=None, max_length=128)
    owner_user_id: int | None = Field(default=None, ge=1)
    status: StoreStatus = "active"
    remark: str | None = Field(default=None, max_length=2000)

    @field_validator("store_name")
    @classmethod
    def strip_store_name(cls, value: str) -> str:
        return _strip_required(value)

    @field_validator("external_store_id", "remark")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return _strip_optional(value)


class StoreUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_name: str | None = Field(default=None, min_length=1, max_length=150)
    platform: StorePlatform | None = None
    external_store_id: str | None = Field(default=None, max_length=128)
    owner_user_id: int | None = Field(default=None, ge=1)
    status: StoreStatus | None = None
    remark: str | None = Field(default=None, max_length=2000)

    @field_validator("store_name")
    @classmethod
    def strip_store_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("店铺名称不能设为空")
        return _strip_required(value)

    @field_validator("platform", "status")
    @classmethod
    def reject_null_required_fields(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("字段不能设为空")
        return value

    @field_validator("external_store_id", "remark")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return _strip_optional(value)

    @model_validator(mode="after")
    def contains_change(self) -> "StoreUpdate":
        if not self.model_fields_set:
            raise ValueError("至少需要提供一个待更新字段")
        return self


class StoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    store_name: str
    platform: StorePlatform
    external_store_id: str | None
    owner_user_id: int | None
    owner_name: str | None
    status: StoreStatus
    remark: str | None
    product_count: int = Field(ge=0)
    low_stock_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class StoreSummaryResponse(BaseModel):
    store_id: int
    product_count: int = Field(ge=0)
    sku_count: int = Field(ge=0)
    low_stock_count: int = Field(ge=0)
    platform_account_count: int = Field(ge=0)
    authorized_account_count: int = Field(ge=0)
