from __future__ import annotations

from datetime import datetime, timedelta
from typing import Tuple

import numpy as np
from sqlalchemy import func, select

from app.clustering.faiss_index import FaissClusterIndex
from app.common.time import utcnow
from app.db import session_scope
from app.models import Article, Cluster, ClusterMember, RawItem, Source


INDEX = FaissClusterIndex(dim=384)
LAST_BUILT_AT: datetime | None = None


def bytes_to_vector(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32)


def vector_to_bytes(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()


def rebuild_index(session, lookback_days: int = 7) -> None:
    global LAST_BUILT_AT
    cutoff = utcnow() - timedelta(days=lookback_days)
    clusters = (
        session.query(Cluster)
        .filter(Cluster.last_seen_at >= cutoff)
        .all()
    )
    embeddings = []
    ids = []
    for cluster in clusters:
        if cluster.centroid_embedding is None:
            continue
        vec = bytes_to_vector(cluster.centroid_embedding)
        if vec.size == 0:
            continue
        embeddings.append(vec)
        ids.append(str(cluster.id))
    if embeddings:
        emb_matrix = np.vstack(embeddings)
    else:
        emb_matrix = np.zeros((0, 384), dtype=np.float32)
    INDEX.rebuild(emb_matrix, ids)
    LAST_BUILT_AT = utcnow()


def ensure_index(session, lookback_days: int = 7) -> None:
    if INDEX is None or LAST_BUILT_AT is None:
        rebuild_index(session, lookback_days=lookback_days)


def update_cluster_stats(session, cluster_id) -> None:
    # coverage_count
    coverage_count = session.query(ClusterMember).filter(ClusterMember.cluster_id == cluster_id).count()

    # sources_count
    sources_count = (
        session.query(Source.id)
        .join(RawItem, RawItem.source_id == Source.id)
        .join(Article, Article.raw_item_id == RawItem.id)
        .join(ClusterMember, ClusterMember.article_id == Article.id)
        .filter(ClusterMember.cluster_id == cluster_id)
        .distinct()
        .count()
    )

    # max_global_score and headline
    row = (
        session.query(Article, RawItem, Source)
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .join(Source, RawItem.source_id == Source.id)
        .join(ClusterMember, ClusterMember.article_id == Article.id)
        .filter(ClusterMember.cluster_id == cluster_id)
        .order_by(Article.global_score.desc(), Source.authority.desc())
        .first()
    )
    if row:
        article_row, raw_row, _source_row = row
        headline = raw_row.title
        max_global_score = article_row.global_score
        top_article_id = article_row.id
    else:
        headline = ""
        max_global_score = 0
        top_article_id = None

    # first/last seen
    times = (
        session.query(func.min(RawItem.published_at), func.max(func.coalesce(RawItem.published_at, RawItem.fetched_at)))
        .join(Article, Article.raw_item_id == RawItem.id)
        .join(ClusterMember, ClusterMember.article_id == Article.id)
        .filter(ClusterMember.cluster_id == cluster_id)
        .first()
    )
    first_seen, last_seen = times if times else (None, None)

    session.query(Cluster).filter(Cluster.id == cluster_id).update(
        {
            "coverage_count": coverage_count,
            "sources_count": sources_count,
            "headline": headline,
            "max_global_score": max_global_score,
            "top_article_id": top_article_id,
            "first_seen_at": first_seen,
            "last_seen_at": last_seen,
        }
    )


def attach_or_create_cluster(
    session,
    article: Article,
    embedding: np.ndarray,
    similarity_threshold: float = 0.86,
    lookback_days: int = 7,
) -> Tuple[str, float]:
    ensure_index(session, lookback_days=lookback_days)
    cluster_id, similarity = INDEX.search(embedding, k=5)

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
    session.add(ClusterMember(cluster_id=new_cluster.id, article_id=article.id, similarity=1.0))
    session.flush()
    update_cluster_stats(session, new_cluster.id)
    return str(new_cluster.id), 1.0
