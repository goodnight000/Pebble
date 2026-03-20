from __future__ import annotations

from datetime import datetime, timedelta
from typing import Tuple

import numpy as np
from sqlalchemy import func, select, text

from app.common.time import utcnow
from app.db import session_scope
from app.models import Article, Cluster, ClusterMember, RawItem, Source


LAST_BUILT_AT: datetime | None = None
LAST_CLUSTER_COUNT: int = 0


def bytes_to_vector(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32)


def vector_to_bytes(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()


def _vector_to_pgvector_literal(vec: np.ndarray) -> str:
    """Convert numpy array to pgvector literal string '[0.1,0.2,...]'."""
    return '[' + ','.join(f'{float(v):.8f}' for v in vec) + ']'


def _set_centroid_vec(session, cluster_id, vec: np.ndarray) -> None:
    """Write centroid_vec via raw SQL (avoids pgvector Python dependency)."""
    session.execute(
        text("UPDATE clusters SET centroid_vec = :vec::vector WHERE id = :cid"),
        {"vec": _vector_to_pgvector_literal(vec), "cid": str(cluster_id)},
    )


def rebuild_index(session, lookback_days: int = 7) -> None:
    """Backfill centroid_vec from centroid_embedding for clusters missing the vector column."""
    global LAST_BUILT_AT, LAST_CLUSTER_COUNT

    cutoff = utcnow() - timedelta(days=lookback_days)

    # Check if centroid_vec column exists (graceful fallback for envs without pgvector)
    try:
        session.execute(text("SELECT centroid_vec FROM clusters LIMIT 0"))
    except Exception:
        session.rollback()
        LAST_BUILT_AT = utcnow()
        return

    # Find clusters with bytea but no vector
    rows = session.execute(
        text("""
            SELECT id, centroid_embedding
            FROM clusters
            WHERE last_seen_at >= :cutoff
              AND centroid_embedding IS NOT NULL
              AND centroid_vec IS NULL
        """),
        {"cutoff": cutoff},
    ).fetchall()

    for row in rows:
        cluster_id = row[0]
        centroid_embedding = row[1]
        vec = bytes_to_vector(centroid_embedding)
        if vec.size == 0:
            continue
        _set_centroid_vec(session, cluster_id, vec)

    if rows:
        session.flush()

    # Update count of indexable clusters for the skip guard
    count_row = session.execute(
        text("""
            SELECT COUNT(*) FROM clusters
            WHERE last_seen_at >= :cutoff AND centroid_embedding IS NOT NULL
        """),
        {"cutoff": cutoff},
    ).scalar()
    LAST_CLUSTER_COUNT = count_row or 0
    LAST_BUILT_AT = utcnow()


def update_cluster_stats(session, cluster_id) -> None:
    # Use a savepoint so a timeout/lock failure here doesn't roll back the
    # entire outer transaction (e.g. the article insert that called us).
    nested = session.begin_nested()
    try:
        _update_cluster_stats_inner(session, cluster_id)
        nested.commit()
    except Exception as exc:
        nested.rollback()
        print(f"[clustering] update_cluster_stats failed for {cluster_id}: {exc}")


_CLUSTER_STATS_SQL = text("""
    WITH stats AS (
        SELECT
            COUNT(*)                                          AS coverage_count,
            COUNT(DISTINCT s.id)                              AS sources_count,
            MIN(r.published_at)                               AS first_seen,
            MAX(COALESCE(r.published_at, r.fetched_at))       AS last_seen
        FROM cluster_members cm
        JOIN articles  a ON cm.article_id  = a.id
        JOIN raw_items r ON a.raw_item_id  = r.id
        JOIN sources   s ON r.source_id    = s.id
        WHERE cm.cluster_id = :cid
    ),
    top AS (
        SELECT a.id AS article_id, a.global_score, r.title
        FROM cluster_members cm
        JOIN articles  a ON cm.article_id  = a.id
        JOIN raw_items r ON a.raw_item_id  = r.id
        JOIN sources   s ON r.source_id    = s.id
        WHERE cm.cluster_id = :cid
        ORDER BY a.global_score DESC NULLS LAST,
                 s.authority    DESC NULLS LAST
        LIMIT 1
    )
    SELECT s.coverage_count, s.sources_count,
           s.first_seen,     s.last_seen,
           t.article_id,     t.global_score, t.title
    FROM stats s, top t
""")


def _update_cluster_stats_inner(session, cluster_id) -> None:
    row = session.execute(_CLUSTER_STATS_SQL, {"cid": str(cluster_id)}).first()

    if not row:
        # Cluster has 0 members — nothing to update.
        return

    session.query(Cluster).filter(Cluster.id == cluster_id).update(
        {
            "coverage_count": row.coverage_count,
            "sources_count": row.sources_count,
            "headline": row.title or "",
            "max_global_score": row.global_score or 0,
            "top_article_id": row.article_id,
            "first_seen_at": row.first_seen,
            "last_seen_at": row.last_seen,
        }
    )


_PGVECTOR_AVAILABLE: bool | None = None


def _pgvector_available(session) -> bool:
    """Return True if the centroid_vec column exists on clusters.

    The result is cached at module level so the probe query only runs once,
    avoiding transaction-aborting errors inside live sessions.
    """
    global _PGVECTOR_AVAILABLE
    if _PGVECTOR_AVAILABLE is not None:
        return _PGVECTOR_AVAILABLE
    try:
        session.execute(text("SELECT centroid_vec FROM clusters LIMIT 0"))
        _PGVECTOR_AVAILABLE = True
    except Exception:
        session.rollback()
        _PGVECTOR_AVAILABLE = False
    return _PGVECTOR_AVAILABLE


def attach_or_create_cluster(
    session,
    article: Article,
    embedding: np.ndarray,
    similarity_threshold: float = 0.86,
    lookback_days: int = 7,
) -> Tuple[str, float]:
    cutoff = utcnow() - timedelta(days=lookback_days)
    vec_literal = _vector_to_pgvector_literal(embedding)

    cluster_id = None
    similarity = 0.0

    # Try pgvector server-side search first
    use_pgvector = _pgvector_available(session)

    if use_pgvector:
        row = session.execute(
            text("""
                SELECT id, 1 - (centroid_vec <=> :vec::vector) AS similarity
                FROM clusters
                WHERE last_seen_at >= :cutoff
                  AND centroid_vec IS NOT NULL
                ORDER BY centroid_vec <=> :vec::vector
                LIMIT 1
            """),
            {"vec": vec_literal, "cutoff": cutoff},
        ).first()

        if row and row.similarity >= similarity_threshold:
            cluster_id = str(row.id)
            similarity = float(row.similarity)
    else:
        # Fallback: in-memory numpy search (no FAISS dependency needed)
        rows = (
            session.query(Cluster.id, Cluster.centroid_embedding)
            .filter(Cluster.last_seen_at >= cutoff, Cluster.centroid_embedding.isnot(None))
            .all()
        )
        best_id = None
        best_sim = 0.0
        emb_norm = np.linalg.norm(embedding)
        if emb_norm > 0:
            emb_normed = embedding / emb_norm
        else:
            emb_normed = embedding
        for cid, centroid_bytes in rows:
            if not centroid_bytes:
                continue
            vec = bytes_to_vector(centroid_bytes)
            if vec.size == 0:
                continue
            sim = float(vec @ emb_normed)
            if sim > best_sim:
                best_sim = sim
                best_id = str(cid)
        if best_id and best_sim >= similarity_threshold:
            cluster_id = best_id
            similarity = best_sim

    if cluster_id and similarity >= similarity_threshold:
        existing_member = (
            session.query(ClusterMember)
            .filter(
                ClusterMember.cluster_id == cluster_id,
                ClusterMember.article_id == article.id,
            )
            .first()
        )
        if existing_member:
            update_cluster_stats(session, cluster_id)
            return cluster_id, existing_member.similarity

        session.add(ClusterMember(cluster_id=cluster_id, article_id=article.id, similarity=similarity))
        session.flush()
        cluster = session.query(Cluster).filter(Cluster.id == cluster_id).first()
        if cluster and cluster.coverage_count:
            # update centroid with running mean
            old_vec = bytes_to_vector(cluster.centroid_embedding)
            n = max(1, cluster.coverage_count)
            new_vec = (old_vec * n + embedding) / (n + 1)
            new_vec = new_vec / np.linalg.norm(new_vec)
            cluster.centroid_embedding = vector_to_bytes(new_vec)
            # Also update pgvector column
            if use_pgvector:
                _set_centroid_vec(session, cluster_id, new_vec)
        update_cluster_stats(session, cluster_id)
        return cluster_id, similarity

    # create new cluster
    new_cluster = Cluster(
        centroid_embedding=vector_to_bytes(embedding),
        headline=article.raw_item.title if article.raw_item else "",
        top_article_id=article.id,
        coverage_count=1,
        sources_count=1,
        max_global_score=article.global_score,
        first_seen_at=article.raw_item.published_at if article.raw_item else None,
        last_seen_at=(article.raw_item.published_at or article.raw_item.fetched_at) if article.raw_item else None,
    )
    session.add(new_cluster)
    session.flush()
    # Set pgvector column for the new cluster
    if use_pgvector:
        _set_centroid_vec(session, new_cluster.id, embedding)
    session.add(ClusterMember(cluster_id=new_cluster.id, article_id=article.id, similarity=1.0))
    session.flush()
    update_cluster_stats(session, new_cluster.id)
    return str(new_cluster.id), 1.0
