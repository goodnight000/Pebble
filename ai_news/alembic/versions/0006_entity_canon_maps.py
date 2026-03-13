"""add entity_canon_maps table

Revision ID: 0006_entity_canon_maps
Revises: 0005_digest_storage_artifacts
Create Date: 2026-03-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0006_entity_canon_maps"
down_revision = "0005_digest_storage_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_canon_maps",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("canon_map", sa.JSON(), nullable=False),
        sa.Column("cluster_count", sa.Integer(), nullable=False),
        sa.Column("entity_count", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("entity_canon_maps")
