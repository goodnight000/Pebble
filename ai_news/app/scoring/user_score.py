from __future__ import annotations

from typing import Dict

from app.scoring.signals import is_official_source


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def compute_domain_vector(event_type: str, topics: Dict[str, float]) -> Dict[str, float]:
    return {
        "research": 1.0 if event_type in {"RESEARCH_PAPER", "BENCHMARK_RESULT"} else topics.get("research_methods", 0),
        "startups": 1.0 if event_type in {"STARTUP_FUNDING", "M_AND_A"} else topics.get("startups_funding", 0),
        "hardware": 1.0 if event_type == "CHIP_HARDWARE" else topics.get("hardware_chips", 0),
        "open_source": 1.0 if event_type == "OPEN_SOURCE_RELEASE" else topics.get("open_source", 0),
        "policy": 1.0 if event_type == "POLICY_REGULATION" else topics.get("safety_policy", 0),
        "tools": topics.get("enterprise_apps", 0),
    }


def compute_user_score(
    *,
    global_score: float,
    event_type: str,
    topics: Dict[str, float],
    entities: Dict[str, float],
    source_id: str,
    source_authority: float,
    coverage_score: float,
    social_score: float,
    final_url: str,
    user_pref,
    user_entity_weights: Dict[str, Dict],
    user_topic_weights: Dict[str, Dict],
    user_source_weights: Dict[str, Dict],
) -> float:
    domain = compute_domain_vector(event_type, topics)

    domain_mult = clamp(
        1.0
        * (user_pref.prefer_research ** domain["research"])
        * (user_pref.prefer_startups ** domain["startups"])
        * (user_pref.prefer_hardware ** domain["hardware"])
        * (user_pref.prefer_open_source ** domain["open_source"])
        * (user_pref.prefer_policy_safety ** domain["policy"])
        * (user_pref.prefer_tutorials_tools ** domain["tools"]),
        0.5,
        1.8,
    )

    # entities
    entity_mult = 1.0
    for entity, weight in sorted(entities.items(), key=lambda kv: kv[1], reverse=True)[:5]:
        config = user_entity_weights.get(entity)
        if config and config.get("blocked"):
            return 0.0
        entity_weight = config.get("weight", 1.0) if config else 1.0
        entity_mult *= clamp(entity_weight, 0.6, 1.6) ** weight

    # topics
    topic_mult = 1.0
    for topic, prob in topics.items():
        config = user_topic_weights.get(topic)
        if config and config.get("blocked") and prob >= 0.35:
            return 0.0
        topic_weight = config.get("weight", 1.0) if config else 1.0
        topic_mult *= clamp(topic_weight, 0.6, 1.6) ** prob

    # source
    source_mult = 1.0
    source_config = user_source_weights.get(source_id)
    if source_config and source_config.get("blocked"):
        return 0.0
    source_weight = source_config.get("weight", 1.0) if source_config else 1.0
    source_mult = clamp(source_weight, 0.7, 1.3)

    if user_pref.prefer_official_sources:
        source_mult *= 1.05 if is_official_source(final_url) else 0.98

    credibility_boost = clamp(
        1 + 0.10 * (user_pref.credibility_bias - 1) * (source_authority + coverage_score - 1),
        0.85,
        1.15,
    )
    hype_boost = clamp(
        1 + 0.10 * (user_pref.hype_tolerance - 1) * (social_score - source_authority),
        0.85,
        1.15,
    )

    score = global_score * domain_mult * entity_mult * topic_mult * source_mult * credibility_boost * hype_boost
    return min(100, round(score, 2))
