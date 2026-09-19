from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

InventoryMovementType = Literal["inbound", "outbound", "adjustment", "lock", "unlock"]


def _strip_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class InventoryResponse(BaseModel):
    id: int
    store_id: int
    store_name: str
    product_id: int
    product_name: str
    sku_id: int
    sku_code: str
    sku_name: str
    sku_status: Literal["active", "inactive"]
    stock_qty: int = Field(ge=0)
    locked_qty: int = Field(ge=0)
    available_qty: int = Field(ge=0)
    warning_threshold: int = Field(ge=0)
    is_low_stock: bool
    location_text: str | None
    version_no: int = Field(ge=1)
    updated_at: datetime


class InventoryConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warning_threshold: int | None = Field(default=None, ge=0, le=2_000_000_000)
    location_text: str | None = Field(default=None, max_length=255)
    expected_version: int = Field(ge=1)

    @field_validator("location_text")
    @classmethod
    def normalize_location(cls, value: str | None) -> str | None:
        return _strip_optional(value)

    @model_validator(mode="after")
    def contains_change(self) -> "InventoryConfigUpdate":
        if not ({"warning_threshold", "location_text"} & self.model_fields_set):
            raise ValueError("至少需要提供预警阈值或库位")
        if "warning_threshold" in self.model_fields_set and self.warning_threshold is None:
            raise ValueError("预警阈值不能设为空")
        return self


class InventoryAdjustmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    movement_type: InventoryMovementType
    change_qty: int = Field(ge=-2_000_000_000, le=2_000_000_000)
    reason_text: str = Field(min_length=1, max_length=500)
    reference_type: str | None = Field(default=None, max_length=50)
    reference_id: str | None = Field(default=None, max_length=128)
    expected_version: int = Field(ge=1)

    @field_validator("reason_text")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("调整原因不能为空")
        return stripped

    @field_validator("reference_type", "reference_id")
    @classmethod
    def normalize_reference(cls, value: str | None) -> str | None:
        return _strip_optional(value)

    @model_validator(mode="after")
    def validate_adjustment(self) -> "InventoryAdjustmentCreate":
        if self.change_qty == 0:
            raise ValueError("库存变更数量不能为 0")
        if self.movement_type in {"inbound", "lock"} and self.change_qty < 0:
            raise ValueError("入库或锁定数量必须为正数")
        if self.movement_type in {"outbound", "unlock"} and self.change_qty > 0:
            raise ValueError("出库或解锁数量必须为负数")
        if (self.reference_type is None) != (self.reference_id is None):
            raise ValueError("引用类型和引用编号必须同时提供")
        return self


class InventoryMovementResponse(BaseModel):
    id: int
    sku_id: int
    movement_type: InventoryMovementType
    quantity_type: Literal["stock", "locked"]
    change_qty: int
    before_qty: int = Field(ge=0)
    after_qty: int = Field(ge=0)
    reason_text: str | None
    reference_type: str | None
    reference_id: str | None
    created_by: int | None
    created_at: datetime


class InventoryAdjustmentResponse(BaseModel):
    inventory: InventoryResponse
    movement: InventoryMovementResponse
