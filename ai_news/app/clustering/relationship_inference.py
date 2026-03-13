"""Batch LLM relationship inference for cluster pairs.

Takes candidate pairs (from Track B in ``relationships.py``) and classifies
each using an LLM.  Results are cached via the existing ``llm/cache.py``
helpers so repeated calls for the same pair are free.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RELATIONSHIP_LABELS = frozenset({"follow-up", "reaction", "competing", "unrelated"})

BATCH_SIZE = 15  # pairs per LLM call

_SYSTEM_PROMPT = (
    "You classify relationships between pairs of AI news clusters. "
    "Return strict JSON only — an array of objects."
)

_USER_PROMPT_TEMPLATE = """\
For each numbered pair of news clusters, classify the relationship.

Labels (pick exactly one per pair):
- follow-up: B is a continuation, consequence, or next chapter of A's story
- reaction: B is a market, industry, public, or regulatory response to A
- competing: A and B are rival products, approaches, or announcements aimed at the same space
- unrelated: no meaningful narrative relationship

{pairs_block}

Return a JSON array:
[{{"pair": 1, "label": "follow-up", "confidence": 0.85, "explanation": "one sentence"}}]

Rules:
- confidence is 0.0-1.0
- explanation must be one short sentence
- if unsure, label as "unrelated" with low confidence"""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class LLMRelationshipResult:
    """Inference result for a single cluster pair."""

    source_cluster_id: str
    target_cluster_id: str
    label: str       # follow-up | reaction | competing | unrelated
    confidence: float  # 0.0–1.0
    explanation: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pair_cache_key(id_a: str, id_b: str) -> str:
    """Deterministic cache key for a cluster pair."""
    canonical = "::".join(sorted([id_a, id_b]))
    h = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    return f"rel_infer:{h}"


def _build_pair_block(index: int, cluster_a: Dict[str, Any], cluster_b: Dict[str, Any]) -> str:
    """Format one pair for the prompt."""
    def _fmt(c: Dict[str, Any]) -> str:
        headline = c.get("headline", "Unknown")
        summary = (c.get("top_summary") or "")[:200]
        entities = [e.get("name", "") for e in c.get("entities", [])[:3]]
        event = c.get("dominant_event_type", "OTHER")
        topic = c.get("dominant_topic", "mixed")
        lines = [f'  Headline: {headline}']
        if summary:
            lines.append(f'  Summary: {summary}')
        if entities:
            lines.append(f'  Entities: {", ".join(entities)}')
        lines.append(f'  Event: {event} | Topic: {topic}')
        return "\n".join(lines)

    return f"Pair {index}:\nA:\n{_fmt(cluster_a)}\nB:\n{_fmt(cluster_b)}"


def _parse_llm_response(
    raw: str,
    pair_ids: List[tuple[str, str]],
) -> List[LLMRelationshipResult]:
    """Parse LLM JSON response into typed results."""
    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("relationship_inference: failed to parse LLM response: %.500s", raw)
        return []

    # Handle {"results": [...]} or {"pairs": [...]} wrappers
    if isinstance(items, dict):
        for key in ("results", "pairs", "relationships", "data"):
            if key in items and isinstance(items[key], list):
                items = items[key]
                break

    if not isinstance(items, list):
        items = [items]

    results: List[LLMRelationshipResult] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        pair_idx = item.get("pair", 0)
        # pair indices are 1-based in prompt
        list_idx = pair_idx - 1
        if list_idx < 0 or list_idx >= len(pair_ids):
            continue

        label = str(item.get("label", "unrelated")).lower().strip()
        if label not in RELATIONSHIP_LABELS:
            label = "unrelated"

        confidence = item.get("confidence", 0.5)
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.5

        explanation = str(item.get("explanation", ""))[:200]

        src_id, tgt_id = pair_ids[list_idx]
        results.append(
            LLMRelationshipResult(
                source_cluster_id=src_id,
                target_cluster_id=tgt_id,
                label=label,
                confidence=confidence,
                explanation=explanation,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def infer_relationships(
    candidates: List[Any],
    *,
    llm: Optional[Any] = None,
    cache_only: bool = False,
) -> List[LLMRelationshipResult]:
    """Run batch LLM inference on candidate cluster pairs.

    Parameters
    ----------
    candidates:
        List of ``LLMCandidatePair`` objects from
        ``compute_cluster_relationships(..., return_llm_candidates=True)``.
    llm:
        Optional ``LLMClient`` instance.  Created on demand if not provided.
    cache_only:
        When True, only return cached results.  Pairs without a cached
        result are skipped (no LLM calls made).  Useful in the hot API
        path where latency matters.

    Returns
    -------
    list[LLMRelationshipResult]
    """
    if not candidates:
        return []

    from app.llm.cache import get_cached, set_cached

    # Separate cached vs uncached
    all_results: List[LLMRelationshipResult] = []
    uncached: List[Any] = []

    for cand in candidates:
        cache_key = _pair_cache_key(cand.source_cluster_id, cand.target_cluster_id)
        cached = get_cached(cache_key)
        if cached:
            label = cached.get("label", "unrelated")
            all_results.append(
                LLMRelationshipResult(
                    source_cluster_id=cand.source_cluster_id,
                    target_cluster_id=cand.target_cluster_id,
                    label=label if label in RELATIONSHIP_LABELS else "unrelated",
                    confidence=cached.get("confidence", 0.5),
                    explanation=cached.get("explanation", ""),
                )
            )
        else:
            uncached.append(cand)

    if cache_only or not uncached:
        return all_results

    # Lazy-import and create LLMClient if needed
    if llm is None:
        from app.llm.client import LLMClient
        llm = LLMClient()

    if not llm.enabled:
        logger.info("relationship_inference: LLM disabled, returning cached results only")
        return all_results

    # Batch uncached pairs
    for batch_start in range(0, len(uncached), BATCH_SIZE):
        batch = uncached[batch_start : batch_start + BATCH_SIZE]
        pair_blocks: List[str] = []
        pair_ids: List[tuple[str, str]] = []

        for idx, cand in enumerate(batch, start=1):
            pair_blocks.append(
                _build_pair_block(idx, cand.source_cluster, cand.target_cluster)
            )
            pair_ids.append((cand.source_cluster_id, cand.target_cluster_id))

        prompt = _USER_PROMPT_TEMPLATE.format(pairs_block="\n\n".join(pair_blocks))

        try:
            raw = llm.chat(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                json_object=True,
            )
        except Exception:
            logger.exception(
                "relationship_inference: LLM call failed for batch of %d pairs", len(batch)
            )
            continue

        logger.debug("relationship_inference: raw LLM response (%.300s)", raw)
        results = _parse_llm_response(raw, pair_ids)

        # Cache individual results
        for r in results:
            cache_key = _pair_cache_key(r.source_cluster_id, r.target_cluster_id)
            set_cached(cache_key, {
                "label": r.label,
                "confidence": r.confidence,
                "explanation": r.explanation,
            })

        all_results.extend(results)

    logger.info(
        "relationship_inference: %d cached, %d inferred (%d batches)",
        len(candidates) - len(uncached),
        len(all_results) - (len(candidates) - len(uncached)),
        (len(uncached) + BATCH_SIZE - 1) // BATCH_SIZE if uncached else 0,
    )

    return all_results
