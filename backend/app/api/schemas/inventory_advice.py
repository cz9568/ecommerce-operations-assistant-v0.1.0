from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

AdviceAction = Literal["replenish", "monitor", "healthy"]
AdvicePriority = Literal["critical", "high", "medium", "low"]
AdviceDataStatus = Literal["sufficient", "insufficient"]
SafetyMultiplier = Annotated[Decimal, Field(ge=1, le=3, max_digits=3, decimal_places=2)]


class InventoryAdviceGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lookback_days: int = Field(default=30, ge=7, le=90)
    coverage_days: int = Field(default=14, ge=1, le=90)
    safety_multiplier: SafetyMultiplier = Decimal("1.20")
    min_outbound_events: int = Field(default=2, ge=1, le=20)


class InventoryAdviceItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    sku_id: int
    sku_code: str
    sku_name: str
    stock_qty: int = Field(ge=0)
    locked_qty: int = Field(ge=0)
    available_qty: int = Field(ge=0)
    warning_threshold: int = Field(ge=0)
    outbound_qty: int = Field(ge=0)
    outbound_events: int = Field(ge=0)
    daily_outbound_rate: Decimal = Field(ge=0)
    target_stock_qty: int = Field(ge=0)
    suggested_restock_qty: int = Field(ge=0)
    action: AdviceAction
    priority: AdvicePriority
    data_status: AdviceDataStatus
    explanation: str


class InventoryAdviceRunSummary(BaseModel):
    id: int
    store_id: int
    store_name: str
    rule_version: str
    lookback_days: int
    coverage_days: int
    safety_multiplier: Decimal
    min_outbound_events: int
    item_count: int = Field(ge=0)
    replenish_count: int = Field(ge=0)
    insufficient_count: int = Field(ge=0)
    message: str | None
    generated_by: int | None
    generated_at: datetime


class InventoryAdviceRunResponse(InventoryAdviceRunSummary):
    items: list[InventoryAdviceItemResponse]
