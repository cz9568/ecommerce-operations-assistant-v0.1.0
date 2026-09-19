"""add creative plan generation metadata and revisions

Revision ID: c42b18d7319a
Revises: a61d9e083b42
Create Date: 2026-09-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c42b18d7319a"
down_revision: str | Sequence[str] | None = "a61d9e083b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "creative_plans", sa.Column("generation_batch_id", sa.String(length=36), nullable=True)
    )
    op.add_column("creative_plans", sa.Column("raw_output", sa.Text(), nullable=True))
    op.add_column("creative_plans", sa.Column("input_snapshot_json", sa.JSON(), nullable=True))
    op.add_column("creative_plans", sa.Column("provider_name", sa.String(length=50), nullable=True))
    op.add_column(
        "creative_plans", sa.Column("schema_version", sa.String(length=50), nullable=True)
    )
    op.add_column("creative_plans", sa.Column("generated_by", sa.Integer(), nullable=True))
    op.add_column("creative_plans", sa.Column("edited_by", sa.Integer(), nullable=True))
    op.add_column(
        "creative_plans", sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        op.f("ix_creative_plans_generation_batch_id"),
        "creative_plans",
        ["generation_batch_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_creative_plans_generated_by",
        "creative_plans",
        "users",
        ["generated_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_creative_plans_edited_by",
        "creative_plans",
        "users",
        ["edited_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "creative_plan_revisions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("creative_plan_id", sa.Integer(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("rationale_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("changed_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["users.id"],
            name="fk_creative_plan_revisions_changed_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["creative_plan_id"],
            ["creative_plans.id"],
            name="fk_creative_plan_revisions_plan_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "creative_plan_id", "version_no", name="uq_creative_plan_revisions_version"
        ),
    )
    op.create_index(
        "ix_creative_plan_revisions_plan_created",
        "creative_plan_revisions",
        ["creative_plan_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_creative_plan_revisions_plan_created", table_name="creative_plan_revisions")
    op.drop_table("creative_plan_revisions")
    op.drop_constraint("fk_creative_plans_edited_by", "creative_plans", type_="foreignkey")
    op.drop_constraint("fk_creative_plans_generated_by", "creative_plans", type_="foreignkey")
    op.drop_index(op.f("ix_creative_plans_generation_batch_id"), table_name="creative_plans")
    op.drop_column("creative_plans", "edited_at")
    op.drop_column("creative_plans", "edited_by")
    op.drop_column("creative_plans", "generated_by")
    op.drop_column("creative_plans", "schema_version")
    op.drop_column("creative_plans", "provider_name")
    op.drop_column("creative_plans", "input_snapshot_json")
    op.drop_column("creative_plans", "raw_output")
    op.drop_column("creative_plans", "generation_batch_id")
