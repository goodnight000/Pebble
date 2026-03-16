"""LLM significance judge — Stage 3 scoring for top articles."""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

SIGNIFICANCE_PROMPT = '''Rate this AI news article's significance on three dimensions (each 1-10 integer).

IMPACT — How much does this change the AI landscape?
  9-10: Industry-reshaping (new frontier model from a top lab, landmark regulation, >$1B acquisition)
  7-8:  Significant advance in a sub-field (notable model release, major open-source project, $100M+ funding)
  5-6:  Noteworthy (product update, solid benchmark result, mid-size funding round)
  3-4:  Minor (small startup news, incremental update, opinion/commentary piece)
  1-2:  Noise (marketing fluff, minor bug fix, unsubstantiated rumor)

BREADTH — How many AI practitioners/stakeholders are affected?
  9-10: Everyone in AI (foundational infrastructure shift, safety regulation, new base model)
  7-8:  Large sub-community (all NLP researchers, all ML engineers, all AI startups)
  5-6:  Specific niche (robotics researchers, speech specialists, one company's user base)
  3-4:  Very narrow audience
  1-2:  Almost no one

NOVELTY — How new or surprising is this?
  9-10: Completely unexpected, no prior leaks or signals
  7-8:  Surprising, significantly advances expectations
  5-6:  Expected development, but now confirmed with meaningful substance
  3-4:  Incremental, predictable follow-up to known story
  1-2:  Already widely known, rehash, or obvious

Scoring discipline:
- Most articles should score 3-6 on each dimension. Reserve 8+ for genuinely exceptional news.
- A routine product update from a major company is still 5-6 impact, not 8+.
- Funding rounds under $50M are typically 4-5 impact unless the company is unusually notable.
- Articles not related to AI/ML should score 1-2 on ALL dimensions.
- General tech tutorials or non-AI software news should score 1-2 across the board.
- Government actions unrelated to AI/tech should score 1 on all dimensions.

Title: {title}
Source: {source_name}
Event type: {event_type}
Content preview: {text_preview}

Return ONLY: {{"impact": <int 1-10>, "breadth": <int 1-10>, "novelty": <int 1-10>}}'''


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


def compute_final_score(
    rule_score: float,
    llm_score: float | None,
    *,
    confirmation_level: str | None = None,
    trust_label: str | None = None,
    verification_state: str | None = None,
    verification_confidence: float | None = None,
    update_status: str | None = None,
) -> float:
    """Blend rule-based and LLM scores, allowing bounded downward correction."""
    if llm_score is None:
        return rule_score
    if update_status in {"corrected", "retracted"}:
        return round(min(rule_score, 0.50 * rule_score + 0.50 * llm_score), 2)
    blended = 0.55 * rule_score + 0.45 * llm_score
    if blended >= rule_score:
        return round(blended, 2)
    # Downward correction with guardrails
    delta = rule_score - blended
    if verification_state in {"verified_artifact", "official_statement", "corroborated_report"}:
        delta = delta * 0.5
    if verification_state == "single_source_report" and (verification_confidence or 0) >= 70:
        delta = delta * 0.75
    if confirmation_level == "official":
        delta = min(delta, 5.0)
    if trust_label in ("official", "confirmed", "likely"):
        delta = delta * 0.5
    delta = min(delta, 20.0)  # Was 15 — allow LLM to correct over-scored articles more
    return round(rule_score - delta, 2)
