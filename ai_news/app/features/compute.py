from __future__ import annotations

from copy import deepcopy

from app.features.entities import extract_entities
from app.features.event_type_rules import classify_event_type
from app.features.funding import parse_funding_amount
from app.features.official_releases import assess_official_model_release
from app.features.topic_anchors import topic_probabilities
from app.models import EventType


def _normalize_topic_weights(topics: dict[str, float]) -> dict[str, float]:
    total = sum(max(value, 0.0) for value in topics.values())
    if total <= 0:
        return topics
    return {topic: float(max(value, 0.0) / total) for topic, value in topics.items()}


def _boost_model_release_topics(topics: dict[str, float]) -> dict[str, float]:
    boosted = deepcopy(topics)
    remainder = 0.28
    boosted["llms"] = max(boosted.get("llms", 0.0), 0.72)
    other_topics = [topic for topic in boosted.keys() if topic != "llms"]
    other_total = sum(topics.get(topic, 0.0) for topic in other_topics) or 1.0
    for topic in other_topics:
        boosted[topic] = remainder * (topics.get(topic, 0.0) / other_total)
    return _normalize_topic_weights(boosted)


def _merge_source_entity(
    entities: dict[str, float], source_entity: str | None, promote: bool = False
) -> dict[str, float]:
    if not source_entity:
        return entities
    if not entities:
        return {source_entity: 1.0}
    if source_entity in entities and not promote:
        return entities
    merged = dict(entities)
    merged[source_entity] = max(merged.get(source_entity, 0.0), 0.85 if promote else 0.55)
    total = sum(merged.values()) or 1.0
    return {entity: value / total for entity, value in merged.items()}


def build_features(
    title: str,
    text: str,
    source_kind: str | None = None,
    url: str | None = None,
    source_name: str | None = None,
):
    event_type = classify_event_type(title, source_kind=source_kind)
    topics = topic_probabilities(title)
    entities = extract_entities(f"{title}\n{text[:2000]}")
    funding_amount = parse_funding_amount(f"{title}\n{text[:2000]}")
    release_assessment = assess_official_model_release(
        title=title,
        text=text,
        url=url,
        source_name=source_name,
    )
    entities = _merge_source_entity(entities, release_assessment.source_entity)
    if release_assessment.is_official_model_release:
        event_type = EventType.MODEL_RELEASE
        topics = _boost_model_release_topics(topics)
        entities = _merge_source_entity(entities, release_assessment.source_entity, promote=True)
    return event_type, topics, entities, funding_amount
