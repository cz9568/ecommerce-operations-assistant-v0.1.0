from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class DashboardMetrics(BaseModel):
    store_count: int = Field(ge=0)
    product_count: int = Field(ge=0)
    low_stock_count: int = Field(ge=0)
    active_job_count: int = Field(ge=0)
    pending_asset_count: int = Field(ge=0)
    review_report_count: int = Field(ge=0)


class DashboardStoreCard(BaseModel):
    id: int
    store_name: str
    platform: str
    status: str
    product_count: int
    low_stock_count: int
    active_job_count: int
    latest_review_at: datetime | None


class DashboardProductItem(BaseModel):
    id: int
    name: str
    store_id: int
    store_name: str
    platform: str
    status: str
    low_stock_count: int
    latest_job_status: str | None
    latest_review_at: datetime | None


class DashboardLowStockItem(BaseModel):
    product_id: int
    product_name: str
    sku_id: int
    sku_code: str
    available_qty: int
    warning_threshold: int


class DashboardRecentJob(BaseModel):
    id: int
    product_id: int
    product_name: str
    job_kind: str
    job_status: str
    progress_percent: int
    created_at: datetime


class DashboardRecentReview(BaseModel):
    id: int
    product_id: int
    product_name: str
    period_start: date
    period_end: date
    roi: Decimal | None
    created_at: datetime


class DashboardResponse(BaseModel):
    platform: str | None
    available_platforms: list[str]
    metrics: DashboardMetrics
    stores: list[DashboardStoreCard]
    products: list[DashboardProductItem]
    low_stock: list[DashboardLowStockItem]
    recent_jobs: list[DashboardRecentJob]
    recent_reviews: list[DashboardRecentReview]
    has_demo_data: bool
