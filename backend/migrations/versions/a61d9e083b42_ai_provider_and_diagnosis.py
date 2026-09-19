"""add AI provider metadata and diagnosis audit fields

Revision ID: a61d9e083b42
Revises: f318c24e8a71
Create Date: 2026-09-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a61d9e083b42"
down_revision: str | Sequence[str] | None = "f318c24e8a71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product_diagnoses", sa.Column("provider_name", sa.String(length=50), nullable=True)
    )
    op.add_column(
        "product_diagnoses", sa.Column("schema_version", sa.String(length=50), nullable=True)
    )
    op.add_column("product_diagnoses", sa.Column("generated_by", sa.Integer(), nullable=True))
    op.add_column("product_diagnoses", sa.Column("edited_by", sa.Integer(), nullable=True))
    op.add_column(
        "product_diagnoses", sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_product_diagnoses_generated_by",
        "product_diagnoses",
        "users",
        ["generated_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_product_diagnoses_edited_by",
        "product_diagnoses",
        "users",
        ["edited_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "ai_usage_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("scene", sa.String(length=50), nullable=False),
        sa.Column("provider_name", sa.String(length=50), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="1", nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("target_type", sa.String(length=50), nullable=True),
        sa.Column("target_id", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("attempts >= 1", name="ck_ai_usage_logs_attempts"),
        sa.CheckConstraint("input_tokens >= 0", name="ck_ai_usage_logs_input_tokens"),
        sa.CheckConstraint("latency_ms >= 0", name="ck_ai_usage_logs_latency"),
        sa.CheckConstraint("output_tokens >= 0", name="ck_ai_usage_logs_output_tokens"),
        sa.CheckConstraint("status IN ('succeeded','failed')", name="ck_ai_usage_logs_status"),
        sa.CheckConstraint("total_tokens >= 0", name="ck_ai_usage_logs_total_tokens"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_usage_logs_scene_created",
        "ai_usage_logs",
        ["scene", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_usage_logs_target",
        "ai_usage_logs",
        ["target_type", "target_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_usage_logs_request_id"),
        "ai_usage_logs",
        ["request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_usage_logs_request_id"), table_name="ai_usage_logs")
    op.drop_index("ix_ai_usage_logs_target", table_name="ai_usage_logs")
    op.drop_index("ix_ai_usage_logs_scene_created", table_name="ai_usage_logs")
    op.drop_table("ai_usage_logs")
    op.drop_constraint("fk_product_diagnoses_edited_by", "product_diagnoses", type_="foreignkey")
    op.drop_constraint("fk_product_diagnoses_generated_by", "product_diagnoses", type_="foreignkey")
    op.drop_column("product_diagnoses", "edited_at")
    op.drop_column("product_diagnoses", "edited_by")
    op.drop_column("product_diagnoses", "generated_by")
    op.drop_column("product_diagnoses", "schema_version")
    op.drop_column("product_diagnoses", "provider_name")
