"""Editorial rank — pure editorial importance score for clusters.

All inputs come from existing Cluster model columns. No DB access,
no side effects.
"""
from __future__ import annotations


def compute_editorial_rank(
    *,
    max_global_score: float,
    coverage_count: int,
    independent_sources_count: int,
    has_official_confirmation: bool,
    cluster_trust_score: float | None,
) -> float:
    """Compute editorial rank from cluster-level signals.

    Returns a 0-100 score reflecting editorial importance independent
    of user personalization.
    """
    base = max_global_score
    coverage_boost = min(coverage_count / 5.0, 1.0) * 5.0
    corr_boost = min(independent_sources_count / 4.0, 1.0) * 5.0
    official_boost = 3.0 if has_official_confirmation else 0.0
    trust_penalty = max(0, (40 - (cluster_trust_score or 40)) * 0.1)
    return min(100.0, max(0.0, round(
        base + coverage_boost + corr_boost + official_boost - trust_penalty, 2,
    )))
