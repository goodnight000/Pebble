"""fix cluster_members primary key layout

Revision ID: 0004_fix_cluster_members
Revises: 0003_content_type
Create Date: 2026-03-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0004_fix_cluster_members"
down_revision = "0003_content_type"
branch_labels = None
depends_on = None


def _id_type(dialect_name: str):
    if dialect_name == "postgresql":
        return postgresql.UUID(as_uuid=True)
    return sa.String(length=36)


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    id_type = _id_type(dialect_name)

    op.create_table(
        "cluster_members_new",
        sa.Column("cluster_id", id_type, sa.ForeignKey("clusters.id"), nullable=False),
        sa.Column("article_id", id_type, sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("cluster_id", "article_id", name="pk_cluster_members"),
        sa.UniqueConstraint("article_id", name="uq_cluster_members_article_id"),
    )

    if dialect_name == "sqlite":
        op.execute(
            """
            INSERT OR IGNORE INTO cluster_members_new (cluster_id, article_id, similarity)
            SELECT cluster_id, article_id, similarity
            FROM cluster_members
            """
        )
    else:
        op.execute(
            """
            INSERT INTO cluster_members_new (cluster_id, article_id, similarity)
            SELECT cluster_id, article_id, similarity
            FROM cluster_members
            ON CONFLICT (article_id) DO NOTHING
            """
        )

    op.drop_index("ix_cluster_members_cluster", table_name="cluster_members")
    op.drop_table("cluster_members")
    op.rename_table("cluster_members_new", "cluster_members")
    op.create_index("ix_cluster_members_cluster", "cluster_members", ["cluster_id"])


def downgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    id_type = _id_type(dialect_name)

    op.create_table(
        "cluster_members_old",
        sa.Column("cluster_id", id_type, sa.ForeignKey("clusters.id"), primary_key=True, nullable=False),
        sa.Column("article_id", id_type, sa.ForeignKey("articles.id"), nullable=True, unique=True),
        sa.Column("similarity", sa.Float(), nullable=False),
    )

    if dialect_name == "sqlite":
        op.execute(
            """
            INSERT OR IGNORE INTO cluster_members_old (cluster_id, article_id, similarity)
            SELECT cluster_id, article_id, similarity
            FROM cluster_members
            ORDER BY cluster_id, article_id
            """
        )
    else:
        op.execute(
            """
            INSERT INTO cluster_members_old (cluster_id, article_id, similarity)
            SELECT cluster_id, article_id, similarity
            FROM cluster_members
            ON CONFLICT (cluster_id) DO NOTHING
            """
        )

    op.drop_index("ix_cluster_members_cluster", table_name="cluster_members")
    op.drop_table("cluster_members")
    op.rename_table("cluster_members_old", "cluster_members")
    op.create_index("ix_cluster_members_cluster", "cluster_members", ["cluster_id"])
