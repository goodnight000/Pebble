"""algorithm v2 - importance scoring, trust scoring, cluster signals

Revision ID: 0002_algorithm_v2
Revises: 0001_initial
Create Date: 2026-03-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_algorithm_v2"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Article: importance scoring signals ---
    op.add_column("articles", sa.Column("entity_prominence", sa.Float(), nullable=True))
    op.add_column("articles", sa.Column("social_velocity", sa.Float(), nullable=True))
    op.add_column("articles", sa.Column("cluster_velocity", sa.Float(), nullable=True))
    op.add_column("articles", sa.Column("event_rarity", sa.Float(), nullable=True))
    op.add_column("articles", sa.Column("independent_sources", sa.Integer(), nullable=True))
    op.add_column("articles", sa.Column("llm_score", sa.Float(), nullable=True))
    op.add_column("articles", sa.Column("llm_reasoning", sa.Text(), nullable=True))
    op.add_column("articles", sa.Column("final_score", sa.Float(), nullable=True))

    # --- Article: trust scoring ---
    op.add_column("articles", sa.Column("trust_score", sa.Float(), nullable=True))
    op.add_column("articles", sa.Column("trust_label", sa.Text(), nullable=True))
    op.add_column("articles", sa.Column("trust_components", sa.JSON(), nullable=True))
    op.add_column("articles", sa.Column("hedging_ratio", sa.Float(), nullable=True))
    op.add_column("articles", sa.Column("attribution_ratio", sa.Float(), nullable=True))
    op.add_column("articles", sa.Column("specificity_score", sa.Float(), nullable=True))
    op.add_column(
        "articles",
        sa.Column("has_primary_document", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("articles", sa.Column("confirmation_level", sa.Text(), nullable=True))

    # --- Cluster: cluster-level scoring ---
    op.add_column("clusters", sa.Column("cluster_velocity", sa.Float(), nullable=True))
    op.add_column("clusters", sa.Column("independent_sources_count", sa.Integer(), nullable=True))
    op.add_column(
        "clusters",
        sa.Column("has_official_confirmation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("clusters", sa.Column("cluster_trust_score", sa.Float(), nullable=True))
    op.add_column("clusters", sa.Column("cluster_trust_label", sa.Text(), nullable=True))


def downgrade() -> None:
    # --- Cluster ---
    op.drop_column("clusters", "cluster_trust_label")
    op.drop_column("clusters", "cluster_trust_score")
    op.drop_column("clusters", "has_official_confirmation")
    op.drop_column("clusters", "independent_sources_count")
    op.drop_column("clusters", "cluster_velocity")

    # --- Article: trust scoring ---
    op.drop_column("articles", "confirmation_level")
    op.drop_column("articles", "has_primary_document")
    op.drop_column("articles", "specificity_score")
    op.drop_column("articles", "attribution_ratio")
    op.drop_column("articles", "hedging_ratio")
    op.drop_column("articles", "trust_components")
    op.drop_column("articles", "trust_label")
    op.drop_column("articles", "trust_score")

    # --- Article: importance scoring signals ---
    op.drop_column("articles", "final_score")
    op.drop_column("articles", "llm_reasoning")
    op.drop_column("articles", "llm_score")
    op.drop_column("articles", "independent_sources")
    op.drop_column("articles", "event_rarity")
    op.drop_column("articles", "cluster_velocity")
    op.drop_column("articles", "social_velocity")
    op.drop_column("articles", "entity_prominence")
