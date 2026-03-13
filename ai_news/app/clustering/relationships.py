"""Compute pairwise cluster relationship edges.

Combines embedding cosine similarity with rule-based signals (shared entities,
event chain compatibility, topic similarity) to produce a ranked list of
``ClusterRelationshipEdge`` candidates suitable for the relationship graph API.
"""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants – ported from src/components/relationshipGraph.ts
# ---------------------------------------------------------------------------

EVENT_FAMILY_ALIASES: Dict[str, str] = {
    "announcement": "release",
    "benchmark": "benchmark",
    "benchmark_result": "benchmark",
    "big_tech_announcement": "release",
    "chip_hardware": "release",
    "collaboration": "partnership",
    "funding": "funding",
    "government_action": "policy",
    "grant": "funding",
    "launch": "release",
    "m_and_a": "ma",
    "merger": "ma",
    "model_release": "release",
    "open_source_release": "release",
    "partnership": "partnership",
    "policy": "policy",
    "policy_regulation": "policy",
    "product_launch": "release",
    "recall": "security",
    "regulation": "policy",
    "release": "release",
    "research": "research",
    "research_paper": "research",
    "security": "security",
    "security_incident": "security",
    "startup_funding": "funding",
    "update": "release",
}

EVENT_CHAIN_COMPATIBILITY: Set[str] = {
    "release:benchmark",
    "release:policy",
    "release:partnership",
    "research:release",
    "research:benchmark",
    "funding:release",
    "funding:partnership",
    "security:policy",
    "security:release",
    "policy:release",
    "policy:security",
    "partnership:release",
}

CORPORATE_SUFFIX_PATTERN = re.compile(
    r"\b(incorporated|inc|corp|corporation|company|co|llc|ltd|limited|plc|gmbh|ag)\b",
    re.IGNORECASE,
)

EMBEDDING_DIM = 384

_EDGE_TYPE_PRIORITY: Dict[str, int] = {
    "follow-up": 5,
    "reaction": 4,
    "competing": 3,
    "shared-entity": 3,
    "event-chain": 2,
    "embedding-similarity": 1,
    "market-adjacency": 0,
}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ClusterRelationshipEdge:
    """A scored, typed relationship between two clusters."""

    source_cluster_id: str
    target_cluster_id: str
    edge_type: str  # shared-entity | event-chain | embedding-similarity | market-adjacency | follow-up | reaction | competing
    combined_score: float
    embedding_similarity: float
    shared_entities: List[str]
    event_chain: bool
    topic_similarity: float
    evidence: List[str] = field(default_factory=list)
    llm_type: Optional[str] = None       # follow-up | reaction | competing | None
    llm_strength: Optional[float] = None  # 0.0-1.0
    llm_explanation: Optional[str] = None


@dataclass
class LLMCandidatePair:
    """A pair rejected by mechanical thresholds but worth LLM evaluation."""

    source_cluster_id: str
    target_cluster_id: str
    source_cluster: Dict[str, Any]
    target_cluster: Dict[str, Any]
    emb_sim: float
    shared_entities: List[str]
    event_chain_raw: float
    topic_sim: float
    reason: str  # why this pair is a candidate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalize_entity(name: str) -> str:
    """Lowercase, strip corporate suffixes, NFKD-normalize, collapse whitespace."""
    text = name.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    # Strip non-word non-space characters (mirrors TS /[^\w\s]/g → ' ')
    text = re.sub(r"[^\w\s]", " ", text, flags=re.ASCII)
    text = CORPORATE_SUFFIX_PATTERN.sub(" ", text)
    # Collapse all whitespace to nothing (matches TS .replace(/\s+/g, ''))
    text = re.sub(r"\s+", "", text)
    return text


def _entity_intersection(
    left_entities: List[Dict[str, Any]],
    right_entities: List[Dict[str, Any]],
    canon_map: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Return sorted list of display names for entities shared between two clusters.

    ``canon_map`` maps normalized entity strings to a canonical form so that
    aliases (e.g. "google" and "alphabet") resolve to the same key.
    """
    def _resolve(name: str) -> str:
        normalized = _normalize_entity(name)
        if canon_map:
            return canon_map.get(normalized, normalized)
        return normalized

    right_map: Dict[str, str] = {}
    for entity in right_entities:
        name = entity.get("name", "")
        key = _resolve(name)
        if key:
            right_map[key] = name

    shared: Dict[str, str] = {}
    for entity in left_entities:
        name = entity.get("name", "")
        key = _resolve(name)
        if not key or key not in right_map:
            continue
        shared[key] = name

    return sorted(shared.values())


def _event_family(event_type: str) -> str:
    """Map a raw event type string to its canonical family."""
    normalized = event_type.strip().lower()
    return EVENT_FAMILY_ALIASES.get(normalized, normalized) or "other"


def _event_chain_score(
    left_cluster: Dict[str, Any],
    right_cluster: Dict[str, Any],
) -> float:
    """Return 0-1 compatibility score factoring in event family and time decay."""
    left_family = _event_family(left_cluster.get("dominant_event_type", ""))
    right_family = _event_family(right_cluster.get("dominant_event_type", ""))

    forward = f"{left_family}:{right_family}"
    backward = f"{right_family}:{left_family}"

    if forward not in EVENT_CHAIN_COMPATIBILITY and backward not in EVENT_CHAIN_COMPATIBILITY:
        return 0.0

    left_age = left_cluster.get("age_hours", 0.0)
    right_age = right_cluster.get("age_hours", 0.0)
    time_delta_hours = abs(left_age - right_age)
    return _clamp01(1.0 - time_delta_hours / 96.0)


def _topic_cosine_similarity(
    left_weights: Dict[str, float],
    right_weights: Dict[str, float],
    left_topic: str,
    right_topic: str,
) -> float:
    """Cosine similarity over topic weight vectors with a dominant-topic bonus."""
    all_topics = set(left_weights) | set(right_weights)

    dot = 0.0
    left_mag = 0.0
    right_mag = 0.0
    for topic in all_topics:
        lv = left_weights.get(topic, 0.0)
        rv = right_weights.get(topic, 0.0)
        dot += lv * rv
        left_mag += lv * lv
        right_mag += rv * rv

    if left_mag > 0 and right_mag > 0:
        cosine = dot / math.sqrt(left_mag * right_mag)
    else:
        cosine = 0.0

    dominant_topic_bonus = 0.12 if left_topic == right_topic else 0.0
    return _clamp01(cosine + dominant_topic_bonus)


def _compute_combined_score(
    emb_sim: float,
    shared_entities: List[str],
    event_chain_raw: float,
    topic_sim: float,
) -> float:
    """Weighted combination: embedding 40%, entities up to 42%, event chain 12%, topic 10%."""
    emb_score = _clamp01((emb_sim - 0.55) / 0.45) * 0.40
    entity_score = (
        (0.30 if len(shared_entities) >= 1 else 0.0)
        + min(len(shared_entities) - 1, 2) * 0.06
    ) if shared_entities else 0.0
    chain_score = min(event_chain_raw, 1.0) * 0.12
    topic_score = _clamp01(topic_sim) * 0.10
    return _clamp01(emb_score + entity_score + chain_score + topic_score)


def _determine_edge_type(
    shared_entities: List[str],
    event_chain: bool,
    emb_sim: float,
    topic_sim: float,
) -> str:
    """Pick the highest-priority edge type that applies."""
    if shared_entities:
        return "shared-entity"
    if event_chain:
        return "event-chain"
    if emb_sim >= 0.55:
        return "embedding-similarity"
    return "market-adjacency"


def _describe_evidence(
    shared_entities: List[str],
    event_chain: bool,
    emb_sim: float,
    topic_sim: float,
) -> List[str]:
    """Build human-readable evidence strings for an edge."""
    evidence: List[str] = []
    if emb_sim > 0.0:
        evidence.append(f"Embedding similarity {emb_sim:.0%}")
    if shared_entities:
        evidence.append(f"Shared entities: {', '.join(shared_entities)}")
    if event_chain:
        evidence.append("Event chain evidence")
    if topic_sim > 0.0:
        evidence.append(f"Topic similarity {_clamp01(topic_sim):.0%}")
    return evidence


# ---------------------------------------------------------------------------
# Centroid extraction helpers
# ---------------------------------------------------------------------------


def _bytes_to_vector(data: bytes, dim: int = EMBEDDING_DIM) -> Optional[np.ndarray]:
    """Decode a centroid_embedding blob to a float32 numpy vector.

    Returns ``None`` when *data* is missing, empty, or has the wrong size.
    """
    if not data:
        return None
    expected_bytes = dim * 4  # float32 = 4 bytes
    if len(data) != expected_bytes:
        return None
    vec = np.frombuffer(data, dtype=np.float32).copy()
    if vec.size != dim:
        return None
    return vec


# ---------------------------------------------------------------------------
# Track B – LLM candidate selection
# ---------------------------------------------------------------------------


def _llm_candidate_reason(
    ci: Dict[str, Any],
    cj: Dict[str, Any],
    shared: List[str],
    emb_sim: float,
    topic_sim: float,
) -> Optional[str]:
    """Return a reason string if this pair is worth LLM evaluation, else None.

    Track B criteria (any one is sufficient):
    - Same non-mixed dominant topic but no shared entities
    - At least 1 shared entity but embedding similarity below threshold
    - Both clusters are "hot" (recent and well-covered)
    - Cross-topic event chain compatibility with recency
    - Cross-topic high-coverage clusters in temporal proximity
    - Cross-topic embedding near-miss below mechanical threshold
    """
    ci_topic = ci.get("dominant_topic", "mixed")
    cj_topic = cj.get("dominant_topic", "mixed")

    # --- Existing same-topic / entity / hot criteria ---
    if ci_topic == cj_topic and ci_topic != "mixed" and not shared:
        return "same_topic_no_entities"

    if len(shared) >= 1 and emb_sim < 0.55:
        return "shared_entity_low_embedding"

    ci_hot = ci.get("age_hours", 999) < 48 and ci.get("coverage_count", 0) >= 3
    cj_hot = cj.get("age_hours", 999) < 48 and cj.get("coverage_count", 0) >= 3
    if ci_hot and cj_hot:
        return "both_hot"

    # --- Cross-topic criteria ---
    both_non_mixed = ci_topic != "mixed" and cj_topic != "mixed"
    is_cross_topic = ci_topic != cj_topic and both_non_mixed

    if is_cross_topic:
        # Event chain compatibility across topics (e.g. research→release,
        # release→policy, funding→release).
        ci_family = _event_family(ci.get("dominant_event_type", ""))
        cj_family = _event_family(cj.get("dominant_event_type", ""))
        forward = f"{ci_family}:{cj_family}"
        backward = f"{cj_family}:{ci_family}"
        if forward in EVENT_CHAIN_COMPATIBILITY or backward in EVENT_CHAIN_COMPATIBILITY:
            min_age = min(ci.get("age_hours", 999), cj.get("age_hours", 999))
            if min_age < 72:
                return "cross_topic_event_chain"

        # High-coverage temporal proximity — major stories in different topics
        # appearing close together with slight topic overlap.
        ci_coverage = ci.get("coverage_count", 0)
        cj_coverage = cj.get("coverage_count", 0)
        if ci_coverage >= 5 and cj_coverage >= 5:
            age_delta = abs(ci.get("age_hours", 999) - cj.get("age_hours", 999))
            if age_delta < 48 and topic_sim >= 0.15:
                return "cross_topic_high_coverage"

    # Embedding near-miss: different topics with embedding similarity just
    # below the mechanical threshold — narratively adjacent content.
    if is_cross_topic and 0.45 <= emb_sim < 0.55:
        min_age = min(ci.get("age_hours", 999), cj.get("age_hours", 999))
        if min_age < 72:
            return "cross_topic_embedding_near_miss"

    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def compute_cluster_relationships(
    clusters: List[Dict[str, Any]],
    *,
    entity_canon_map: Optional[Dict[str, str]] = None,
    embedding_threshold: float = 0.55,
    max_edges: int = 100,
    return_llm_candidates: bool = False,
) -> (
    List[ClusterRelationshipEdge]
    | tuple[List[ClusterRelationshipEdge], List[LLMCandidatePair]]
):
    """Compute pairwise cluster relationship edges.

    Parameters
    ----------
    clusters:
        Each dict must contain:
        - ``id`` (str)
        - ``centroid_embedding`` (bytes, 384-dim float32)
        - ``entities`` (list of dicts with ``"name"`` key)
        - ``dominant_event_type`` (str)
        - ``topic_weights`` (dict[str, float])
        - ``age_hours`` (float)
        Optional:
        - ``dominant_topic`` (str) – used for topic bonus; defaults to ``"mixed"``
        - ``headline`` (str) – needed for LLM candidate context
        - ``top_summary`` (str) – needed for LLM candidate context
        - ``coverage_count`` (int) – used for Track B "hot" detection

    entity_canon_map:
        Maps normalized entity name → canonical form, enabling alias resolution.

    embedding_threshold:
        Minimum embedding cosine similarity to consider a pair (default 0.55).

    max_edges:
        Maximum number of edges to return (default 100).

    return_llm_candidates:
        When True, return a tuple of ``(edges, llm_candidates)`` where
        ``llm_candidates`` contains pairs that failed mechanical thresholds
        but are worth evaluating with an LLM.

    Returns
    -------
    list[ClusterRelationshipEdge]
        Sorted descending by ``combined_score``.  If *return_llm_candidates*
        is True, returns ``(edges, llm_candidates)`` instead.
    """
    empty: List[ClusterRelationshipEdge] = []
    if len(clusters) < 2:
        return (empty, []) if return_llm_candidates else empty

    # -- Build embedding matrix -------------------------------------------------
    n = len(clusters)
    valid_mask = np.zeros(n, dtype=bool)
    embeddings = np.zeros((n, EMBEDDING_DIM), dtype=np.float32)

    for idx, cluster in enumerate(clusters):
        vec = _bytes_to_vector(cluster.get("centroid_embedding"))
        if vec is None:
            continue
        norm = np.linalg.norm(vec)
        if norm == 0:
            continue
        embeddings[idx] = vec / norm
        valid_mask[idx] = True

    valid_count = int(valid_mask.sum())
    if valid_count < 2:
        logger.debug(
            "compute_cluster_relationships: only %d valid embeddings out of %d clusters; "
            "falling back to rule-based only for remaining pairs",
            valid_count,
            n,
        )

    # -- Pairwise cosine similarity via matrix multiply -------------------------
    # For clusters with valid embeddings the dot product gives cosine similarity
    # (vectors are already unit-normalized above).
    sim_matrix = embeddings @ embeddings.T

    # -- Iterate over upper triangle --------------------------------------------
    edges: List[ClusterRelationshipEdge] = []
    llm_candidates: List[LLMCandidatePair] = []

    for i in range(n):
        for j in range(i + 1, n):
            ci = clusters[i]
            cj = clusters[j]

            both_valid = valid_mask[i] and valid_mask[j]
            emb_sim = float(sim_matrix[i, j]) if both_valid else 0.0

            # --- Adaptive thresholds ------------------------------------------
            # Compute rule-based signals first so we can decide whether to
            # include pairs in the medium/weak embedding bands.
            shared = _entity_intersection(
                ci.get("entities", []),
                cj.get("entities", []),
                canon_map=entity_canon_map,
            )

            chain_raw = _event_chain_score(ci, cj)
            event_chain = chain_raw >= 0.42

            topic_sim = _topic_cosine_similarity(
                ci.get("topic_weights", {}),
                cj.get("topic_weights", {}),
                ci.get("dominant_topic", "mixed"),
                cj.get("dominant_topic", "mixed"),
            )

            # Apply adaptive thresholds
            passed_mechanical = True
            if emb_sim >= 0.75:
                # Strong — always include
                pass
            elif emb_sim >= 0.65:
                # Medium — need entity or event chain
                if not shared and not event_chain:
                    passed_mechanical = False
            elif emb_sim >= embedding_threshold:
                # Weak — need strong rule-based signals
                if len(shared) < 2 and not event_chain:
                    passed_mechanical = False
            else:
                # Below embedding threshold — only include if strong rule-based
                # signals exist (shared entities or event chain evidence).
                if len(shared) >= 2 or event_chain:
                    pass  # allow through on rule-based evidence alone
                else:
                    passed_mechanical = False

            # --- Track B: collect LLM candidates from rejected pairs ----------
            if not passed_mechanical and return_llm_candidates:
                candidate_reason = _llm_candidate_reason(ci, cj, shared, emb_sim, topic_sim)
                if candidate_reason:
                    src_id = str(ci["id"])
                    tgt_id = str(cj["id"])
                    if src_id > tgt_id:
                        src_id, tgt_id = tgt_id, src_id
                    llm_candidates.append(
                        LLMCandidatePair(
                            source_cluster_id=src_id,
                            target_cluster_id=tgt_id,
                            source_cluster=ci,
                            target_cluster=cj,
                            emb_sim=emb_sim,
                            shared_entities=shared,
                            event_chain_raw=chain_raw,
                            topic_sim=topic_sim,
                            reason=candidate_reason,
                        )
                    )

            if not passed_mechanical:
                continue

            # --- Scoring ------------------------------------------------------
            combined = _compute_combined_score(emb_sim, shared, chain_raw, topic_sim)
            if combined <= 0:
                continue

            edge_type = _determine_edge_type(shared, event_chain, emb_sim, topic_sim)
            evidence = _describe_evidence(shared, event_chain, emb_sim, topic_sim)

            # Canonicalize direction so source < target lexicographically
            src_id = str(ci["id"])
            tgt_id = str(cj["id"])
            if src_id > tgt_id:
                src_id, tgt_id = tgt_id, src_id

            edges.append(
                ClusterRelationshipEdge(
                    source_cluster_id=src_id,
                    target_cluster_id=tgt_id,
                    edge_type=edge_type,
                    combined_score=round(combined, 6),
                    embedding_similarity=round(emb_sim, 6),
                    shared_entities=shared,
                    event_chain=event_chain,
                    topic_similarity=round(topic_sim, 6),
                    evidence=evidence,
                )
            )

    # -- Sort descending by combined_score, then edge type priority, then id ----
    edges.sort(
        key=lambda e: (
            -e.combined_score,
            -_EDGE_TYPE_PRIORITY.get(e.edge_type, 0),
            e.source_cluster_id,
            e.target_cluster_id,
        ),
    )

    result_edges = edges[:max_edges]
    if return_llm_candidates:
        return result_edges, llm_candidates
    return result_edges


# ---------------------------------------------------------------------------
# Phase 3 – Score fusion with LLM inference results
# ---------------------------------------------------------------------------

# Minimum floor scores so strong LLM findings surface as visible edges.
_LLM_SCORE_FLOOR: Dict[str, float] = {
    "follow-up": 0.35,
    "reaction": 0.30,
    "competing": 0.32,
}


def fuse_llm_results(
    mechanical_edges: List[ClusterRelationshipEdge],
    llm_results: List[Any],
    *,
    max_edges: int = 100,
) -> List[ClusterRelationshipEdge]:
    """Merge LLM relationship classifications into the mechanical edge list.

    LLM results can:
    - **Create** new edges for pairs with no mechanical edge.
    - **Boost** existing edges when the LLM label is informative.
    - **Penalize** existing edges when the LLM says ``"unrelated"``.

    Parameters
    ----------
    mechanical_edges:
        Output of ``compute_cluster_relationships()``.
    llm_results:
        List of ``LLMRelationshipResult`` (from ``relationship_inference.py``).
        Each has ``source_cluster_id``, ``target_cluster_id``, ``label``,
        ``confidence``, ``explanation``.
    max_edges:
        Cap on returned edges.
    """
    # Index LLM results by canonicalized pair key
    llm_by_pair: Dict[tuple[str, str], Any] = {}
    for r in llm_results:
        key = (min(r.source_cluster_id, r.target_cluster_id),
               max(r.source_cluster_id, r.target_cluster_id))
        llm_by_pair[key] = r

    # Index mechanical edges for mutation
    edge_keys: set[tuple[str, str]] = set()
    for edge in mechanical_edges:
        key = (edge.source_cluster_id, edge.target_cluster_id)
        edge_keys.add(key)

        llm = llm_by_pair.get(key)
        if llm is None:
            continue

        if llm.label == "unrelated" and llm.confidence >= 0.7:
            # Penalize: reduce score by 40%
            edge.combined_score = round(edge.combined_score * 0.6, 6)
        elif llm.label != "unrelated":
            # Boost: take max of mechanical vs LLM-derived score
            floor = _LLM_SCORE_FLOOR.get(llm.label, 0.25)
            llm_derived = llm.confidence * 0.70 + floor * 0.30
            if llm_derived > edge.combined_score:
                edge.combined_score = round(llm_derived, 6)
            # Promote edge type if LLM is confident
            if llm.confidence >= 0.5:
                edge.edge_type = llm.label
            edge.llm_type = llm.label
            edge.llm_strength = round(llm.confidence, 4)
            edge.llm_explanation = llm.explanation

    # Create new edges for LLM-found relationships with no mechanical edge
    for key, llm in llm_by_pair.items():
        if key in edge_keys:
            continue
        if llm.label == "unrelated":
            continue
        if llm.confidence < 0.6:
            continue

        floor = _LLM_SCORE_FLOOR.get(llm.label, 0.25)
        score = llm.confidence * 0.70 + floor * 0.30

        mechanical_edges.append(
            ClusterRelationshipEdge(
                source_cluster_id=key[0],
                target_cluster_id=key[1],
                edge_type=llm.label,
                combined_score=round(score, 6),
                embedding_similarity=0.0,
                shared_entities=[],
                event_chain=False,
                topic_similarity=0.0,
                evidence=[llm.explanation] if llm.explanation else [],
                llm_type=llm.label,
                llm_strength=round(llm.confidence, 4),
                llm_explanation=llm.explanation,
            )
        )

    # Re-sort after fusion
    mechanical_edges.sort(
        key=lambda e: (
            -e.combined_score,
            -_EDGE_TYPE_PRIORITY.get(e.edge_type, 0),
            e.source_cluster_id,
            e.target_cluster_id,
        ),
    )

    return mechanical_edges[:max_edges]
