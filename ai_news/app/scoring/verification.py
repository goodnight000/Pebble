"""Type-aware verification scoring with legacy trust compatibility."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlparse

from app.scoring.signals import clamp01, corroboration_score, is_official_source

COMMUNITY_SOURCE_KINDS = {"hn", "reddit", "twitter", "mastodon", "bluesky"}
COMMUNITY_HOSTS = {"news.ycombinator.com", "reddit.com", "www.reddit.com", "x.com", "twitter.com", "bsky.app"}
PREPRINT_HOSTS = {"arxiv.org", "www.arxiv.org", "ssrn.com", "www.ssrn.com", "biorxiv.org", "medrxiv.org"}
PUBLISHED_RESEARCH_HOSTS = {
    "doi.org",
    "dl.acm.org",
    "ieeexplore.ieee.org",
    "nature.com",
    "www.nature.com",
    "science.org",
    "www.science.org",
}
ARTIFACT_HOSTS = {"github.com", "www.github.com", "huggingface.co", "pypi.org", "npmjs.com", "crates.io"}

ANNOUNCEMENT_PATTERNS = [
    r"\bwe (?:are )?(?:launching|releasing|introducing|announcing|open-sourcing)\b",
    r"\btoday we (?:are )?(?:launching|releasing|introducing|announcing)\b",
    r"\b(?:press release|release notes|changelog)\b",
]
ANONYMOUS_SOURCE_PATTERNS = [
    r"\bpeople familiar with the matter\b",
    r"\bsources? say\b",
    r"\baccording to (?:people|sources|unnamed|anonymous)\b",
    r"\bmay be\b",
    r"\breportedly\b",
]
DIRECT_EVIDENCE_PATTERNS = [
    r"\baccording to (?:the company|the filing|court documents|the paper|the report)\b",
    r"\bin (?:a filing|court filing|SEC filing|paper|report)\b",
    r"\bthe repo\b",
    r"\bsource code\b",
    r"\bdocumentation\b",
]
CONTRADICTION_PATTERNS = [
    r"\b(?:denied|refuted|walked back|false|inaccurate|debunked)\b",
]
CORRECTION_PATTERNS = [
    r"^\s*(?:retraction|withdrawal)[:\-\s]",
    r"^\s*this (?:paper|article|post|announcement) (?:has been|was) (?:retracted|withdrawn)\b",
    r"^\s*we (?:are|have) (?:retracting|withdrawing)\b",
    r"^\s*correction[:\-\s]",
    r"^\s*this (?:paper|article|post|announcement) (?:has been|was) corrected\b",
    r"^\s*we (?:have )?updated .* to correct\b",
    r"^\s*update[:\-\s].*correct",
]
SPECIFICITY_PATTERNS = [
    r"\bversion \d",
    r"\b\d+(?:\.\d+)?%\b",
    r"\b\d+\s*(?:billion|million|GPU|GPUs|parameters?|tokens?)\b",
]


@dataclass
class VerificationInputs:
    cluster_articles: list = field(default_factory=list)
    source_authority: float = 0.0
    text: str = ""
    url: str = ""
    primary_entity: str | None = None
    independent_sources: int = 0
    event_type: str = "OTHER"
    source_kind: str = "rss"
    source_name: str = ""
    created_at: datetime | None = None


@dataclass
class VerificationResult:
    verification_mode: str
    verification_state: str
    freshness_state: str
    verification_confidence: float
    verification_signals: dict[str, Any]
    update_status: str
    canonical_evidence_url: str


def compute_verification(inputs: VerificationInputs) -> VerificationResult:
    mode = classify_verification_mode(inputs)
    freshness = derive_freshness_state(inputs)
    update_status = _detect_update_status(inputs.text)
    contradictory = _contains_any(inputs.text, CONTRADICTION_PATTERNS)

    if mode == "artifact":
        confidence, signals = _score_artifact(inputs)
        state = "verified_artifact" if confidence >= 60 else "community_signal"
    elif mode == "official_statement":
        confidence, signals = _score_official_statement(inputs)
        state = "official_statement"
    elif mode == "research_preprint":
        confidence, signals = _score_research(inputs, published=False)
        state = "verified_artifact" if confidence >= 60 else "single_source_report"
    elif mode == "research_published":
        confidence, signals = _score_research(inputs, published=True)
        state = "verified_artifact" if confidence >= 65 else "single_source_report"
    elif mode == "reported_news":
        confidence, signals = _score_reported_news(inputs)
        if contradictory:
            state = "disputed"
        elif inputs.independent_sources >= 2 and confidence >= 65:
            state = "corroborated_report"
        else:
            state = "single_source_report"
    else:
        confidence, signals = _score_community_post(inputs)
        state = "disputed" if contradictory else "community_signal"

    if update_status in {"corrected", "retracted"}:
        state = "corrected_or_retracted"
        confidence = min(confidence, 30.0 if update_status == "retracted" else 40.0)
    elif contradictory:
        state = "disputed"
        confidence = min(confidence, 35.0)

    return VerificationResult(
        verification_mode=mode,
        verification_state=state,
        freshness_state=freshness,
        verification_confidence=round(confidence, 2),
        verification_signals=signals,
        update_status=update_status,
        canonical_evidence_url=inputs.url,
    )


def classify_verification_mode(inputs: VerificationInputs) -> str:
    host = _host(inputs.url)
    if host in PREPRINT_HOSTS:
        return "research_preprint"
    if host in PUBLISHED_RESEARCH_HOSTS or host == "doi.org":
        return "research_published"
    if _is_artifact_url(inputs.url):
        return "artifact"
    if is_official_source(inputs.url):
        return "official_statement"
    if inputs.source_kind in COMMUNITY_SOURCE_KINDS or host in COMMUNITY_HOSTS:
        return "community_post"
    return "reported_news"


def derive_freshness_state(inputs: VerificationInputs) -> str:
    age_hours = _age_hours(inputs)
    if age_hours < 6:
        return "fresh"
    if age_hours < 24:
        return "maturing"
    return "stable"


def legacy_trust_label_for_state(
    verification_state: str | None,
    verification_confidence: float | None = None,
) -> str | None:
    mapping = {
        "official_statement": "official",
        "corroborated_report": "confirmed",
        "community_signal": "unverified",
        "disputed": "disputed",
        "corrected_or_retracted": "disputed",
    }
    if verification_state == "verified_artifact":
        return "confirmed" if (verification_confidence or 0) >= 75 else "likely"
    if verification_state == "single_source_report":
        return "likely" if (verification_confidence or 0) >= 70 else "unverified"
    return mapping.get(verification_state)


def legacy_trust_components(result: VerificationResult, text: str) -> dict[str, Any]:
    corroboration = _signal(result.verification_signals, "external_corroboration", "corroboration_independence")
    source_trust = _signal(
        result.verification_signals,
        "identity_authenticity",
        "poster_authenticity",
        "publisher_reliability",
        "paper_identity",
        "document_identity",
    )
    claim_quality = _signal(
        result.verification_signals,
        "claim_alignment",
        "attribution_quality",
        "direct_evidence_strength",
        "document_existence",
    )
    primary_document = 100.0 if result.verification_mode in {
        "artifact",
        "research_preprint",
        "research_published",
        "official_statement",
    } else 0.0
    confirmation_level = "official" if result.verification_state == "official_statement" else (
        "attributed" if result.verification_state in {"verified_artifact", "corroborated_report"} else "rumor"
    )

    sample = (text or "").lower()[:5000]
    sentence_count = max(1, len([s for s in re.split(r"[.!?]+", sample) if s.strip()]))
    hedging_count = sum(1 for pattern in ANONYMOUS_SOURCE_PATTERNS if re.search(pattern, sample, re.IGNORECASE))
    attribution_count = sum(1 for pattern in DIRECT_EVIDENCE_PATTERNS if re.search(pattern, sample, re.IGNORECASE))
    specificity_count = sum(1 for pattern in SPECIFICITY_PATTERNS if re.search(pattern, sample, re.IGNORECASE))

    return {
        "corroboration": round(corroboration, 1),
        "official_confirmation": 100.0 if confirmation_level == "official" else (65.0 if confirmation_level == "attributed" else 15.0),
        "source_trust": round(source_trust, 1),
        "claim_quality": round(claim_quality, 1),
        "primary_document": primary_document,
        "confirmation_level": confirmation_level,
        "hedging_ratio": round(min(1.0, hedging_count / sentence_count), 3),
        "attribution_ratio": round(min(1.0, attribution_count / sentence_count), 3),
        "specificity_score": round(min(1.0, specificity_count / 3.0), 3),
        "verification_mode": result.verification_mode,
        "verification_state": result.verification_state,
        "freshness_state": result.freshness_state,
    }


def _score_artifact(inputs: VerificationInputs) -> tuple[float, dict[str, float]]:
    host = _host(inputs.url)
    path = urlparse(inputs.url).path
    identity = 1.0 if is_official_source(inputs.url) else max(0.68, clamp01(inputs.source_authority) * 0.9 + 0.15)
    direct = 1.0
    integrity = 0.85 if "/releases" in path or host in {"pypi.org", "npmjs.com", "crates.io"} else 0.68
    if host == "huggingface.co":
        integrity = max(integrity, 0.75)
    alignment = 0.75 + (0.15 if _contains_any(inputs.text, DIRECT_EVIDENCE_PATTERNS + ANNOUNCEMENT_PATTERNS) else 0.0)
    corroboration = corroboration_score(inputs.independent_sources)
    confidence = 100.0 * (
        0.30 * identity
        + 0.35 * direct
        + 0.20 * integrity
        + 0.10 * clamp01(alignment)
        + 0.05 * corroboration
    )
    return confidence, {
        "identity_authenticity": round(identity * 100, 1),
        "direct_evidence_strength": round(direct * 100, 1),
        "artifact_integrity": round(integrity * 100, 1),
        "claim_alignment": round(clamp01(alignment) * 100, 1),
        "external_corroboration": round(corroboration * 100, 1),
    }


def _score_official_statement(inputs: VerificationInputs) -> tuple[float, dict[str, float]]:
    announcement = _contains_any(inputs.text, ANNOUNCEMENT_PATTERNS)
    identity = 1.0 if is_official_source(inputs.url) else clamp01(inputs.source_authority)
    direct = 0.92 if announcement else 0.76
    alignment = 0.88 if announcement else 0.72
    corroboration = corroboration_score(inputs.independent_sources)
    update = 1.0
    confidence = 100.0 * (
        0.35 * identity
        + 0.30 * direct
        + 0.20 * alignment
        + 0.10 * corroboration
        + 0.05 * update
    )
    return confidence, {
        "identity_authenticity": round(identity * 100, 1),
        "direct_evidence_strength": round(direct * 100, 1),
        "claim_alignment": round(alignment * 100, 1),
        "external_corroboration": round(corroboration * 100, 1),
        "update_status": round(update * 100, 1),
    }


def _score_research(inputs: VerificationInputs, *, published: bool) -> tuple[float, dict[str, float]]:
    exists = 1.0
    identity = 0.78 if published else 0.68
    artifacts = 0.75 if _contains_any(inputs.text, [r"\bcode\b", r"\bdataset\b", r"\brepo\b", r"\bgithub\b"]) else 0.45
    alignment = 0.78 if _contains_any(inputs.text, [r"\bpaper\b", r"\babstract\b", r"\bexperiments?\b", r"\bresults?\b"]) else 0.62
    corroboration = corroboration_score(inputs.independent_sources)
    update = 1.0
    confidence = 100.0 * (
        (0.20 if published else 0.20) * identity
        + (0.25 if not published else 0.20) * exists
        + 0.15 * artifacts
        + 0.15 * alignment
        + (0.10 if not published else 0.15) * corroboration
        + (0.15 if published else 0.15) * update
    )
    if not published:
        confidence = min(confidence, 79.0)
    return confidence, {
        ("document_identity" if published else "paper_identity"): round(identity * 100, 1),
        ("publisher_or_venue_strength" if published else "document_existence"): round(exists * 100, 1),
        "supporting_artifacts": round(artifacts * 100, 1),
        "claim_alignment": round(alignment * 100, 1),
        "external_corroboration": round(corroboration * 100, 1),
        "update_status": round(update * 100, 1),
    }


def _score_reported_news(inputs: VerificationInputs) -> tuple[float, dict[str, float]]:
    anonymous = _contains_any(inputs.text, ANONYMOUS_SOURCE_PATTERNS)
    direct_evidence = _contains_any(inputs.text, DIRECT_EVIDENCE_PATTERNS)
    contradiction = _contains_any(inputs.text, CONTRADICTION_PATTERNS)
    specificity = _contains_any(inputs.text, SPECIFICITY_PATTERNS)

    attribution = 0.35 if anonymous else 0.8
    direct = 0.35 if anonymous and not direct_evidence else (0.8 if direct_evidence else 0.55)
    corroboration = corroboration_score(inputs.independent_sources)
    publisher = clamp01(inputs.source_authority)
    alignment = 0.78 if specificity else 0.62
    contradiction_penalty = 1.0 if contradiction else 0.0

    confidence = 100.0 * (
        0.25 * attribution
        + 0.25 * direct
        + 0.25 * corroboration
        + 0.10 * publisher
        + 0.10 * alignment
        + 0.05 * (1.0 - contradiction_penalty)
    )
    return confidence, {
        "attribution_quality": round(attribution * 100, 1),
        "direct_evidence_strength": round(direct * 100, 1),
        "corroboration_independence": round(corroboration * 100, 1),
        "publisher_reliability": round(publisher * 100, 1),
        "claim_alignment": round(alignment * 100, 1),
        "contradiction_penalty": round(contradiction_penalty * 100, 1),
    }


def _score_community_post(inputs: VerificationInputs) -> tuple[float, dict[str, float]]:
    rumor = _contains_any(inputs.text, ANONYMOUS_SOURCE_PATTERNS)
    poster = clamp01(inputs.source_authority)
    linked = 0.15 if _host(inputs.url) in COMMUNITY_HOSTS else 0.45
    corroboration = corroboration_score(inputs.independent_sources) * 0.6
    provenance = 0.25 if inputs.source_kind in COMMUNITY_SOURCE_KINDS else 0.4
    contradiction_penalty = 0.25 if rumor else 0.0
    confidence = 100.0 * (
        0.20 * poster
        + 0.35 * linked
        + 0.20 * corroboration
        + 0.10 * provenance
        + 0.15 * (1.0 - contradiction_penalty)
    )
    return min(confidence, 69.0), {
        "poster_authenticity": round(poster * 100, 1),
        "linked_evidence_strength": round(linked * 100, 1),
        "external_corroboration": round(corroboration * 100, 1),
        "provenance": round(provenance * 100, 1),
        "contradiction_penalty": round(contradiction_penalty * 100, 1),
    }


def _signal(signals: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = signals.get(key)
        if value is not None:
            return float(value)
    return 0.0


def _contains_any(text: str, patterns: list[str]) -> bool:
    sample = (text or "").lower()[:5000]
    return any(re.search(pattern, sample, re.IGNORECASE) for pattern in patterns)


def _detect_update_status(text: str) -> str:
    sample = (text or "").lower()[:400]
    if any(re.search(pattern, sample, re.IGNORECASE) for pattern in CORRECTION_PATTERNS[:3]):
        return "retracted"
    if any(re.search(pattern, sample, re.IGNORECASE) for pattern in CORRECTION_PATTERNS[3:]):
        return "corrected"
    return "active"


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _is_artifact_url(url: str) -> bool:
    host = _host(url)
    path = [segment for segment in urlparse(url).path.split("/") if segment]
    if host in {"github.com", "www.github.com"}:
        return len(path) >= 2 and path[0] not in {"topics", "orgs", "explore", "sponsors"}
    if host == "huggingface.co":
        return len(path) >= 2 and path[0] not in {"docs", "blog", "spaces"}
    return host in ARTIFACT_HOSTS


def _age_hours(inputs: VerificationInputs) -> float:
    now = datetime.now(timezone.utc)
    timestamps: list[datetime] = []
    if inputs.created_at:
        timestamps.append(_ensure_utc(inputs.created_at))
    for article in inputs.cluster_articles:
        created_at = getattr(article, "created_at", None)
        if created_at:
            timestamps.append(_ensure_utc(created_at))
    if not timestamps:
        return 0.0
    first_seen = min(timestamps)
    return max(0.0, (now - first_seen).total_seconds() / 3600.0)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
