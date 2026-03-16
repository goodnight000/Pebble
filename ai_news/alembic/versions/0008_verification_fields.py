"""add verification fields to articles and clusters

Revision ID: 0008_verification_fields
Revises: 0007_longform_digest
Create Date: 2026-03-15 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_verification_fields"
down_revision = "0007_longform_digest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("verification_mode", sa.Text(), nullable=True))
    op.add_column("articles", sa.Column("verification_state", sa.Text(), nullable=True))
    op.add_column("articles", sa.Column("freshness_state", sa.Text(), nullable=True))
    op.add_column("articles", sa.Column("verification_confidence", sa.Float(), nullable=True))
    op.add_column("articles", sa.Column("verification_signals", sa.JSON(), nullable=True))
    op.add_column("articles", sa.Column("update_status", sa.Text(), nullable=True))
    op.add_column("articles", sa.Column("canonical_evidence_url", sa.Text(), nullable=True))

    op.add_column("clusters", sa.Column("cluster_verification_state", sa.Text(), nullable=True))
    op.add_column("clusters", sa.Column("cluster_freshness_state", sa.Text(), nullable=True))
    op.add_column("clusters", sa.Column("cluster_verification_confidence", sa.Float(), nullable=True))
    op.add_column("clusters", sa.Column("cluster_verification_signals", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("clusters", "cluster_verification_signals")
    op.drop_column("clusters", "cluster_verification_confidence")
    op.drop_column("clusters", "cluster_freshness_state")
    op.drop_column("clusters", "cluster_verification_state")

    op.drop_column("articles", "canonical_evidence_url")
    op.drop_column("articles", "update_status")
    op.drop_column("articles", "verification_signals")
    op.drop_column("articles", "verification_confidence")
    op.drop_column("articles", "freshness_state")
    op.drop_column("articles", "verification_state")
    op.drop_column("articles", "verification_mode")
