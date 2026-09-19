from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ImportType = Literal["products", "sku_inventory", "performance_records"]
ImportStatus = Literal["uploaded", "validated", "importing", "completed", "failed", "cancelled"]
ImportRowStatus = Literal["valid", "invalid", "imported", "failed"]


class ImportError(BaseModel):
    column: str | None = None
    code: str
    message: str


class ImportRowResponse(BaseModel):
    id: int
    batch_id: int
    row_number: int
    row_status: ImportRowStatus
    raw_data: dict[str, Any]
    normalized_data: dict[str, Any] | None
    errors: list[ImportError]
    target_type: str | None
    target_id: str | None


class ImportBatchResponse(BaseModel):
    id: int
    import_type: ImportType
    batch_status: ImportStatus
    original_filename: str
    idempotency_key: str
    total_rows: int = Field(ge=0)
    valid_rows: int = Field(ge=0)
    success_rows: int = Field(ge=0)
    failed_rows: int = Field(ge=0)
    created_by: int | None
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ImportBatchPage(BaseModel):
    items: list[ImportBatchResponse]
    page: int
    page_size: int
    total: int


class ImportPreviewResponse(BaseModel):
    batch: ImportBatchResponse
    rows: list[ImportRowResponse]
    field_notes: dict[str, str]


class DemoDataResponse(BaseModel):
    created: bool
    marker: str
    store_id: int
    product_id: int
    sku_id: int
    object_ids: dict[str, int]
    message: str
