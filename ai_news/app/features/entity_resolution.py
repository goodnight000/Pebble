"""Embedding-based entity resolution.

Resolves entity name aliases (e.g. "Google" / "Alphabet", "GPT-4" / "GPT-4o")
by clustering entity name embeddings and mapping every variant to a canonical
form.  Results are cached at module level for reuse by the relationship
computation pipeline.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

import numpy as np

from app.common.embeddings import embed_texts
from app.config import load_entity_aliases

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy scipy imports – these are transitive deps via scikit-learn / faiss and
# should always be available at runtime, but we guard to keep the module
# importable in minimal test environments.
# ---------------------------------------------------------------------------

try:
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    _SCIPY_AVAILABLE = True
except ImportError:  # pragma: no cover
    _SCIPY_AVAILABLE = False

# ---------------------------------------------------------------------------
# Normalization (mirrors relationships._normalize_entity)
# ---------------------------------------------------------------------------

_CORPORATE_SUFFIX_PATTERN = re.compile(
    r"\b(incorporated|inc|corp|corporation|company|co|llc|ltd|limited|plc|gmbh|ag)\b",
    re.IGNORECASE,
)


def _normalize_entity(name: str) -> str:
    """Lowercase, NFKD-normalize, strip symbols & corporate suffixes, collapse ws."""
    text = name.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.ASCII)
    text = _CORPORATE_SUFFIX_PATTERN.sub(" ", text)
    text = re.sub(r"\s+", "", text)
    return text


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class EntityResolutionResult:
    """Holds the output of an entity resolution run."""

    canon_map: Dict[str, str]  # normalized entity name -> canonical display form
    clusters: List[Set[str]]  # groups of equivalent entity names
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------

_CACHED_RESULT: Optional[EntityResolutionResult] = None


def get_cached_entity_resolution() -> Optional[Dict[str, str]]:
    """Return the cached canon_map, or ``None`` if not yet computed."""
    if _CACHED_RESULT is None:
        return None
    return _CACHED_RESULT.canon_map


def update_entity_resolution_cache(result: EntityResolutionResult) -> None:
    """Update the module-level cache."""
    global _CACHED_RESULT
    _CACHED_RESULT = result


# ---------------------------------------------------------------------------
# Static alias helpers
# ---------------------------------------------------------------------------


def _load_static_alias_map() -> Dict[str, str]:
    """Build a mapping of *normalized* alias -> canonical display name from config.

    Uses the same normalisation as ``_normalize_entity`` so that lookups in the
    relationship module's ``_entity_intersection`` are compatible.
    """
    data = load_entity_aliases()
    aliases = data.get("aliases", {})
    mapping: Dict[str, str] = {}
    for canonical, names in aliases.items():
        for name in names:
            mapping[_normalize_entity(name)] = canonical
    return mapping


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def resolve_entities(
    entity_names: List[str],
    distance_threshold: float = 0.15,
) -> EntityResolutionResult:
    """Cluster entity names by embedding similarity and return a canon map.

    Parameters
    ----------
    entity_names:
        Raw entity display names collected from articles/clusters.
    distance_threshold:
        Maximum average-linkage cosine distance to merge two names into the
        same cluster (default 0.15 ≈ 0.85 cosine similarity).

    Returns
    -------
    EntityResolutionResult
        ``canon_map`` keys are *normalized* entity strings (matching the
        format used by ``relationships._normalize_entity``).
    """

    static_aliases = _load_static_alias_map()

    # -- Deduplicate (case-insensitive) keeping first-seen display form -----
    seen_lower: Dict[str, str] = {}  # lowercase -> original display form
    unique_names: List[str] = []
    for name in entity_names:
        key = name.strip().lower()
        if not key:
            continue
        if key not in seen_lower:
            seen_lower[key] = name.strip()
            unique_names.append(name.strip())

    # -- Edge case: nothing to resolve --------------------------------------
    if len(unique_names) == 0:
        return EntityResolutionResult(
            canon_map=dict(static_aliases),
            clusters=[],
        )

    if len(unique_names) == 1:
        norm = _normalize_entity(unique_names[0])
        canonical = static_aliases.get(norm, unique_names[0])
        canon_map = dict(static_aliases)
        canon_map[norm] = canonical
        lc = unique_names[0].strip().lower()
        if lc:
            canon_map[lc] = canonical
        return EntityResolutionResult(
            canon_map=canon_map,
            clusters=[{unique_names[0]}],
        )

    # -- Embed all unique names ---------------------------------------------
    try:
        embeddings = embed_texts(unique_names)
    except Exception:
        logger.warning("embed_texts failed; falling back to static aliases only", exc_info=True)
        return _static_only_result(unique_names, static_aliases)

    if embeddings is None or embeddings.size == 0:
        logger.warning("embed_texts returned empty; falling back to static aliases only")
        return _static_only_result(unique_names, static_aliases)

    # -- L2-normalize (embed_texts with sentence-transformers already does
    #    this, but the hash fallback may not be perfectly unit-length) -------
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    embeddings = embeddings / norms

    # -- Pairwise cosine distance matrix ------------------------------------
    sim_matrix = embeddings @ embeddings.T
    # Clip to [0, 2] range to avoid tiny floating-point negatives
    dist_matrix = np.clip(1.0 - sim_matrix, 0.0, 2.0)

    # Zero out the diagonal (should already be ~0, but ensure exactness)
    np.fill_diagonal(dist_matrix, 0.0)

    # -- Agglomerative clustering -------------------------------------------
    if not _SCIPY_AVAILABLE:
        logger.warning("scipy unavailable; falling back to static aliases only")
        return _static_only_result(unique_names, static_aliases)

    condensed = squareform(dist_matrix)
    Z = linkage(condensed, method="average")
    labels = fcluster(Z, t=distance_threshold, criterion="distance")

    # -- Group entities by cluster label ------------------------------------
    groups: Dict[int, List[str]] = {}
    for idx, label in enumerate(labels):
        groups.setdefault(int(label), []).append(unique_names[idx])

    # -- Pick canonical name per group and build the canon_map --------------
    canon_map: Dict[str, str] = dict(static_aliases)
    result_clusters: List[Set[str]] = []

    for members in groups.values():
        cluster_set = set(members)
        result_clusters.append(cluster_set)

        canonical = _pick_canonical(members, static_aliases)

        for member in members:
            norm = _normalize_entity(member)
            if norm:
                canon_map[norm] = canonical
            # Also store a simple lowercase key so that callers using
            # ``name.lower()`` lookups (e.g. ``_merge_entities``) can
            # find the canonical form without full normalisation.
            lc = member.strip().lower()
            if lc:
                canon_map[lc] = canonical

    return EntityResolutionResult(
        canon_map=canon_map,
        clusters=result_clusters,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _pick_canonical(members: List[str], static_aliases: Dict[str, str]) -> str:
    """Choose the canonical display name for a cluster of entity names.

    Priority:
    1. If any member has a static alias canonical form, use that.
    2. Otherwise, use the shortest member name (most concise / proper form).
    """
    # Check if any member resolves to a static canonical
    for member in members:
        norm = _normalize_entity(member)
        if norm in static_aliases:
            return static_aliases[norm]

    # Fall back to shortest name
    return min(members, key=len)


def _static_only_result(
    entity_names: List[str],
    static_aliases: Dict[str, str],
) -> EntityResolutionResult:
    """Build a resolution result using only the static alias map (fallback)."""
    canon_map: Dict[str, str] = dict(static_aliases)
    clusters: List[Set[str]] = []

    for name in entity_names:
        norm = _normalize_entity(name)
        if norm and norm not in canon_map:
            canon_map[norm] = name
        lc = name.strip().lower()
        if lc and lc not in canon_map:
            canon_map[lc] = name
        clusters.append({name})

    return EntityResolutionResult(
        canon_map=canon_map,
        clusters=clusters,
    )
