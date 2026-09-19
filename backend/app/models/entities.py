from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin','operator','viewer')", name="ck_users_role"),
        CheckConstraint("status IN ('active','inactive')", name="ck_users_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="viewer", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthTokenRevocation(Base):
    __tablename__ = "auth_token_revocations"
    __table_args__ = (Index("ix_auth_token_revocations_expires", "expires_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Store(TimestampMixin, Base):
    __tablename__ = "stores"
    __table_args__ = (
        UniqueConstraint("platform", "external_store_id", name="uq_store_platform_external_id"),
        CheckConstraint("status IN ('active','inactive')", name="ck_stores_status"),
        Index("ix_stores_platform_status", "platform", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_name: Mapped[str] = mapped_column(String(150), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    external_store_id: Mapped[str | None] = mapped_column(String(128))
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_name: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    remark: Mapped[str | None] = mapped_column(Text)


class PlatformAccount(TimestampMixin, Base):
    __tablename__ = "platform_accounts"
    __table_args__ = (
        UniqueConstraint("store_id", "platform", "account_name", name="uq_platform_account"),
        CheckConstraint(
            "auth_status IN ('unconfigured','pending','authorized','expired','revoked','failed')",
            name="ck_platform_accounts_auth_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    account_name: Mapped[str] = mapped_column(String(128), nullable=False)
    auth_status: Mapped[str] = mapped_column(String(20), default="unconfigured", nullable=False)
    auth_meta_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    remark: Mapped[str | None] = mapped_column(Text)


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("status IN ('draft','active','inactive')", name="ck_products_status"),
        CheckConstraint("price >= 0", name="ck_products_price"),
        CheckConstraint("cost IS NULL OR cost >= 0", name="ck_products_cost"),
        Index("ix_products_store_status", "store_id", "status"),
        Index("ix_products_platform_category", "platform", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str | None] = mapped_column(String(120))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    target_audience: Mapped[str | None] = mapped_column(Text)
    selling_points: Mapped[str | None] = mapped_column(Text)
    product_url: Mapped[str | None] = mapped_column(String(2048))
    images_json: Mapped[list[Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)


class PlatformProductMapping(TimestampMixin, Base):
    __tablename__ = "platform_product_mappings"
    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "platform",
            "platform_product_id",
            "platform_sku_id",
            name="uq_store_platform_product_mapping",
        ),
        CheckConstraint(
            "mapping_status IN ('active','inactive','invalid')",
            name="ck_platform_product_mappings_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    platform_product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    platform_sku_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    mapping_status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    raw_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ProductSku(TimestampMixin, Base):
    __tablename__ = "product_skus"
    __table_args__ = (
        UniqueConstraint("product_id", "sku_code", name="uq_product_sku_code"),
        CheckConstraint("status IN ('active','inactive')", name="ck_product_skus_status"),
        CheckConstraint("price >= 0", name="ck_product_skus_price"),
        CheckConstraint("cost IS NULL OR cost >= 0", name="ck_product_skus_cost"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sku_code: Mapped[str] = mapped_column(String(100), nullable=False)
    sku_name: Mapped[str] = mapped_column(String(255), nullable=False)
    spec_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    platform_sku_id: Mapped[str | None] = mapped_column(String(128))


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        CheckConstraint("stock_qty >= 0", name="ck_inventory_items_stock"),
        CheckConstraint("locked_qty >= 0", name="ck_inventory_items_locked"),
        CheckConstraint("locked_qty <= stock_qty", name="ck_inventory_items_locked_lte_stock"),
        CheckConstraint("warning_threshold >= 0", name="ck_inventory_items_warning"),
        CheckConstraint("version_no >= 1", name="ck_inventory_items_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku_id: Mapped[int] = mapped_column(
        ForeignKey("product_skus.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    stock_qty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_qty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warning_threshold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    location_text: Mapped[str | None] = mapped_column(String(255))
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint("before_qty >= 0", name="ck_inventory_movements_before"),
        CheckConstraint("after_qty >= 0", name="ck_inventory_movements_after"),
        CheckConstraint("change_qty <> 0", name="ck_inventory_movements_change"),
        Index("ix_inventory_movements_sku_created", "sku_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    sku_id: Mapped[int] = mapped_column(
        ForeignKey("product_skus.id", ondelete="RESTRICT"), nullable=False
    )
    movement_type: Mapped[str] = mapped_column(String(40), nullable=False)
    change_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    before_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    after_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_text: Mapped[str | None] = mapped_column(String(500))
    reference_type: Mapped[str | None] = mapped_column(String(50))
    reference_id: Mapped[str | None] = mapped_column(String(128))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InventoryAdviceRun(Base):
    __tablename__ = "inventory_advice_runs"
    __table_args__ = (
        Index("ix_inventory_advice_runs_store_generated", "store_id", "generated_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_version: Mapped[str] = mapped_column(String(50), nullable=False)
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False)
    coverage_days: Mapped[int] = mapped_column(Integer, nullable=False)
    safety_multiplier: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    min_outbound_events: Mapped[int] = mapped_column(Integer, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    replenish_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    insufficient_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[str | None] = mapped_column(String(500))
    generated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InventoryAdviceItem(Base):
    __tablename__ = "inventory_advice_items"
    __table_args__ = (
        UniqueConstraint("run_id", "sku_id", name="uq_inventory_advice_run_sku"),
        CheckConstraint(
            "action IN ('replenish','monitor','healthy')",
            name="ck_inventory_advice_items_action",
        ),
        CheckConstraint(
            "priority IN ('critical','high','medium','low')",
            name="ck_inventory_advice_items_priority",
        ),
        CheckConstraint(
            "data_status IN ('sufficient','insufficient')",
            name="ck_inventory_advice_items_data_status",
        ),
        CheckConstraint("stock_qty >= 0", name="ck_inventory_advice_items_stock"),
        CheckConstraint("locked_qty >= 0", name="ck_inventory_advice_items_locked"),
        CheckConstraint("available_qty >= 0", name="ck_inventory_advice_items_available"),
        CheckConstraint("warning_threshold >= 0", name="ck_inventory_advice_items_warning"),
        CheckConstraint("outbound_qty >= 0", name="ck_inventory_advice_items_outbound"),
        CheckConstraint("outbound_events >= 0", name="ck_inventory_advice_items_events"),
        CheckConstraint("target_stock_qty >= 0", name="ck_inventory_advice_items_target"),
        CheckConstraint("suggested_restock_qty >= 0", name="ck_inventory_advice_items_restock"),
        Index("ix_inventory_advice_items_run_priority", "run_id", "priority"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_advice_runs.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    sku_id: Mapped[int] = mapped_column(
        ForeignKey("product_skus.id", ondelete="RESTRICT"), nullable=False
    )
    stock_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    locked_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    available_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    outbound_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    outbound_events: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_outbound_rate: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    target_stock_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    suggested_restock_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    data_status: Mapped[str] = mapped_column(String(20), nullable=False)
    explanation: Mapped[str] = mapped_column(String(1000), nullable=False)


class Competitor(TimestampMixin, Base):
    __tablename__ = "competitors"
    __table_args__ = (
        CheckConstraint("price IS NULL OR price >= 0", name="ck_competitors_price"),
        CheckConstraint("status IN ('active','inactive')", name="ck_competitors_status"),
        Index("ix_competitors_product_platform", "product_id", "platform"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048))
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sales_hint: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(500))
    main_image: Mapped[str | None] = mapped_column(String(2048))
    selling_points: Mapped[str | None] = mapped_column(Text)
    review_keywords: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    field_sources_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    last_parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CompetitorMonitor(Base):
    __tablename__ = "competitor_monitors"
    __table_args__ = (
        UniqueConstraint("competitor_id", name="uq_competitor_monitor"),
        CheckConstraint(
            "monitor_status IN ('active','paused','failed')",
            name="ck_competitor_monitors_status",
        ),
        CheckConstraint("interval_minutes >= 10", name="ck_competitor_monitors_interval"),
        Index("ix_competitor_monitors_due", "monitor_status", "next_run_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    competitor_id: Mapped[int] = mapped_column(
        ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False
    )
    monitor_status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=1440, nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lock_token: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CompetitorMonitorSnapshot(Base):
    __tablename__ = "competitor_monitor_snapshots"
    __table_args__ = (Index("ix_monitor_snapshots_monitor_created", "monitor_id", "created_at"),)

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("competitor_monitors.id", ondelete="CASCADE"), nullable=False
    )
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sales_hint: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(500))
    main_image: Mapped[str | None] = mapped_column(String(2048))
    selling_points: Mapped[str | None] = mapped_column(Text)
    review_keywords: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    changed_fields_json: Mapped[list[str] | None] = mapped_column(JSON)
    is_success: Mapped[bool] = mapped_column(default=True, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PublicLinkParseTask(TimestampMixin, Base):
    __tablename__ = "public_link_parse_tasks"
    __table_args__ = (
        CheckConstraint(
            "task_status IN ('pending','running','succeeded','failed','cancelled','timeout')",
            name="ck_public_link_parse_tasks_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_public_link_parse_tasks_attempts"),
        Index("ix_link_parse_tasks_product_status", "product_id", "task_status"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    competitor_id: Mapped[int | None] = mapped_column(
        ForeignKey("competitors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    task_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    final_url: Mapped[str | None] = mapped_column(String(2048))
    http_status: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ProductDiagnosis(TimestampMixin, Base):
    __tablename__ = "product_diagnoses"
    __table_args__ = (Index("ix_product_diagnoses_product_created", "product_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(30), default="ai", nullable=False)
    source_review_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("review_reports.id", ondelete="SET NULL"), nullable=True
    )
    positioning: Mapped[str | None] = mapped_column(Text)
    price_band: Mapped[str | None] = mapped_column(Text)
    audience_insights: Mapped[str | None] = mapped_column(Text)
    pain_points: Mapped[str | None] = mapped_column(Text)
    selling_point_analysis: Mapped[str | None] = mapped_column(Text)
    risks: Mapped[str | None] = mapped_column(Text)
    recommendations: Mapped[str | None] = mapped_column(Text)
    raw_output: Mapped[str | None] = mapped_column(Text)
    input_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    model_name: Mapped[str | None] = mapped_column(String(100))
    provider_name: Mapped[str | None] = mapped_column(String(50))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    schema_version: Mapped[str | None] = mapped_column(String(50))
    generated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    edited_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class AiUsageLog(Base):
    __tablename__ = "ai_usage_logs"
    __table_args__ = (
        CheckConstraint("status IN ('succeeded','failed')", name="ck_ai_usage_logs_status"),
        CheckConstraint("input_tokens >= 0", name="ck_ai_usage_logs_input_tokens"),
        CheckConstraint("output_tokens >= 0", name="ck_ai_usage_logs_output_tokens"),
        CheckConstraint("total_tokens >= 0", name="ck_ai_usage_logs_total_tokens"),
        CheckConstraint("latency_ms >= 0", name="ck_ai_usage_logs_latency"),
        CheckConstraint("attempts >= 1", name="ck_ai_usage_logs_attempts"),
        Index("ix_ai_usage_logs_scene_created", "scene", "created_at"),
        Index("ix_ai_usage_logs_target", "target_type", "target_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    scene: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    target_type: Mapped[str | None] = mapped_column(String(50))
    target_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CreativePlan(TimestampMixin, Base):
    __tablename__ = "creative_plans"
    __table_args__ = (
        CheckConstraint(
            "plan_type IN ('main_image','video_script','title')",
            name="ck_creative_plans_type",
        ),
        CheckConstraint(
            "status IN ('draft','selected','archived')", name="ck_creative_plans_status"
        ),
        Index("ix_creative_plans_product_type_status", "product_id", "plan_type", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    plan_type: Mapped[str] = mapped_column(String(30), nullable=False)
    generation_batch_id: Mapped[str | None] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    rationale_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    raw_output: Mapped[str | None] = mapped_column(Text)
    input_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    provider_name: Mapped[str | None] = mapped_column(String(50))
    model_name: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    schema_version: Mapped[str | None] = mapped_column(String(50))
    generated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    edited_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CreativePlanRevision(Base):
    __tablename__ = "creative_plan_revisions"
    __table_args__ = (
        UniqueConstraint(
            "creative_plan_id", "version_no", name="uq_creative_plan_revisions_version"
        ),
        Index("ix_creative_plan_revisions_plan_created", "creative_plan_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    creative_plan_id: Mapped[int] = mapped_column(
        ForeignKey("creative_plans.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    rationale_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GenerationJob(TimestampMixin, Base):
    __tablename__ = "generation_jobs"
    __table_args__ = (
        CheckConstraint("job_kind IN ('image','video')", name="ck_generation_jobs_kind"),
        CheckConstraint(
            "job_status IN ('pending','running','succeeded','failed','cancelled','timeout')",
            name="ck_generation_jobs_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_generation_jobs_attempts"),
        CheckConstraint("max_attempts >= 1", name="ck_generation_jobs_max_attempts"),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_generation_jobs_progress",
        ),
        CheckConstraint("version_no >= 1", name="ck_generation_jobs_version"),
        UniqueConstraint("idempotency_key", name="uq_generation_jobs_idempotency"),
        Index("ix_generation_jobs_claim", "job_status", "next_run_at", "locked_at"),
        Index("ix_generation_jobs_product_created", "product_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    creative_plan_id: Mapped[int] = mapped_column(
        ForeignKey("creative_plans.id", ondelete="RESTRICT"), nullable=False
    )
    creative_plan_version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    job_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    job_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(50))
    external_job_id: Mapped[str | None] = mapped_column(String(255), index=True)
    input_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    requested_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(100))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class GenerationJobEvent(Base):
    __tablename__ = "generation_job_events"
    __table_args__ = (Index("ix_job_events_job_created", "job_id", "created_at"),)

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_message: Mapped[str | None] = mapped_column(Text)
    event_data_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GeneratedAsset(TimestampMixin, Base):
    __tablename__ = "generated_assets"
    __table_args__ = (
        CheckConstraint("asset_type IN ('image','video')", name="ck_generated_assets_type"),
        CheckConstraint(
            "review_status IN ('pending','approved','rejected')",
            name="ck_generated_assets_review_status",
        ),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 5)", name="ck_assets_score"),
        CheckConstraint("file_size_bytes >= 0", name="ck_assets_file_size"),
        CheckConstraint("lock_version >= 1", name="ck_assets_lock_version"),
        CheckConstraint(
            "file_status IN ('available','missing','invalid')",
            name="ck_assets_file_status",
        ),
        UniqueConstraint(
            "creative_plan_id", "asset_type", "version_no", name="uq_asset_plan_version"
        ),
        UniqueConstraint("generation_job_id", "source_asset_index", name="uq_asset_job_index"),
        UniqueConstraint("storage_key", name="uq_assets_storage_key"),
        Index("ix_generated_assets_product_review", "product_id", "review_status"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    creative_plan_id: Mapped[int] = mapped_column(
        ForeignKey("creative_plans.id", ondelete="RESTRICT"), nullable=False
    )
    generation_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="SET NULL")
    )
    source_asset_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    asset_url: Mapped[str | None] = mapped_column(String(2048))
    mime_type: Mapped[str | None] = mapped_column(String(100))
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    file_status: Mapped[str] = mapped_column(String(20), default="available", nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(100))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_sec: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    review_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    usage_scene: Mapped[str | None] = mapped_column(String(255))
    score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    tags_json: Mapped[list[Any] | None] = mapped_column(JSON)
    remark: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PromotionLink(TimestampMixin, Base):
    __tablename__ = "promotion_links"
    __table_args__ = (
        CheckConstraint("status IN ('active','inactive')", name="ck_promotion_links_status"),
        CheckConstraint("lock_version >= 1", name="ck_promotion_links_lock_version"),
        Index("ix_promotion_links_product_status", "product_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    link_name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    tracking_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    utm_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    click_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    scene_text: Mapped[str | None] = mapped_column(String(255))
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class PromotionLinkClick(Base):
    __tablename__ = "promotion_link_clicks"
    __table_args__ = (
        Index("ix_promotion_link_clicks_link_clicked", "promotion_link_id", "clicked_at"),
        Index(
            "ix_promotion_link_clicks_dedup",
            "promotion_link_id",
            "client_ip_hash",
            "clicked_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    promotion_link_id: Mapped[int] = mapped_column(
        ForeignKey("promotion_links.id", ondelete="CASCADE"), nullable=False
    )
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    client_ip_hash: Mapped[str | None] = mapped_column(String(128))
    user_agent: Mapped[str | None] = mapped_column(String(1000))
    is_counted: Mapped[bool] = mapped_column(default=True, nullable=False)
    filter_reason: Mapped[str | None] = mapped_column(String(50))


class AdRecommendation(TimestampMixin, Base):
    __tablename__ = "ad_recommendations"
    __table_args__ = (
        CheckConstraint(
            "confirm_status IN ('pending','confirmed','rejected')",
            name="ck_ad_recommendations_confirm_status",
        ),
        Index("ix_ad_recommendations_product_created", "product_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    summary_text: Mapped[str | None] = mapped_column(Text)
    objective_text: Mapped[str | None] = mapped_column(Text)
    audience_segments_json: Mapped[list[Any] | None] = mapped_column(JSON)
    budget_plan_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    creative_tests_json: Mapped[list[Any] | None] = mapped_column(JSON)
    bid_strategy_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    risk_controls_json: Mapped[list[Any] | None] = mapped_column(JSON)
    next_steps_json: Mapped[list[Any] | None] = mapped_column(JSON)
    confirm_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirm_remark: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    schema_version: Mapped[str | None] = mapped_column(String(50))
    provider_name: Mapped[str | None] = mapped_column(String(50))
    input_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    raw_output: Mapped[str | None] = mapped_column(Text)
    generated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class AdExperiment(TimestampMixin, Base):
    __tablename__ = "ad_experiments"
    __table_args__ = (
        CheckConstraint(
            "experiment_status IN ('draft','confirmed','running','finished','cancelled')",
            name="ck_ad_experiments_status",
        ),
        CheckConstraint("budget_amount >= 0", name="ck_ad_experiments_budget"),
        Index("ix_ad_experiments_product_status", "product_id", "experiment_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    recommendation_id: Mapped[int | None] = mapped_column(
        ForeignKey("ad_recommendations.id", ondelete="SET NULL")
    )
    related_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("generated_assets.id", ondelete="SET NULL")
    )
    related_link_id: Mapped[int | None] = mapped_column(
        ForeignKey("promotion_links.id", ondelete="SET NULL")
    )
    experiment_name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_text: Mapped[str | None] = mapped_column(Text)
    audience_text: Mapped[str | None] = mapped_column(Text)
    budget_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    success_metric_text: Mapped[str | None] = mapped_column(Text)
    hypothesis_text: Mapped[str | None] = mapped_column(Text)
    experiment_status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class PerformanceRecord(Base):
    __tablename__ = "performance_records"
    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="ck_performance_records_period"),
        CheckConstraint("impressions >= 0", name="ck_performance_records_impressions"),
        CheckConstraint("clicks >= 0", name="ck_performance_records_clicks"),
        CheckConstraint("conversions >= 0", name="ck_performance_records_conversions"),
        CheckConstraint("spend >= 0", name="ck_performance_records_spend"),
        CheckConstraint("revenue >= 0", name="ck_performance_records_revenue"),
        CheckConstraint(
            "clicks <= impressions", name="ck_performance_records_clicks_lte_impressions"
        ),
        CheckConstraint(
            "conversions <= clicks", name="ck_performance_records_conversions_lte_clicks"
        ),
        CheckConstraint(
            "record_status IN ('active','voided')", name="ck_performance_records_status"
        ),
        CheckConstraint("version_no >= 1", name="ck_performance_records_version"),
        Index("ix_performance_records_product_period", "product_id", "period_start", "period_end"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    creative_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("creative_plans.id", ondelete="SET NULL")
    )
    generated_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("generated_assets.id", ondelete="SET NULL")
    )
    promotion_link_id: Mapped[int | None] = mapped_column(
        ForeignKey("promotion_links.id", ondelete="SET NULL")
    )
    experiment_id: Mapped[int | None] = mapped_column(
        ForeignKey("ad_experiments.id", ondelete="SET NULL")
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    impressions: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    clicks: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    ctr: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    conversions: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    conversion_rate: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    spend: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    roi: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    notes: Mapped[str | None] = mapped_column(Text)
    record_status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    voided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ReviewReport(Base):
    __tablename__ = "review_reports"
    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="ck_review_reports_period"),
        Index("ix_review_reports_product_period", "product_id", "period_start", "period_end"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    summary_text: Mapped[str | None] = mapped_column(Text)
    insights_json: Mapped[list[Any] | None] = mapped_column(JSON)
    problem_analysis_json: Mapped[list[Any] | None] = mapped_column(JSON)
    next_actions_json: Mapped[list[Any] | None] = mapped_column(JSON)
    input_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    model_name: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    provider_name: Mapped[str | None] = mapped_column(String(50))
    schema_version: Mapped[str | None] = mapped_column(String(50))
    raw_output: Mapped[str | None] = mapped_column(Text)
    generated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    edited_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ReviewReportRevision(Base):
    __tablename__ = "review_report_revisions"
    __table_args__ = (
        UniqueConstraint("review_report_id", "version_no", name="uq_review_report_revision"),
        Index("ix_review_report_revisions_report_created", "review_report_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    review_report_id: Mapped[int] = mapped_column(
        ForeignKey("review_reports.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    insights_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    problem_analysis_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    next_actions_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ImportBatch(TimestampMixin, Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint(
            "import_type IN ('products','sku_inventory','performance_records','platform_mappings')",
            name="ck_import_batches_type",
        ),
        CheckConstraint(
            "batch_status IN ('uploaded','validated','importing','completed','failed','cancelled')",
            name="ck_import_batches_status",
        ),
        Index("ix_import_batches_type_status", "import_type", "batch_status"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    import_type: Mapped[str] = mapped_column(String(40), nullable=False)
    batch_status: Mapped[str] = mapped_column(String(20), default="uploaded", nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(1024))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportRow(Base):
    __tablename__ = "import_rows"
    __table_args__ = (
        UniqueConstraint("batch_id", "row_number", name="uq_import_row_number"),
        CheckConstraint(
            "row_status IN ('valid','invalid','imported','failed')",
            name="ck_import_rows_status",
        ),
        Index("ix_import_rows_batch_status", "batch_id", "row_status"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    row_status: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_data_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    normalized_data_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    errors_json: Mapped[list[Any] | None] = mapped_column(JSON)
    target_type: Mapped[str | None] = mapped_column(String(50))
    target_id: Mapped[str | None] = mapped_column(String(128))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_actor_created", "actor_user_id", "created_at"),
        Index("ix_audit_logs_target", "target_type", "target_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(128))
    request_id: Mapped[str | None] = mapped_column(String(100), index=True)
    ip_hash: Mapped[str | None] = mapped_column(String(128))
    detail_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SystemSetting(TimestampMixin, Base):
    __tablename__ = "system_settings"
    __table_args__ = (
        CheckConstraint(
            "value_type IN ('string','integer','decimal','boolean','json')",
            name="ck_system_settings_value_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    setting_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    value_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    is_sensitive: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
