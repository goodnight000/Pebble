"""add digest storage artifact metadata

Revision ID: 0005_digest_storage_artifacts
Revises: 0004_fix_cluster_members
Create Date: 2026-03-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0005_digest_storage_artifacts"
down_revision = "0004_fix_cluster_members"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("daily_digests", sa.Column("storage_bucket", sa.Text(), nullable=True))
    op.add_column("daily_digests", sa.Column("storage_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("daily_digests", "storage_path")
    op.drop_column("daily_digests", "storage_bucket")
