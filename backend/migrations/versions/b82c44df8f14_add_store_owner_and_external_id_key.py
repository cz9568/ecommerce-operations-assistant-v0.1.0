"""add store owner and external id key

Revision ID: b82c44df8f14
Revises: 7ebf4f3fc50e
Create Date: 2026-09-16 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b82c44df8f14"
down_revision: str | Sequence[str] | None = "7ebf4f3fc50e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("stores", sa.Column("owner_user_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_stores_owner_user_id"), "stores", ["owner_user_id"], unique=False)
    op.create_foreign_key(
        "fk_stores_owner_user_id_users",
        "stores",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_store_platform_external_id",
        "stores",
        ["platform", "external_store_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_store_platform_external_id", "stores", type_="unique")
    op.drop_constraint("fk_stores_owner_user_id_users", "stores", type_="foreignkey")
    op.drop_index(op.f("ix_stores_owner_user_id"), table_name="stores")
    op.drop_column("stores", "owner_user_id")
