"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-01-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("feed_url", sa.Text(), nullable=True),
        sa.Column("authority", sa.Float(), nullable=False),
        sa.Column("always_scrape", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("priority_poll", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("rate_limit_rps", sa.Float(), nullable=False, server_default=sa.text("0.5")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("name", name="uq_sources_name"),
    )

    op.create_table(
        "raw_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("language", sa.Text(), nullable=False, server_default=sa.text("'en'")),
        sa.Column("social_hn_points", sa.Integer(), nullable=True),
        sa.Column("social_hn_comments", sa.Integer(), nullable=True),
        sa.Column("social_reddit_upvotes", sa.Integer(), nullable=True),
        sa.Column("social_github_stars", sa.Integer(), nullable=True),
        sa.Column("pre_score", sa.Float(), nullable=True),
        sa.Column("scrape_decision", sa.Text(), nullable=True),
        sa.Column("scrape_reason", sa.Text(), nullable=True),
        sa.Column("canonical_hash", sa.Text(), nullable=False),
        sa.UniqueConstraint("source_id", "external_id", name="uq_raw_items_source_external"),
        sa.UniqueConstraint("canonical_hash", name="uq_raw_items_canonical"),
    )
    op.create_index("ix_raw_items_fetched_at", "raw_items", ["fetched_at"])

    op.create_table(
        "articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("raw_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("raw_items.id"), unique=True),
        sa.Column("final_url", sa.Text(), nullable=False),
        sa.Column("html", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("extraction_quality", sa.Float(), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("topics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("entities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("funding_amount_usd", sa.BigInteger(), nullable=True),
        sa.Column("global_score", sa.Float(), nullable=False),
        sa.Column("urgent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("extraction_quality >= 0 and extraction_quality <= 1", name="ck_articles_quality"),
    )

    op.create_table(
        "clusters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("centroid_embedding", sa.LargeBinary(), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("top_article_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("articles.id"), nullable=True),
        sa.Column("coverage_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sources_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_global_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "cluster_members",
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clusters.id"), primary_key=True),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("articles.id"), unique=True),
        sa.Column("similarity", sa.Float(), nullable=False),
    )
    op.create_index("ix_cluster_members_cluster", "cluster_members", ["cluster_id"])

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "user_prefs",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("min_show_score", sa.Float(), nullable=False, server_default=sa.text("55")),
        sa.Column("min_urgent_score", sa.Float(), nullable=False, server_default=sa.text("85")),
        sa.Column("serendipity", sa.Float(), nullable=False, server_default=sa.text("0.15")),
        sa.Column("prefer_official_sources", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("prefer_research", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("prefer_startups", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("prefer_hardware", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("prefer_open_source", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("prefer_policy_safety", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("prefer_tutorials_tools", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("recency_bias", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("credibility_bias", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("hype_tolerance", sa.Float(), nullable=False, server_default=sa.text("1.0")),
    )

    op.create_table(
        "user_entity_weights",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("entity", sa.Text(), primary_key=True),
        sa.Column("weight", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_table(
        "user_topic_weights",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("topic", sa.Text(), primary_key=True),
        sa.Column("weight", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_table(
        "user_source_weights",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id"), primary_key=True),
        sa.Column("weight", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_table(
        "daily_digests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("article_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("ix_daily_digests_user_date", "daily_digests", ["user_id", "date"])


def downgrade() -> None:
    op.drop_index("ix_daily_digests_user_date", table_name="daily_digests")
    op.drop_table("daily_digests")
    op.drop_table("user_source_weights")
    op.drop_table("user_topic_weights")
    op.drop_table("user_entity_weights")
    op.drop_table("user_prefs")
    op.drop_table("users")
    op.drop_index("ix_cluster_members_cluster", table_name="cluster_members")
    op.drop_table("cluster_members")
    op.drop_table("clusters")
    op.drop_table("articles")
    op.drop_index("ix_raw_items_fetched_at", table_name="raw_items")
    op.drop_table("raw_items")
    op.drop_table("sources")
