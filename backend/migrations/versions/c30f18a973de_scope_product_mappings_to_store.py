"""scope product mappings to store

Revision ID: c30f18a973de
Revises: b82c44df8f14
Create Date: 2026-09-16 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c30f18a973de"
down_revision: str | Sequence[str] | None = "b82c44df8f14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_platform_product_mapping",
        "platform_product_mappings",
        type_="unique",
    )
    op.add_column(
        "platform_product_mappings",
        sa.Column("store_id", sa.Integer(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE platform_product_mappings AS mapping "
            "JOIN products AS product ON product.id = mapping.product_id "
            "SET mapping.store_id = product.store_id"
        )
    )
    op.alter_column(
        "platform_product_mappings",
        "store_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_index(
        op.f("ix_platform_product_mappings_store_id"),
        "platform_product_mappings",
        ["store_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_platform_product_mappings_store_id_stores",
        "platform_product_mappings",
        "stores",
        ["store_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.add_column(
        "platform_product_mappings",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_store_platform_product_mapping",
        "platform_product_mappings",
        ["store_id", "platform", "platform_product_id", "platform_sku_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_store_platform_product_mapping",
        "platform_product_mappings",
        type_="unique",
    )
    op.drop_column("platform_product_mappings", "updated_at")
    op.drop_constraint(
        "fk_platform_product_mappings_store_id_stores",
        "platform_product_mappings",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_platform_product_mappings_store_id"),
        table_name="platform_product_mappings",
    )
    op.drop_column("platform_product_mappings", "store_id")
    op.create_unique_constraint(
        "uq_platform_product_mapping",
        "platform_product_mappings",
        ["product_id", "platform", "platform_product_id", "platform_sku_id"],
    )
