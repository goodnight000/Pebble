"""content_type categorization system

Revision ID: 0003_content_type
Revises: 0002_algorithm_v2
Create Date: 2026-03-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_content_type"
down_revision = "0002_algorithm_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Article: content_type ---
    op.add_column("articles", sa.Column("content_type", sa.Text(), nullable=False, server_default="news"))

    # --- DailyDigest: content_type + digest copy ---
    op.add_column("daily_digests", sa.Column("content_type", sa.Text(), nullable=False, server_default="all"))
    op.add_column("daily_digests", sa.Column("headline", sa.Text(), nullable=True))
    op.add_column("daily_digests", sa.Column("executive_summary", sa.Text(), nullable=True))
    op.add_column(
        "daily_digests",
        sa.Column("llm_authored", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # Backfill existing articles: research papers
    op.execute("UPDATE articles SET content_type = 'research' WHERE event_type = 'RESEARCH_PAPER'")

    # Drop old index, create new unique index including content_type
    op.drop_index("ix_daily_digests_user_date", table_name="daily_digests")
    op.create_index(
        "ix_daily_digests_user_date_ct",
        "daily_digests",
        ["user_id", "date", "content_type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_daily_digests_user_date_ct", table_name="daily_digests")
    op.create_index("ix_daily_digests_user_date", "daily_digests", ["user_id", "date"])

    op.drop_column("daily_digests", "llm_authored")
    op.drop_column("daily_digests", "executive_summary")
    op.drop_column("daily_digests", "headline")
    op.drop_column("daily_digests", "content_type")

    op.drop_column("articles", "content_type")
