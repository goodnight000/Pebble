from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlparse

from app.scoring.signals import is_official_source


SOURCE_ENTITY_HINTS = {
    "openai.com": "OpenAI",
    "anthropic.com": "Anthropic",
    "deepmind.google": "DeepMind",
    "research.google": "Google",
    "blog.google": "Google",
    "meta.com": "Meta",
    "ai.meta.com": "Meta",
    "microsoft.com": "Microsoft",
    "nvidia.com": "NVIDIA",
    "apple.com": "Apple",
    "amazon.science": "Amazon",
    "aws.amazon.com": "Amazon",
    "x.ai": "xAI",
    "mistral.ai": "Mistral",
    "cohere.com": "Cohere",
}

SOURCE_NAME_HINTS = {
    "OpenAI": "OpenAI",
    "Anthropic": "Anthropic",
    "DeepMind": "DeepMind",
    "Google": "Google",
    "Meta": "Meta",
    "Microsoft": "Microsoft",
    "NVIDIA": "NVIDIA",
    "Apple": "Apple",
    "Amazon": "Amazon",
    "AWS": "Amazon",
    "xAI": "xAI",
    "Mistral": "Mistral",
    "Cohere": "Cohere",
}

MODEL_ARTIFACT_PATTERNS = [
    re.compile(
        r"\b("
        r"(?:gpt|o\d|claude|gemini|grok|llama|qwen|deepseek|mistral|kimi|phi|nova|command)"
        r"[-\s]?\d+(?:\.\d+)*(?:\s+(?:pro|flash|mini|ultra|sonnet|opus|haiku|thinking|turbo|lite|nano|preview|instant|max))?"
        r")\b",
        re.I,
    ),
    re.compile(
        r"\b([A-Z][A-Za-z]+(?:[-\s]?[A-Za-z]+)?\s+\d+(?:\.\d+)*(?:\s+(?:Pro|Flash|Mini|Ultra|Sonnet|Opus|Haiku|Thinking|Turbo|Lite|Nano|Preview|Instant|Max))?)\b"
    ),
]

RELEASE_FRAMING_PATTERNS = [
    re.compile(r"\bintroducing\b", re.I),
    re.compile(r"\bavailable now\b", re.I),
    re.compile(r"\bstarting today\b", re.I),
    re.compile(r"\bmost capable\b", re.I),
    re.compile(r"\bmost intelligent\b", re.I),
    re.compile(r"\bfrontier model\b", re.I),
    re.compile(r"\bnew model\b", re.I),
    re.compile(r"\bstate-of-the-art\b", re.I),
]

MODEL_CAPABILITY_PATTERNS = [
    re.compile(r"\bmodel\b", re.I),
    re.compile(r"\bcoding\b", re.I),
    re.compile(r"\breasoning\b", re.I),
    re.compile(r"\btool use\b", re.I),
    re.compile(r"\bcomputer use\b", re.I),
    re.compile(r"\bcontext\b", re.I),
    re.compile(r"\btokens?\b", re.I),
    re.compile(r"\bmultimodal\b", re.I),
    re.compile(r"\bbenchmark\b", re.I),
]

SYSTEM_CARD_PATTERNS = [
    re.compile(r"\bsystem card\b", re.I),
    re.compile(r"system-card", re.I),
]

NON_RELEASE_PATTERNS = [
    re.compile(r"\beducation\b", re.I),
    re.compile(r"\bopportunity\b", re.I),
    re.compile(r"\blessons learned\b", re.I),
    re.compile(r"\bcase study\b", re.I),
    re.compile(r"\bpolicy\b", re.I),
]


@dataclass(frozen=True)
class OfficialReleaseAssessment:
    is_official_source: bool
    is_official_model_release: bool
    confidence: float
    artifact_name: str | None
    source_entity: str | None
    evidence_score: int


def infer_source_entity(source_name: str | None, url: str | None) -> str | None:
    host = (urlparse(url or "").hostname or "").lower()
    for domain, entity in SOURCE_ENTITY_HINTS.items():
        if host == domain or host.endswith("." + domain):
            return entity
    source_name = source_name or ""
    for hint, entity in SOURCE_NAME_HINTS.items():
        if hint.lower() in source_name.lower():
            return entity
    return None


def _extract_artifact_name(title: str, text: str, url: str) -> str | None:
    combined = " ".join(part for part in (title, url, text[:400]) if part)
    for pattern in MODEL_ARTIFACT_PATTERNS:
        match = pattern.search(combined)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()
    return None


def assess_official_model_release(
    *,
    title: str,
    text: str,
    url: str | None,
    source_name: str | None,
) -> OfficialReleaseAssessment:
    title = title or ""
    text = text or ""
    url = url or ""
    combined = " ".join(part for part in (title, text[:1200], url) if part)
    official = is_official_source(url)
    source_entity = infer_source_entity(source_name, url)
    artifact_name = _extract_artifact_name(title, text, url)
    release_hits = sum(1 for pattern in RELEASE_FRAMING_PATTERNS if pattern.search(combined))
    capability_hits = sum(1 for pattern in MODEL_CAPABILITY_PATTERNS if pattern.search(combined))
    system_card_hits = sum(1 for pattern in SYSTEM_CARD_PATTERNS if pattern.search(combined))
    non_release_hits = sum(1 for pattern in NON_RELEASE_PATTERNS if pattern.search(combined))

    evidence_score = 0
    if official:
        evidence_score += 3
    if artifact_name:
        evidence_score += 3
    if release_hits:
        evidence_score += 2
    if capability_hits >= 2:
        evidence_score += 2
    elif capability_hits == 1:
        evidence_score += 1
    if system_card_hits:
        evidence_score += 2
    if non_release_hits and not artifact_name:
        evidence_score -= 2

    is_release = bool(
        official
        and artifact_name
        and (
            system_card_hits
            or (release_hits >= 1 and capability_hits >= 2)
            or (release_hits >= 2 and capability_hits >= 1)
        )
    )
    confidence = max(0.0, min(1.0, evidence_score / 10.0))
    return OfficialReleaseAssessment(
        is_official_source=official,
        is_official_model_release=is_release,
        confidence=confidence,
        artifact_name=artifact_name,
        source_entity=source_entity,
        evidence_score=evidence_score,
    )
