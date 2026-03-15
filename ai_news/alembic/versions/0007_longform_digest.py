"""add longform_html to daily_digests

Revision ID: 0007_longform_digest
Revises: 0006_entity_canon_maps
Create Date: 2026-03-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_longform_digest"
down_revision = "0006_entity_canon_maps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("daily_digests", sa.Column("longform_html", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("daily_digests", "longform_html")
