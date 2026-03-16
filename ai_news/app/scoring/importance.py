"""Global importance score v2 -- 11-signal weighted system."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .signals import (
    authority_score,
    clamp01,
    cluster_velocity_score,
    corroboration_score,
    entity_prominence_score,
    event_impact_score,
    event_rarity_score,
    funding_score,
    improved_novelty_score,
    is_official_source,
    research_rigor_score,
    social_velocity_score,
    source_diversity_score,
)

WEIGHTS = {
    "entity_prominence": 0.15,
    "event_impact": 0.15,
    "authority": 0.12,
    "corroboration": 0.12,
    "social_velocity": 0.10,
    "cluster_velocity": 0.08,
    "novelty": 0.08,
    "event_rarity": 0.07,
    "funding": 0.05,
    "research_rigor": 0.05,
    "source_diversity": 0.03,
}

WEIGHTS_RESEARCH = {
    **WEIGHTS,
    "social_velocity": 0.06,
    "research_rigor": 0.12,
    "event_impact": 0.08,
    "entity_prominence": 0.10,
    "novelty": 0.14,
}

WEIGHTS_GITHUB = {
    **WEIGHTS,
    "social_velocity": 0.25,
    "authority": 0.05,
    "entity_prominence": 0.05,
    "event_impact": 0.05,
    "corroboration": 0.03,
    "novelty": 0.15,
}

BASE_IMPORTANCE = {
    "MODEL_RELEASE": 44.0,
    "SECURITY_INCIDENT": 32.0,   # Was 42 — routine advisories were over-scored
    "CHIP_HARDWARE": 32.0,       # Was 40 — minor driver updates were over-scored
    "BIG_TECH_ANNOUNCEMENT": 36.0,
    "GOVERNMENT_ACTION": 34.0,
    "POLICY_REGULATION": 34.0,
    "M_AND_A": 32.0,
    "STARTUP_FUNDING": 28.0,
    "PRODUCT_LAUNCH": 26.0,
    "OPEN_SOURCE_RELEASE": 26.0,
    "BENCHMARK_RESULT": 24.0,
    "RESEARCH_PAPER": 22.0,
    "OTHER": 12.0,
}

SIGNAL_BONUSES = {
    "entity_prominence": 10.0,
    "authority": 6.0,
    "corroboration": 10.0,
    "social_velocity": 12.0,
    "cluster_velocity": 6.0,
    "novelty": 8.0,
    "event_rarity": 6.0,
    "funding": 10.0,
    "research_rigor": 8.0,
    "source_diversity": 4.0,
}

CONFIRMED_EVENT_TYPES = {
    "MODEL_RELEASE", "CHIP_HARDWARE", "SECURITY_INCIDENT",
    "POLICY_REGULATION", "GOVERNMENT_ACTION",
}


@dataclass
class GlobalScoreInputs:
    source_authority: float = 0.0
    event_type: str = "OTHER"
    entities: dict[str, float] | None = None
    independent_sources: int = 0
    raw_item: object = None  # RawItem for social signals
    age_hours: float = 1.0
    articles_in_cluster: int = 1
    cluster_age_hours: float = 1.0
    novelty_sim: float = 0.0
    recent_max_score: float = 0.0
    primary_entity: str | None = None
    session: object = None  # SQLAlchemy session for event_rarity
    source_kind: str = ""
    text: str = ""
    funding_amount_usd: int | None = None
    final_url: str = ""
    source_names: list[str] = field(default_factory=list)
    content_type: str = "news"
    extraction_quality: float = 1.0


def compute_global_score_v2(inputs: GlobalScoreInputs) -> tuple[float, dict[str, float]]:
    """Compute 11-signal importance score. Returns (score_0_100, signal_breakdown)."""
    signals = {
        "entity_prominence": entity_prominence_score(inputs.entities),
        "event_impact": event_impact_score(inputs.event_type),
        "authority": authority_score(inputs.source_authority),
        "corroboration": corroboration_score(inputs.independent_sources),
        "social_velocity": social_velocity_score(inputs.raw_item, inputs.age_hours),
        "cluster_velocity": cluster_velocity_score(
            inputs.articles_in_cluster, inputs.cluster_age_hours,
        ),
        "novelty": improved_novelty_score(inputs.novelty_sim, inputs.recent_max_score),
        "event_rarity": (
            event_rarity_score(inputs.event_type, inputs.primary_entity, inputs.session)
            if inputs.session
            else 0.5
        ),
        "funding": funding_score(inputs.funding_amount_usd),
        "research_rigor": research_rigor_score(inputs.source_kind, inputs.text),
        "source_diversity": source_diversity_score(inputs.source_names),
    }

    score = BASE_IMPORTANCE.get(inputs.event_type, BASE_IMPORTANCE["OTHER"])
    score += sum(
        SIGNAL_BONUSES[name] * signals[name]
        for name in SIGNAL_BONUSES
    )

    if inputs.content_type == "research":
        score += 4.0 * signals["research_rigor"] + 4.0 * signals["novelty"]
    elif inputs.content_type == "github":
        score += 4.0 * signals["social_velocity"] + 4.0 * signals["novelty"]

    official = is_official_source(inputs.final_url)
    if official:
        score += 8.0
    if inputs.event_type == "MODEL_RELEASE" and official:
        score += 10.0
        if signals["entity_prominence"] >= 0.7:
            score += 4.0
        if signals["authority"] >= 0.9:
            score += 2.0
        score = max(score, 90.0)
    elif inputs.event_type in CONFIRMED_EVENT_TYPES and inputs.independent_sources >= 3:
        score += 5.0

    if (inputs.funding_amount_usd or 0) >= 1_000_000_000:
        score += 4.0

    signals["base_importance"] = BASE_IMPORTANCE.get(inputs.event_type, BASE_IMPORTANCE["OTHER"]) / 100.0
    score = min(100.0, round(score, 2))

    # Soft penalty for snippet-only / low-quality extractions
    eq_penalty = 1.0
    if inputs.extraction_quality <= 0.30:
        eq_penalty = 0.70 + 0.30 * (inputs.extraction_quality / 0.30)
        score = round(score * eq_penalty, 2)
    signals["extraction_quality_penalty"] = round(eq_penalty, 4)

    return score, signals
