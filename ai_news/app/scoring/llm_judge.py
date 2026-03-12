"""LLM significance judge — Stage 3 scoring for top articles."""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

SIGNIFICANCE_PROMPT = '''You are an AI industry analyst. Score this news article's significance.

Rate on three dimensions (each 1-10):

IMPACT: How much does this change the AI landscape?
  9-10: Industry-reshaping (new frontier model, major acquisition >$1B, landmark regulation)
  7-8: Significant for a sub-field (notable model release, major open-source project, $100M+ funding)
  5-6: Noteworthy (product update, benchmark result, mid-size funding)
  3-4: Minor (small startup news, incremental update, opinion piece)
  1-2: Noise (marketing fluff, minor bug fix, rumor with no substance)

BREADTH: How many AI practitioners/stakeholders does this affect?
  9-10: Everyone in AI (infrastructure shift, safety regulation, foundational model)
  7-8: Large sub-community (all NLP researchers, all ML engineers, all AI startups)
  5-6: Specific niche (robotics researchers, speech specialists, one company's users)
  3-4: Very narrow audience
  1-2: Almost no one

NOVELTY: How new/surprising is this?
  9-10: Completely unexpected, paradigm-shifting
  7-8: Surprising, advances expectations significantly
  5-6: Expected development, but meaningful execution
  3-4: Incremental, predictable
  1-2: Already known, rehash, or obvious

Article title: {title}
Source: {source_name}
Event type: {event_type}
Summary (first 500 chars): {text_preview}

Respond with ONLY a JSON object:
{{"impact": <int>, "breadth": <int>, "novelty": <int>}}'''


def build_significance_prompt(
    title: str,
    source_name: str,
    event_type: str,
    text_preview: str,
) -> str:
    """Build the calibrated 3-dimension significance prompt."""
    # Truncate preview to ~800 chars to keep token cost low
    preview = (text_preview or "")[:800]
    return SIGNIFICANCE_PROMPT.format(
        title=title,
        source_name=source_name,
        event_type=event_type,
        text_preview=preview,
    )


def parse_llm_response(response: str) -> tuple[int, int, int] | None:
    """Extract impact/breadth/novelty scores from LLM JSON response."""
    try:
        data = json.loads(response.strip())
    except json.JSONDecodeError:
        # Try to extract JSON from surrounding text
        match = re.search(r'\{[^}]+\}', response)
        if not match:
            logger.warning("LLM judge: could not parse response: %s", response[:200])
            return None
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            logger.warning("LLM judge: invalid JSON in response: %s", response[:200])
            return None

    try:
        impact = int(data["impact"])
        breadth = int(data["breadth"])
        novelty = int(data["novelty"])
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("LLM judge: missing/invalid fields: %s", exc)
        return None

    # Normalize to 1-10 scale.
    # Some models may still return 0-100; convert defensively.
    if impact > 10 or breadth > 10 or novelty > 10:
        impact = round(impact / 10)
        breadth = round(breadth / 10)
        novelty = round(novelty / 10)
    impact = max(1, min(10, impact))
    breadth = max(1, min(10, breadth))
    novelty = max(1, min(10, novelty))

    return impact, breadth, novelty


def llm_significance_score(impact: int, breadth: int, novelty: int) -> float:
    """Weighted conversion of 1-10 dimensions into a 0-100 score."""
    raw = 0.50 * impact + 0.25 * breadth + 0.25 * novelty
    score = (raw - 1) * 100 / 9
    return round(max(0.0, min(100.0, score)), 2)


def compute_final_score(rule_score: float, llm_score: float | None) -> float:
    """Blend rule-based and LLM scores without lowering strong rule scores."""
    if llm_score is None:
        return rule_score
    blended = 0.70 * rule_score + 0.30 * llm_score
    return round(max(rule_score, blended), 2)
