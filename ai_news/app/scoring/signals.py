"""Individual scoring signal functions for the 11-signal importance system."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def log_norm(value: float, max_val: float) -> float:
    if value <= 0:
        return 0.0
    return clamp01(math.log1p(value) / math.log1p(max_val))


ENTITY_TIERS: dict[str, float] = {
    "OpenAI": 1.0, "Google": 1.0, "DeepMind": 1.0, "Microsoft": 0.95,
    "Meta": 0.95, "Anthropic": 0.95, "NVIDIA": 0.90, "Apple": 0.90,
    "Amazon": 0.85, "xAI": 0.85, "Mistral": 0.80, "Cohere": 0.75,
    "Stability AI": 0.75, "Hugging Face": 0.80, "AMD": 0.70, "Intel": 0.70,
    "Samsung": 0.65, "Baidu": 0.70, "Alibaba": 0.70, "Tencent": 0.65,
    "CrowdStrike": 0.80, "Palo Alto Networks": 0.80, "Cloudflare": 0.75,
    "Mandiant": 0.70, "CISA": 0.75, "MITRE": 0.70,
    "Recorded Future": 0.65, "SentinelOne": 0.65, "Fortinet": 0.65,
    "Cisco Talos": 0.65,
}


def entity_prominence_score(entities: dict[str, float] | None) -> float:
    """Highest tier score among detected entities, weighted by entity probability."""
    if not entities:
        return 0.3
    best = 0.0
    for name, weight in entities.items():
        tier = ENTITY_TIERS.get(name, 0.3)  # default 0.3 for unknown entities
        best = max(best, tier * clamp01(weight))
    return clamp01(best)


EVENT_IMPACT: dict[str, float] = {
    "MODEL_RELEASE": 1.0,
    "CHIP_HARDWARE": 0.70,         # Was 0.95 — let signals differentiate minor vs major
    "SECURITY_INCIDENT": 0.65,     # Was 0.90 — routine advisories shouldn't auto-boost
    "BIG_TECH_ANNOUNCEMENT": 0.80,
    "GOVERNMENT_ACTION": 0.80,
    "POLICY_REGULATION": 0.80,
    "STARTUP_FUNDING": 0.70,
    "M_AND_A": 0.80,
    "OPEN_SOURCE_RELEASE": 0.70,
    "BENCHMARK_RESULT": 0.65,
    "RESEARCH_PAPER": 0.60,
    "PRODUCT_LAUNCH": 0.60,
    "OTHER": 0.40,
}


def event_impact_score(event_type: str) -> float:
    return EVENT_IMPACT.get(event_type, 0.40)


def authority_score(authority: float) -> float:
    return clamp01(authority)


def corroboration_score(independent_sources: int) -> float:
    """Wilson-inspired confidence that is conservative at low source counts."""
    if independent_sources <= 0:
        return 0.0
    p = min(independent_sources / 8.0, 1.0)
    z = 1.64  # 90% confidence
    n = max(independent_sources, 1)
    lower = (p + z * z / (2 * n) - z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / (1 + z * z / n)
    return max(0.0, lower)


def social_velocity_score(raw_item: object, age_hours: float) -> float:
    """Points-per-hour across platforms, weighted combination."""
    if age_hours < 0.1:
        age_hours = 0.1
    hn_pph = (getattr(raw_item, "social_hn_points", 0) or 0) / age_hours
    reddit_pph = (getattr(raw_item, "social_reddit_upvotes", 0) or 0) / age_hours
    github_pph = (getattr(raw_item, "social_github_stars", 0) or 0) / age_hours
    # Weighted combination across platforms with diminishing returns.
    velocity = (
        0.45 * log_norm(hn_pph, 200)
        + 0.30 * log_norm(reddit_pph, 500)
        + 0.25 * log_norm(github_pph, 100)
    )
    return clamp01(velocity)


def cluster_velocity_score(articles_in_cluster: int, cluster_age_hours: float) -> float:
    """Articles per hour in cluster."""
    if cluster_age_hours < 0.1:
        cluster_age_hours = 0.1
    aph = max(articles_in_cluster - 1, 0) / cluster_age_hours
    return clamp01(log_norm(aph, 10))


def improved_novelty_score(similarity: float, recent_max_score: float = 0.0) -> float:
    """Inverse similarity weighted by recent important-article scores."""
    weighted_sim = clamp01(similarity) * clamp01(recent_max_score / 100.0)
    if weighted_sim >= 0.85:
        return 0.0
    novelty = 1.0 / (1.0 + math.exp(10 * (weighted_sim - 0.7)))
    return clamp01(novelty)


def event_rarity_score(
    event_type: str, primary_entity: str | None, session: object, days: int = 90,
) -> float:
    """Frequency-based rarity over the recent time window."""
    from datetime import datetime, timedelta, timezone

    from app.models import Article, RawItem

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    total = (
        session.query(Article)
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .filter(RawItem.fetched_at >= cutoff)
        .count()
    )
    same_type = (
        session.query(Article)
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .filter(RawItem.fetched_at >= cutoff, Article.event_type == event_type)
        .count()
    )
    if total == 0:
        return 0.5
    base_rate = max(same_type / total, 1e-6)
    surprise_bits = -math.log2(base_rate)
    max_surprise = -math.log2(1e-6)
    return min(1.0, surprise_bits / max_surprise)


def funding_score(amount: int | None) -> float:
    if not amount or amount <= 0:
        return 0.0
    return log_norm(amount, 5_000_000_000)


def research_rigor_score(source_kind: str, text: str) -> float:
    if source_kind == "arxiv":
        return 0.90
    lower = (text or "").lower()[:5000]
    if "arxiv:" in lower or "doi.org/" in lower:
        return 0.70
    if any(
        p in lower
        for p in ("we propose", "experiments", "dataset", "ablation")
    ):
        return 0.55
    return 0.35


def source_diversity_score(source_names: list[str]) -> float:
    """Ratio of unique source names to total cluster articles."""
    if not source_names:
        return 0.5
    if len(source_names) <= 1:
        return 0.5
    unique = len(set(source_names))
    return clamp01(unique / max(len(source_names), 1))


OFFICIAL_DOMAINS = {
    "openai.com", "deepmind.google", "anthropic.com", "nvidia.com",
    "microsoft.com", "meta.com", "ai.meta.com", "research.google",
    "blog.google", "apple.com", "amazon.science", "x.ai",
    "nist.gov", "cisa.gov", "crowdstrike.com", "paloaltonetworks.com", "mandiant.com",
}


def is_official_source(url: str) -> bool:
    if not url:
        return False
    host = urlparse(url).hostname or ""
    return any(host == d or host.endswith("." + d) for d in OFFICIAL_DOMAINS)
