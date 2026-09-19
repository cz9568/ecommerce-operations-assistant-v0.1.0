"""add inventory advice snapshots

Revision ID: e74ab89d13c2
Revises: d91e6f7a24b0
Create Date: 2026-09-16 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e74ab89d13c2"
down_revision: str | Sequence[str] | None = "d91e6f7a24b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_advice_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("rule_version", sa.String(length=50), nullable=False),
        sa.Column("lookback_days", sa.Integer(), nullable=False),
        sa.Column("coverage_days", sa.Integer(), nullable=False),
        sa.Column("safety_multiplier", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("min_outbound_events", sa.Integer(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("replenish_count", sa.Integer(), nullable=False),
        sa.Column("insufficient_count", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=True),
        sa.Column("generated_by", sa.Integer(), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["generated_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_inventory_advice_runs_store_id"),
        "inventory_advice_runs",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        "ix_inventory_advice_runs_store_generated",
        "inventory_advice_runs",
        ["store_id", "generated_at"],
        unique=False,
    )
    op.create_table(
        "inventory_advice_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("sku_id", sa.Integer(), nullable=False),
        sa.Column("stock_qty", sa.Integer(), nullable=False),
        sa.Column("locked_qty", sa.Integer(), nullable=False),
        sa.Column("available_qty", sa.Integer(), nullable=False),
        sa.Column("warning_threshold", sa.Integer(), nullable=False),
        sa.Column("outbound_qty", sa.Integer(), nullable=False),
        sa.Column("outbound_events", sa.Integer(), nullable=False),
        sa.Column("daily_outbound_rate", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("target_stock_qty", sa.Integer(), nullable=False),
        sa.Column("suggested_restock_qty", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("data_status", sa.String(length=20), nullable=False),
        sa.Column("explanation", sa.String(length=1000), nullable=False),
        sa.CheckConstraint(
            "action IN ('replenish','monitor','healthy')",
            name="ck_inventory_advice_items_action",
        ),
        sa.CheckConstraint("available_qty >= 0", name="ck_inventory_advice_items_available"),
        sa.CheckConstraint(
            "data_status IN ('sufficient','insufficient')",
            name="ck_inventory_advice_items_data_status",
        ),
        sa.CheckConstraint("outbound_events >= 0", name="ck_inventory_advice_items_events"),
        sa.CheckConstraint("locked_qty >= 0", name="ck_inventory_advice_items_locked"),
        sa.CheckConstraint("outbound_qty >= 0", name="ck_inventory_advice_items_outbound"),
        sa.CheckConstraint(
            "priority IN ('critical','high','medium','low')",
            name="ck_inventory_advice_items_priority",
        ),
        sa.CheckConstraint("suggested_restock_qty >= 0", name="ck_inventory_advice_items_restock"),
        sa.CheckConstraint("stock_qty >= 0", name="ck_inventory_advice_items_stock"),
        sa.CheckConstraint("target_stock_qty >= 0", name="ck_inventory_advice_items_target"),
        sa.CheckConstraint("warning_threshold >= 0", name="ck_inventory_advice_items_warning"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["inventory_advice_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sku_id"], ["product_skus.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "sku_id", name="uq_inventory_advice_run_sku"),
    )
    op.create_index(
        "ix_inventory_advice_items_run_priority",
        "inventory_advice_items",
        ["run_id", "priority"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_inventory_advice_items_run_priority", table_name="inventory_advice_items")
    op.drop_table("inventory_advice_items")
    op.drop_index("ix_inventory_advice_runs_store_generated", table_name="inventory_advice_runs")
    op.drop_index(op.f("ix_inventory_advice_runs_store_id"), table_name="inventory_advice_runs")
    op.drop_table("inventory_advice_runs")
