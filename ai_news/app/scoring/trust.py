"""Trust score system — 5-component weighted scoring with explainable labels."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from ..models import Article

# ── Weights ──────────────────────────────────────────────────────────
TRUST_WEIGHTS = {
    "corroboration": 0.30,
    "official_confirmation": 0.25,
    "source_trust": 0.20,
    "claim_quality": 0.15,
    "primary_document": 0.10,
}

# ── Patterns ─────────────────────────────────────────────────────────
HEDGE_PATTERNS = [
    r"\b(?:reportedly|allegedly|rumored?|unconfirmed|could|might|may)\b",
    r"\b(?:sources?\s+say|according\s+to\s+(?:unnamed|anonymous))\b",
    r"\b(?:it\s+is\s+(?:believed|thought|speculated))\b",
    r"\b(?:appears?\s+to|seems?\s+to|is\s+said\s+to)\b",
]

STRONG_ATTRIBUTION_PATTERNS = [
    r"\b(?:announced|confirmed|stated|said\s+in\s+a\s+(?:statement|blog\s+post|press\s+release))\b",
    r"\b(?:according\s+to\s+(?:the\s+company|officials?|the\s+report|documents?))\b",
    r"\b(?:in\s+a\s+(?:filing|report|paper|announcement))\b",
    r"\b(?:told\s+(?:reporters|journalists|media))\b",
]

SPECIFICITY_PATTERNS = [
    r"\$[\d,.]+\s*(?:million|billion|M|B)\b",
    r"\b\d+(?:\.\d+)?%\b",
    r"\bversion\s+\d+\b",
    r"\b\d+\s*(?:parameters?|params?|tokens?)\b",
]

PRIMARY_DOC_PATTERNS = [
    r"arxiv\.org/abs/",
    r"github\.com/.+/releases",
    r"doi\.org/",
    r"sec\.gov/",
    r"pypi\.org/project/",
    r"huggingface\.co/.+/",
    r"blog\.(openai|anthropic|google|meta)\.com",
]

OFFICIAL_DOMAINS = {
    "openai.com", "deepmind.google", "anthropic.com", "nvidia.com",
    "microsoft.com", "meta.com", "ai.meta.com", "research.google",
    "blog.google", "apple.com", "amazon.science", "x.ai",
}

CONTRADICTORY_PATTERNS = [
    r"\b(?:denied|refuted|walked\s+back|contradicted|false|inaccurate)\b",
]


@dataclass
class TrustScoreInputs:
    cluster_articles: list = field(default_factory=list)
    source_authority: float = 0.0
    is_primary_source: bool = False
    text: str = ""
    url: str = ""
    primary_entity: str | None = None
    independent_sources: int = 0
    event_type: str = "OTHER"


# ── Component functions ──────────────────────────────────────────────

def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def estimate_independent_sources(cluster_articles: list) -> int:
    """Estimate truly independent sources with wire-echo and attribution penalties."""
    if not cluster_articles:
        return 0
    source_domains: set[str] = set()
    texts: list[str] = []

    for art in cluster_articles:
        domain = urlparse(getattr(art, "final_url", "") or "").hostname or ""
        if domain.startswith("www."):
            domain = domain[4:]
        if domain:
            source_domains.add(domain)
        text = (getattr(art, "text", "") or "")[:500]
        if text:
            texts.append(text)

    independent_count = max(1, len(source_domains)) if source_domains else 0

    # Wire echo collapse when most copies are near-identical.
    if len(texts) >= 2:
        reference = texts[0]
        echo_count = sum(1 for t in texts[1:] if SequenceMatcher(None, reference, t).ratio() > 0.60)
        if echo_count > len(texts) * 0.6:
            independent_count = max(1, independent_count // 2)

    # Attribution-chain penalty (everyone cites one original source).
    attribution_sources: set[str] = set()
    for art in cluster_articles:
        text = (getattr(art, "text", "") or "")[:1000]
        if not text:
            continue
        for pattern in [
            r"according\s+to\s+(\w+(?:\s+\w+)?)",
            r"as\s+(?:first\s+)?reported\s+by\s+(\w+(?:\s+\w+)?)",
        ]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                attribution_sources.add(match.group(1).lower())
    if attribution_sources and len(attribution_sources) == 1:
        independent_count = max(1, independent_count - len(cluster_articles) // 2)

    return independent_count


def corroboration_trust_score(independent_sources: int, avg_authority: float) -> float:
    """Corroboration component of trust score."""
    if independent_sources <= 0:
        return 0.1
    source_factor = math.log(1 + independent_sources) / math.log(1 + 10)
    source_factor = min(1.0, source_factor)
    quality_weighted = source_factor * (0.5 + 0.5 * _clamp01(avg_authority))
    return quality_weighted


def official_confirmation_score(
    cluster_articles: list,
    primary_entity: str | None,
) -> tuple[float, str]:
    """Check if any article in cluster is from an official source.

    Returns (score_0_1, confirmation_level).
    """
    has_official = False
    has_press_release = False
    has_entity_confirmation = False

    for art in cluster_articles:
        url = getattr(art, "final_url", "") or ""
        host = urlparse(url).hostname or ""
        if any(host == d or host.endswith("." + d) for d in OFFICIAL_DOMAINS):
            has_official = True
        text = (getattr(art, "body", "") or getattr(art, "text", "") or "").lower()
        if any(phrase in text for phrase in [
            "press release", "we are pleased to announce", "today we released",
            "today we are launching", "we are open-sourcing", "we are excited to share",
        ]):
            has_press_release = True

        if primary_entity:
            entity_lower = primary_entity.lower()
            if re.search(rf"{re.escape(entity_lower)}\s+(?:said|confirmed|announced|stated)", text):
                has_entity_confirmation = True

    if has_official or has_press_release:
        return 1.0, "official"
    if has_entity_confirmation:
        return 0.75, "attributed"
    if any(
        re.search(r"\b(?:sources?|people)\s+(?:say|said|familiar|close)", (getattr(a, "text", "") or "").lower())
        for a in cluster_articles
    ):
        return 0.25, "unattributed"
    else:
        return 0.05, "rumor"


def source_trust_score(source_authority: float, is_primary_source: bool) -> float:
    """Source reliability with primary source boost."""
    base = _clamp01(source_authority)
    if is_primary_source:
        base = min(1.0, base * 1.15)
    return base


def claim_quality_score(text: str) -> tuple[float, float, float, float]:
    """Analyze text for hedging, attribution, and specificity.

    Returns (quality_score, hedging_ratio, attribution_ratio, specificity_score).
    """
    if not text:
        return 0.5, 0.0, 0.0, 0.0

    sample = text[:5000].lower()
    sentences = [s.strip() for s in re.split(r"[.!?]+", sample) if len(s.strip()) > 10]
    n_sentences = max(len(sentences), 1)

    # Hedging ratio (lower is better for trust)
    hedge_count = sum(
        1 for s in sentences
        if any(re.search(p, s, re.IGNORECASE) for p in HEDGE_PATTERNS)
    )
    hedging_ratio = hedge_count / n_sentences

    # Attribution ratio (higher is better)
    attr_count = sum(
        1 for s in sentences
        if any(re.search(p, s, re.IGNORECASE) for p in STRONG_ATTRIBUTION_PATTERNS)
    )
    attribution_ratio = min(attr_count / n_sentences, 1.0)

    # Specificity (higher is better)
    spec_count = sum(1 for p in SPECIFICITY_PATTERNS if re.search(p, sample, re.IGNORECASE))
    specificity = min(spec_count / 3.0, 1.0)  # 3+ specific claims → 1.0

    # Quality: penalize hedging, reward attribution and specificity
    quality = _clamp01(
        0.40 * (1.0 - hedging_ratio) + 0.35 * attribution_ratio + 0.25 * specificity
    )

    return quality, hedging_ratio, attribution_ratio, specificity


def has_primary_document(text: str, url: str) -> bool:
    """Check if article references or links to a primary document."""
    combined = (text or "")[:5000] + " " + (url or "")
    return any(re.search(p, combined, re.IGNORECASE) for p in PRIMARY_DOC_PATTERNS)


def compute_trust_score(inputs: TrustScoreInputs) -> tuple[float, str, dict]:
    """Compute trust score from 5 components.

    Returns (trust_score_0_100, trust_label, components_dict).
    """
    # 1. Corroboration
    avg_auth = inputs.source_authority
    if inputs.cluster_articles:
        authorities = [
            getattr(a, "source_authority", inputs.source_authority) or inputs.source_authority
            for a in inputs.cluster_articles
        ]
        if authorities:
            avg_auth = sum(authorities) / len(authorities)
    c_corroboration = corroboration_trust_score(inputs.independent_sources, avg_auth)

    # 2. Official confirmation
    c_official, confirmation_level = official_confirmation_score(
        inputs.cluster_articles, inputs.primary_entity
    )

    # 3. Source trust
    c_source = source_trust_score(inputs.source_authority, inputs.is_primary_source)

    # 4. Claim quality
    c_quality, hedging, attribution, specificity = claim_quality_score(inputs.text)

    # 5. Primary document
    c_primary = 1.0 if has_primary_document(inputs.text, inputs.url) else 0.0

    # Weighted sum
    raw = (
        TRUST_WEIGHTS["corroboration"] * c_corroboration
        + TRUST_WEIGHTS["official_confirmation"] * c_official
        + TRUST_WEIGHTS["source_trust"] * c_source
        + TRUST_WEIGHTS["claim_quality"] * c_quality
        + TRUST_WEIGHTS["primary_document"] * c_primary
    )
    trust_score = round(min(100.0, raw * 100.0), 2)

    # Content-type floors
    if inputs.event_type == "RESEARCH_PAPER" and c_primary > 0:
        trust_score = max(trust_score, 65.0)
    if inputs.event_type == "OPEN_SOURCE_RELEASE" and c_primary > 0:
        trust_score = max(trust_score, 70.0)

    # Developing-story penalty for very recent first reports.
    hours_since_first_report = _hours_since_first_report(inputs.cluster_articles)
    is_still_developing = hours_since_first_report is not None and hours_since_first_report < 6
    if is_still_developing and hours_since_first_report < 2:
        trust_score = round(trust_score * 0.90, 2)

    # Determine label
    label = _determine_label(
        trust_score=trust_score,
        confirmation_level=confirmation_level,
        independent_sources=inputs.independent_sources,
        is_still_developing=is_still_developing,
        hours_since_first_report=hours_since_first_report,
        has_contradictory_sources=_has_contradictory_sources(inputs.cluster_articles),
    )

    # Components for tooltip
    components = {
        "corroboration": round(c_corroboration * 100, 1),
        "official_confirmation": round(c_official * 100, 1),
        "source_trust": round(c_source * 100, 1),
        "claim_quality": round(c_quality * 100, 1),
        "primary_document": round(c_primary * 100, 1),
        "confirmation_level": confirmation_level,
        "hedging_ratio": round(hedging, 3),
        "attribution_ratio": round(attribution, 3),
        "specificity_score": round(specificity, 3),
    }

    return trust_score, label, components


def _determine_label(
    trust_score: float,
    confirmation_level: str,
    independent_sources: int,
    is_still_developing: bool,
    hours_since_first_report: float | None,
    has_contradictory_sources: bool,
) -> str:
    """Assign trust label based on confirmation, score, and corroboration."""
    if has_contradictory_sources:
        return "disputed"

    if confirmation_level == "official":
        return "official"

    if trust_score >= 75 and independent_sources >= 3:
        return "confirmed"

    if trust_score >= 55 and independent_sources >= 2:
        return "likely"

    if is_still_developing and (hours_since_first_report or 999) < 6:
        return "developing"

    if independent_sources >= 2 and trust_score >= 40 and confirmation_level != "rumor":
        return "likely"

    if trust_score < 40:
        return "unverified"

    return "developing"


def _has_contradictory_sources(cluster_articles: list) -> bool:
    for art in cluster_articles:
        text = (getattr(art, "text", "") or "")[:2000]
        if not text:
            continue
        lowered = text.lower()
        if any(re.search(pattern, lowered) for pattern in CONTRADICTORY_PATTERNS):
            return True
    return False


def _hours_since_first_report(cluster_articles: list) -> float | None:
    if not cluster_articles:
        return None
    timestamps = []
    for art in cluster_articles:
        ts = getattr(art, "created_at", None)
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        timestamps.append(ts)
    if not timestamps:
        return None
    first = min(timestamps)
    now = datetime.now(timezone.utc)
    return max(0.0, (now - first).total_seconds() / 3600.0)
