"""Per-event-type time decay and urgent classification."""
from __future__ import annotations

import math

EVENT_HALFLIFE_HOURS: dict[str, float] = {
    "SECURITY_INCIDENT": 6,
    "MODEL_RELEASE": 24,
    "BIG_TECH_ANNOUNCEMENT": 24,
    "OPEN_SOURCE_RELEASE": 24,
    "PRODUCT_LAUNCH": 24,
    "STARTUP_FUNDING": 36,
    "M_AND_A": 36,
    "POLICY_REGULATION": 48,
    "GOVERNMENT_ACTION": 48,
    "BENCHMARK_RESULT": 48,
    "RESEARCH_PAPER": 72,
    "OTHER": 18,
}

TRUSTED_LABELS = {"official", "confirmed", "likely"}


def rank_score(importance_score: float, event_type: str, age_hours: float, content_type: str = "news") -> float:
    """Time-decayed rank score with per-event-type half-life."""
    if content_type == "github":
        half_life = 48  # GitHub repos stay relevant longer
    else:
        half_life = EVENT_HALFLIFE_HOURS.get(event_type, 18)
    decay = 2.0 ** (-age_hours / half_life)
    return round(importance_score * decay, 2)


def compute_urgent(
    global_score: float,
    age_hours: float,
    independent_sources: int,
    is_official: bool,
    trust_label: str | None,
) -> bool:
    """Determine if article is urgent. Now requires trust_label >= 'likely'."""
    if global_score < 85:
        return False
    if age_hours > 6:
        return False
    if trust_label and trust_label not in TRUSTED_LABELS:
        return False
    if independent_sources >= 2 or is_official:
        return True
    return False
