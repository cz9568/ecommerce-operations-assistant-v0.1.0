"""complete asset storage and review fields

Revision ID: f69c2a8e14b7
Revises: e53f09c42a17
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f69c2a8e14b7"
down_revision: str | None = "e53f09c42a17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    column_names = {column["name"] for column in inspector.get_columns("generated_assets")}
    columns = (
        sa.Column("source_asset_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("mime_type", sa.String(length=100)),
        sa.Column("file_size_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64)),
        sa.Column("file_status", sa.String(length=20), server_default="available", nullable=False),
        sa.Column("lock_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
    )
    for column in columns:
        if column.name not in column_names:
            op.add_column("generated_assets", column)

    op.alter_column(
        "generated_assets",
        "storage_key",
        existing_type=sa.String(length=1024),
        type_=sa.String(length=512),
        existing_nullable=False,
    )

    inspector = sa.inspect(bind)
    check_names = {
        constraint["name"] for constraint in inspector.get_check_constraints("generated_assets")
    }
    checks = {
        "ck_assets_file_size": "file_size_bytes >= 0",
        "ck_assets_lock_version": "lock_version >= 1",
        "ck_assets_file_status": "file_status IN ('available','missing','invalid')",
    }
    for name, expression in checks.items():
        if name not in check_names:
            op.create_check_constraint(name, "generated_assets", expression)

    inspector = sa.inspect(bind)
    unique_names = {
        constraint["name"] for constraint in inspector.get_unique_constraints("generated_assets")
    }
    if "uq_asset_job_index" not in unique_names:
        op.create_unique_constraint(
            "uq_asset_job_index",
            "generated_assets",
            ["generation_job_id", "source_asset_index"],
        )
    if "uq_assets_storage_key" not in unique_names:
        op.create_unique_constraint("uq_assets_storage_key", "generated_assets", ["storage_key"])


def downgrade() -> None:
    op.drop_constraint("uq_assets_storage_key", "generated_assets", type_="unique")
    op.drop_constraint("uq_asset_job_index", "generated_assets", type_="unique")
    op.drop_constraint("ck_assets_file_status", "generated_assets", type_="check")
    op.drop_constraint("ck_assets_lock_version", "generated_assets", type_="check")
    op.drop_constraint("ck_assets_file_size", "generated_assets", type_="check")
    op.alter_column(
        "generated_assets",
        "storage_key",
        existing_type=sa.String(length=512),
        type_=sa.String(length=1024),
        existing_nullable=False,
    )
    op.drop_column("generated_assets", "synced_at")
    op.drop_column("generated_assets", "lock_version")
    op.drop_column("generated_assets", "file_status")
    op.drop_column("generated_assets", "checksum_sha256")
    op.drop_column("generated_assets", "file_size_bytes")
    op.drop_column("generated_assets", "mime_type")
    op.drop_column("generated_assets", "source_asset_index")
