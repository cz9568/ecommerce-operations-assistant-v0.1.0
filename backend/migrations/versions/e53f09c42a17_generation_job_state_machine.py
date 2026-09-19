"""complete generation job state machine fields

Revision ID: e53f09c42a17
Revises: c42b18d7319a
Create Date: 2026-09-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e53f09c42a17"
down_revision: str | Sequence[str] | None = "c42b18d7319a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "generation_jobs",
        sa.Column("creative_plan_version_no", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column("generation_jobs", sa.Column("requested_by", sa.Integer(), nullable=True))
    op.add_column(
        "generation_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("generation_jobs", sa.Column("error_code", sa.String(length=100), nullable=True))
    op.add_column(
        "generation_jobs",
        sa.Column("version_no", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_foreign_key(
        "fk_generation_jobs_requested_by",
        "generation_jobs",
        "users",
        ["requested_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_generation_jobs_progress",
        "generation_jobs",
        "progress_percent >= 0 AND progress_percent <= 100",
    )
    op.create_check_constraint("ck_generation_jobs_version", "generation_jobs", "version_no >= 1")


def downgrade() -> None:
    op.drop_constraint("ck_generation_jobs_version", "generation_jobs", type_="check")
    op.drop_constraint("ck_generation_jobs_progress", "generation_jobs", type_="check")
    op.drop_constraint("fk_generation_jobs_requested_by", "generation_jobs", type_="foreignkey")
    op.drop_column("generation_jobs", "version_no")
    op.drop_column("generation_jobs", "error_code")
    op.drop_column("generation_jobs", "heartbeat_at")
    op.drop_column("generation_jobs", "requested_by")
    op.drop_column("generation_jobs", "creative_plan_version_no")
