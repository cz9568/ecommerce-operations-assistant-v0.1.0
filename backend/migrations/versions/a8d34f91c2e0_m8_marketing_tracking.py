"""add M8 marketing tracking and recommendation provenance

Revision ID: a8d34f91c2e0
Revises: f69c2a8e14b7
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8d34f91c2e0"
down_revision: str | None = "f69c2a8e14b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "promotion_links",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "promotion_links",
        sa.Column("lock_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_check_constraint(
        "ck_promotion_links_lock_version", "promotion_links", "lock_version >= 1"
    )

    op.add_column(
        "promotion_link_clicks",
        sa.Column("is_counted", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column("promotion_link_clicks", sa.Column("filter_reason", sa.String(length=50)))
    op.create_index(
        "ix_promotion_link_clicks_dedup",
        "promotion_link_clicks",
        ["promotion_link_id", "client_ip_hash", "clicked_at"],
        unique=False,
    )

    op.add_column("ad_recommendations", sa.Column("schema_version", sa.String(length=50)))
    op.add_column("ad_recommendations", sa.Column("provider_name", sa.String(length=50)))
    op.add_column("ad_recommendations", sa.Column("input_snapshot_json", sa.JSON()))
    op.add_column("ad_recommendations", sa.Column("raw_output", sa.Text()))
    op.add_column("ad_recommendations", sa.Column("generated_by", sa.Integer()))
    op.create_foreign_key(
        "fk_ad_recommendations_generated_by_users",
        "ad_recommendations",
        "users",
        ["generated_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_ad_recommendations_generated_by_users",
        "ad_recommendations",
        type_="foreignkey",
    )
    op.drop_column("ad_recommendations", "generated_by")
    op.drop_column("ad_recommendations", "raw_output")
    op.drop_column("ad_recommendations", "input_snapshot_json")
    op.drop_column("ad_recommendations", "provider_name")
    op.drop_column("ad_recommendations", "schema_version")

    op.drop_index("ix_promotion_link_clicks_dedup", table_name="promotion_link_clicks")
    op.drop_column("promotion_link_clicks", "filter_reason")
    op.drop_column("promotion_link_clicks", "is_counted")

    op.drop_constraint("ck_promotion_links_lock_version", "promotion_links", type_="check")
    op.drop_column("promotion_links", "lock_version")
    op.drop_column("promotion_links", "updated_at")
