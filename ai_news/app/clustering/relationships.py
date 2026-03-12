"""Compute pairwise cluster relationship edges.

Combines embedding cosine similarity with rule-based signals (shared entities,
event chain compatibility, topic similarity) to produce a ranked list of
``ClusterRelationshipEdge`` candidates suitable for the relationship graph API.
"""

from __future__ import annotations

import logging
import math
import re
import struct
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
    "collaboration": "partnership",
    "funding": "funding",
    "grant": "funding",
    "launch": "release",
    "merger": "ma",
    "partnership": "partnership",
    "policy": "policy",
    "recall": "security",
    "regulation": "policy",
    "release": "release",
    "research": "research",
    "security": "security",
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

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ClusterRelationshipEdge:
    """A scored, typed relationship between two clusters."""

    source_cluster_id: str
    target_cluster_id: str
    edge_type: str  # shared-entity | event-chain | embedding-similarity | market-adjacency
    combined_score: float
    embedding_similarity: float
    shared_entities: List[str]
    event_chain: bool
    topic_similarity: float
    evidence: List[str] = field(default_factory=list)


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
    text = re.sub(r"[^\w\s]", " ", text)
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
    event_chain: bool,
    topic_sim: float,
) -> float:
    """Weighted combination: embedding 40%, entities up to 42%, event chain 12%, topic 10%."""
    emb_score = _clamp01((emb_sim - 0.55) / 0.45) * 0.40
    entity_score = (
        (0.30 if len(shared_entities) >= 1 else 0.0)
        + min(len(shared_entities) - 1, 2) * 0.06
    ) if shared_entities else 0.0
    chain_score = 0.12 if event_chain else 0.0
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
# Main entry point
# ---------------------------------------------------------------------------


def compute_cluster_relationships(
    clusters: List[Dict[str, Any]],
    *,
    entity_canon_map: Optional[Dict[str, str]] = None,
    embedding_threshold: float = 0.55,
    max_edges: int = 100,
) -> List[ClusterRelationshipEdge]:
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

    entity_canon_map:
        Maps normalized entity name → canonical form, enabling alias resolution.

    embedding_threshold:
        Minimum embedding cosine similarity to consider a pair (default 0.55).

    max_edges:
        Maximum number of edges to return (default 100).

    Returns
    -------
    list[ClusterRelationshipEdge]
        Sorted descending by ``combined_score``.
    """
    if len(clusters) < 2:
        return []

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
            if emb_sim >= 0.75:
                # Strong — always include
                pass
            elif emb_sim >= 0.65:
                # Medium — need entity or event chain
                if not shared and not event_chain:
                    continue
            elif emb_sim >= embedding_threshold:
                # Weak — need strong rule-based signals
                if len(shared) < 2 and not event_chain:
                    continue
            else:
                # Below threshold — only include if strong rule-based signals
                # exist even without embedding support (handles clusters where
                # one or both embeddings are invalid).
                if not both_valid and (len(shared) >= 2 or event_chain):
                    pass  # allow through on rule-based evidence alone
                else:
                    continue

            # --- Scoring ------------------------------------------------------
            combined = _compute_combined_score(emb_sim, shared, event_chain, topic_sim)
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
    _EDGE_TYPE_PRIORITY = {
        "shared-entity": 3,
        "event-chain": 2,
        "embedding-similarity": 1,
        "market-adjacency": 0,
    }

    edges.sort(
        key=lambda e: (
            -e.combined_score,
            -_EDGE_TYPE_PRIORITY.get(e.edge_type, 0),
            e.source_cluster_id,
            e.target_cluster_id,
        ),
    )

    return edges[:max_edges]
