"""add pgvector columns for server-side similarity search

Revision ID: 0009_pgvector
Revises: 0008_verification_fields
Create Date: 2026-03-20
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_pgvector"
down_revision = "0008_verification_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension (pre-installed on Supabase)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Add vector columns alongside existing bytea columns
    op.execute("ALTER TABLE clusters ADD COLUMN IF NOT EXISTS centroid_vec vector(384)")
    # NOTE: articles.embedding_vec is deferred to a future migration when
    # article-level similarity search is needed.

    # Create HNSW index for fast approximate nearest-neighbour search on clusters.
    # cosine distance operator class; ~2000 vectors expected.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_clusters_centroid_hnsw
        ON clusters USING hnsw (centroid_vec vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # NOTE: Backfill of existing bytea -> vector is handled by the
    # rebuild_index() function in app.clustering.cluster (runs on scheduler
    # startup).  Pure-SQL conversion of little-endian float32 bytea is
    # non-trivial, so we do it in Python.


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_clusters_centroid_hnsw")
    op.execute("ALTER TABLE clusters DROP COLUMN IF EXISTS centroid_vec")
    pass  # articles.embedding_vec not added in this migration
