"""backfill inventory items

Revision ID: d91e6f7a24b0
Revises: c30f18a973de
Create Date: 2026-09-16 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d91e6f7a24b0"
down_revision: str | Sequence[str] | None = "c30f18a973de"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO inventory_items "
            "(sku_id, stock_qty, locked_qty, warning_threshold, version_no, updated_at) "
            "SELECT sku.id, 0, 0, 0, 1, NOW() "
            "FROM product_skus AS sku "
            "LEFT JOIN inventory_items AS inventory ON inventory.sku_id = sku.id "
            "WHERE inventory.id IS NULL"
        )
    )
    op.create_check_constraint(
        "ck_inventory_items_locked_lte_stock",
        "inventory_items",
        "locked_qty <= stock_qty",
    )
    op.create_check_constraint(
        "ck_inventory_items_version",
        "inventory_items",
        "version_no >= 1",
    )
    op.create_check_constraint(
        "ck_inventory_movements_before",
        "inventory_movements",
        "before_qty >= 0",
    )
    op.create_check_constraint(
        "ck_inventory_movements_change",
        "inventory_movements",
        "change_qty <> 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_inventory_movements_change", "inventory_movements", type_="check")
    op.drop_constraint("ck_inventory_movements_before", "inventory_movements", type_="check")
    op.drop_constraint("ck_inventory_items_version", "inventory_items", type_="check")
    op.drop_constraint("ck_inventory_items_locked_lte_stock", "inventory_items", type_="check")
    # Backfilled rows are intentionally retained to avoid deleting inventory data.
