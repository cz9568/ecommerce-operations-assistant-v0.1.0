"""add M9 performance lifecycle and review revisions

Revision ID: b1f7c92de340
Revises: a8d34f91c2e0
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1f7c92de340"
down_revision: str | None = "a8d34f91c2e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "performance_records",
        sa.Column("record_status", sa.String(length=20), server_default="active", nullable=False),
    )
    op.add_column(
        "performance_records",
        sa.Column("version_no", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column("performance_records", sa.Column("created_by", sa.Integer()))
    op.add_column("performance_records", sa.Column("updated_by", sa.Integer()))
    op.add_column("performance_records", sa.Column("voided_by", sa.Integer()))
    op.add_column("performance_records", sa.Column("voided_at", sa.DateTime(timezone=True)))
    op.add_column(
        "performance_records",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_performance_records_clicks_lte_impressions",
        "performance_records",
        "clicks <= impressions",
    )
    op.create_check_constraint(
        "ck_performance_records_conversions_lte_clicks",
        "performance_records",
        "conversions <= clicks",
    )
    op.create_check_constraint(
        "ck_performance_records_status",
        "performance_records",
        "record_status IN ('active','voided')",
    )
    op.create_check_constraint(
        "ck_performance_records_version", "performance_records", "version_no >= 1"
    )
    for column in ("created_by", "updated_by", "voided_by"):
        op.create_foreign_key(
            f"fk_performance_records_{column}_users",
            "performance_records",
            "users",
            [column],
            ["id"],
            ondelete="SET NULL",
        )

    op.add_column("review_reports", sa.Column("provider_name", sa.String(length=50)))
    op.add_column("review_reports", sa.Column("schema_version", sa.String(length=50)))
    op.add_column("review_reports", sa.Column("raw_output", sa.Text()))
    op.add_column("review_reports", sa.Column("generated_by", sa.Integer()))
    op.add_column("review_reports", sa.Column("edited_by", sa.Integer()))
    op.add_column("review_reports", sa.Column("edited_at", sa.DateTime(timezone=True)))
    for column in ("generated_by", "edited_by"):
        op.create_foreign_key(
            f"fk_review_reports_{column}_users",
            "review_reports",
            "users",
            [column],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "review_report_revisions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("review_report_id", sa.Integer(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("insights_json", sa.JSON(), nullable=False),
        sa.Column("problem_analysis_json", sa.JSON(), nullable=False),
        sa.Column("next_actions_json", sa.JSON(), nullable=False),
        sa.Column("changed_by", sa.Integer()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["review_report_id"], ["review_reports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_report_id", "version_no", name="uq_review_report_revision"),
    )
    op.create_index(
        "ix_review_report_revisions_report_created",
        "review_report_revisions",
        ["review_report_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_review_report_revisions_report_created",
        table_name="review_report_revisions",
    )
    op.drop_table("review_report_revisions")

    for column in ("edited_by", "generated_by"):
        op.drop_constraint(
            f"fk_review_reports_{column}_users",
            "review_reports",
            type_="foreignkey",
        )
    op.drop_column("review_reports", "edited_at")
    op.drop_column("review_reports", "edited_by")
    op.drop_column("review_reports", "generated_by")
    op.drop_column("review_reports", "raw_output")
    op.drop_column("review_reports", "schema_version")
    op.drop_column("review_reports", "provider_name")

    for column in ("voided_by", "updated_by", "created_by"):
        op.drop_constraint(
            f"fk_performance_records_{column}_users",
            "performance_records",
            type_="foreignkey",
        )
    op.drop_constraint("ck_performance_records_version", "performance_records", type_="check")
    op.drop_constraint("ck_performance_records_status", "performance_records", type_="check")
    op.drop_constraint(
        "ck_performance_records_conversions_lte_clicks",
        "performance_records",
        type_="check",
    )
    op.drop_constraint(
        "ck_performance_records_clicks_lte_impressions",
        "performance_records",
        type_="check",
    )
    op.drop_column("performance_records", "updated_at")
    op.drop_column("performance_records", "voided_at")
    op.drop_column("performance_records", "voided_by")
    op.drop_column("performance_records", "updated_by")
    op.drop_column("performance_records", "created_by")
    op.drop_column("performance_records", "version_no")
    op.drop_column("performance_records", "record_status")
