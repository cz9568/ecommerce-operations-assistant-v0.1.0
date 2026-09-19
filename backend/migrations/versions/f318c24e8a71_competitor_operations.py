"""complete competitor operations

Revision ID: f318c24e8a71
Revises: e74ab89d13c2
Create Date: 2026-09-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f318c24e8a71"
down_revision: str | Sequence[str] | None = "e74ab89d13c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "competitors",
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
    )
    op.add_column("competitors", sa.Column("field_sources_json", sa.JSON(), nullable=True))
    op.add_column(
        "competitors", sa.Column("last_parsed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_competitors_status", "competitors", "status IN ('active','inactive')"
    )

    op.add_column(
        "public_link_parse_tasks", sa.Column("competitor_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "public_link_parse_tasks",
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
    )
    op.add_column(
        "public_link_parse_tasks", sa.Column("final_url", sa.String(length=2048), nullable=True)
    )
    op.add_column("public_link_parse_tasks", sa.Column("http_status", sa.Integer(), nullable=True))
    op.add_column(
        "public_link_parse_tasks", sa.Column("error_code", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "public_link_parse_tasks",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "public_link_parse_tasks",
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "public_link_parse_tasks",
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("public_link_parse_tasks", sa.Column("applied_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_public_link_parse_tasks_competitor_id",
        "public_link_parse_tasks",
        "competitors",
        ["competitor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_public_link_parse_tasks_applied_by",
        "public_link_parse_tasks",
        "users",
        ["applied_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_public_link_parse_tasks_competitor_id"),
        "public_link_parse_tasks",
        ["competitor_id"],
        unique=False,
    )

    op.add_column(
        "competitor_monitors", sa.Column("last_error_code", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "competitor_monitors",
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "competitor_monitors", sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "competitor_monitors",
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "competitor_monitors", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "competitor_monitors", sa.Column("lock_token", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "competitor_monitors",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.add_column(
        "competitor_monitor_snapshots", sa.Column("title", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "competitor_monitor_snapshots",
        sa.Column("main_image", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "competitor_monitor_snapshots", sa.Column("review_keywords", sa.Text(), nullable=True)
    )
    op.add_column(
        "competitor_monitor_snapshots",
        sa.Column("source_url", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "competitor_monitor_snapshots", sa.Column("changed_fields_json", sa.JSON(), nullable=True)
    )
    op.add_column(
        "competitor_monitor_snapshots",
        sa.Column("is_success", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "competitor_monitor_snapshots",
        sa.Column("error_code", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "competitor_monitor_snapshots", sa.Column("error_message", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    for column in (
        "error_message",
        "error_code",
        "is_success",
        "changed_fields_json",
        "source_url",
        "review_keywords",
        "main_image",
        "title",
    ):
        op.drop_column("competitor_monitor_snapshots", column)
    for column in (
        "updated_at",
        "lock_token",
        "locked_until",
        "last_success_at",
        "last_run_at",
        "consecutive_failures",
        "last_error_code",
    ):
        op.drop_column("competitor_monitors", column)
    op.drop_index(
        op.f("ix_public_link_parse_tasks_competitor_id"),
        table_name="public_link_parse_tasks",
    )
    op.drop_constraint(
        "fk_public_link_parse_tasks_applied_by", "public_link_parse_tasks", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_public_link_parse_tasks_competitor_id",
        "public_link_parse_tasks",
        type_="foreignkey",
    )
    for column in (
        "applied_by",
        "applied_at",
        "finished_at",
        "started_at",
        "error_code",
        "http_status",
        "final_url",
        "max_attempts",
        "competitor_id",
    ):
        op.drop_column("public_link_parse_tasks", column)
    op.drop_constraint("ck_competitors_status", "competitors", type_="check")
    op.drop_column("competitors", "last_parsed_at")
    op.drop_column("competitors", "field_sources_json")
    op.drop_column("competitors", "status")
