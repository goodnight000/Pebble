"""Evaluate clustering threshold impact on precision/recall.

Read-only script — pulls article embeddings and cluster assignments
from the last 30 days and simulates re-clustering at different thresholds.

Usage:
    python -m scripts.eval_clustering_threshold
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clustering.cluster import bytes_to_vector
from app.common.time import utcnow
from app.db import session_scope
from app.models import Article, Cluster, ClusterMember


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _simulate_clustering(embeddings: list[np.ndarray], threshold: float) -> list[list[int]]:
    """Simple greedy clustering at given threshold."""
    clusters: list[list[int]] = []
    centroids: list[np.ndarray] = []

    for i, emb in enumerate(embeddings):
        best_sim = -1.0
        best_cluster = -1
        for j, centroid in enumerate(centroids):
            sim = _cosine_sim(emb, centroid)
            if sim > best_sim:
                best_sim = sim
                best_cluster = j
        if best_sim >= threshold and best_cluster >= 0:
            clusters[best_cluster].append(i)
            # Update centroid
            members = clusters[best_cluster]
            centroids[best_cluster] = np.mean(
                [embeddings[m] for m in members], axis=0,
            )
        else:
            clusters.append([i])
            centroids.append(emb.copy())

    return clusters


def main():
    cutoff = utcnow() - timedelta(days=30)

    with session_scope() as session:
        articles = (
            session.query(Article)
            .filter(Article.created_at >= cutoff, Article.embedding.isnot(None))
            .all()
        )

        # Load actual cluster assignments
        members = (
            session.query(ClusterMember)
            .join(Article, ClusterMember.article_id == Article.id)
            .filter(Article.created_at >= cutoff)
            .all()
        )

    if not articles:
        print("No articles found in the last 30 days.")
        return

    print(f"Articles (last 30 days): {len(articles)}")

    # Build actual clusters
    actual_clusters: dict[str, list[str]] = defaultdict(list)
    article_to_cluster: dict[str, str] = {}
    for m in members:
        actual_clusters[str(m.cluster_id)].append(str(m.article_id))
        article_to_cluster[str(m.article_id)] = str(m.cluster_id)

    print(f"Actual clusters: {len(actual_clusters)}")
    actual_sizes = [len(v) for v in actual_clusters.values()]
    if actual_sizes:
        print(f"  Avg size: {sum(actual_sizes)/len(actual_sizes):.1f}")
        print(f"  Max size: {max(actual_sizes)}")
        print(f"  Singletons: {sum(1 for s in actual_sizes if s == 1)}")

    # Extract embeddings
    embeddings = []
    article_ids = []
    for art in articles:
        vec = bytes_to_vector(art.embedding)
        if vec.size > 0:
            embeddings.append(vec)
            article_ids.append(str(art.id))

    print(f"\nArticles with valid embeddings: {len(embeddings)}")

    # Simulate at different thresholds
    thresholds = [0.78, 0.80, 0.82, 0.84, 0.86]
    print(f"\n{'Threshold':>10} {'Clusters':>10} {'AvgSize':>10} {'Singletons':>12} {'FragRate':>10}")
    print("-" * 55)

    for threshold in thresholds:
        simulated = _simulate_clustering(embeddings, threshold)
        n_clusters = len(simulated)
        avg_size = sum(len(c) for c in simulated) / max(n_clusters, 1)
        singletons = sum(1 for c in simulated if len(c) == 1)
        frag_rate = singletons / max(n_clusters, 1)
        print(f"{threshold:>10.2f} {n_clusters:>10} {avg_size:>10.1f} {singletons:>12} {frag_rate:>10.2f}")


if __name__ == "__main__":
    main()
