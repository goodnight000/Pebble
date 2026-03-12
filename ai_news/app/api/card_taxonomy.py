from __future__ import annotations

import re
from typing import Dict, Iterable, List, Literal


Category = Literal[
    "Research",
    "Product",
    "Company",
    "Funding",
    "Policy",
    "Open Source",
    "Hardware",
    "Security",
    "General",
]


EVENT_CATEGORY: Dict[str, Category] = {
    "RESEARCH_PAPER": "Research",
    "BENCHMARK_RESULT": "Research",
    "MODEL_RELEASE": "Product",
    "PRODUCT_LAUNCH": "Product",
    "BIG_TECH_ANNOUNCEMENT": "Company",
    "M_AND_A": "Company",
    "STARTUP_FUNDING": "Funding",
    "POLICY_REGULATION": "Policy",
    "GOVERNMENT_ACTION": "Policy",
    "OPEN_SOURCE_RELEASE": "Open Source",
    "CHIP_HARDWARE": "Hardware",
    "SECURITY_INCIDENT": "Security",
}


CATEGORY_PRIORITY: List[Category] = [
    "Product",
    "Company",
    "Funding",
    "Open Source",
    "Hardware",
    "Security",
    "Policy",
    "Research",
    "General",
]


INTERNAL_TOPIC_CHIPS: Dict[str, tuple[str, ...]] = {
    "llms": ("LLMs",),
    "multimodal": ("Multimodal",),
    "agents": ("Agents",),
    "robotics": ("Robotics",),
    "vision": ("Vision",),
    "audio_speech": ("Speech",),
    "hardware_chips": ("Hardware", "Infrastructure"),
    "open_source": ("Open Source", "Developer Tools"),
    "enterprise_apps": ("Enterprise",),
    "safety_policy": ("Governance",),
    "research_methods": ("Science",),
}


KEYWORD_RULES: List[tuple[str, str, re.Pattern[str]]] = [
    ("Healthcare", "core", re.compile(r"\b(clinical|diagnostic|patient|hospital|medical|healthcare|physician|doctor)\b", re.I)),
    ("Biotech", "core", re.compile(r"\b(biotech|biology|genomics|protein|drug discovery|molecular)\b", re.I)),
    ("Security", "core", re.compile(r"\b(security|privacy|cyber|vulnerability|exploit|malware|breach|red team)\b", re.I)),
    ("Hardware", "core", re.compile(r"\b(gpu|tpu|chip|chips|accelerator|semiconductor|hbm|silicon)\b", re.I)),
    ("Infrastructure", "context", re.compile(r"\b(inference|training cluster|data center|serving|deployment|infrastructure|compute)\b", re.I)),
    ("LLMs", "core", re.compile(r"\b(llm|llms|language model|foundation model|chatbot)\b", re.I)),
    ("Multimodal", "core", re.compile(r"\b(multimodal|vision-language|text-to-image|image generation|text-to-video)\b", re.I)),
    ("Agents", "core", re.compile(r"\b(agent|agents|agentic|tool use|workflow automation|orchestrat)\b", re.I)),
    ("Robotics", "core", re.compile(r"\b(robot|robots|robotics|embodied|manipulation|autonomous system)\b", re.I)),
    ("Vision", "core", re.compile(r"\b(vision|image|camera|ocr|object detection|visual)\b", re.I)),
    ("Speech", "core", re.compile(r"\b(speech|voice|audio|transcription|tts|asr)\b", re.I)),
    ("Video", "core", re.compile(r"\b(video|film|clip|editing)\b", re.I)),
    ("Coding", "core", re.compile(r"\b(coding|code|coder|programming|software engineer|pull request|repo)\b", re.I)),
    ("Developer Tools", "context", re.compile(r"\b(sdk|framework|cli|developer|devtool|testing|eval harness|repository|workflow)\b", re.I)),
    ("Enterprise", "context", re.compile(r"\b(enterprise|business|workplace|customer service|crm|productivity|saas)\b", re.I)),
    ("Consumer", "context", re.compile(r"\b(consumer|shopping|creator|wearable|assistant app|everyday)\b", re.I)),
    ("Science", "context", re.compile(r"\b(research|study|paper|benchmark|dataset|experiment|trial|evaluation)\b", re.I)),
    ("Education", "context", re.compile(r"\b(education|student|teacher|classroom|learning)\b", re.I)),
    ("Governance", "context", re.compile(r"\b(governance|policy|regulation|compliance|law|guidance|government)\b", re.I)),
]


CHIP_SORT_ORDER: Dict[str, int] = {
    "Healthcare": 0,
    "Biotech": 1,
    "Security": 2,
    "Hardware": 3,
    "Infrastructure": 4,
    "LLMs": 5,
    "Multimodal": 6,
    "Agents": 7,
    "Robotics": 8,
    "Vision": 9,
    "Speech": 10,
    "Video": 11,
    "Coding": 12,
    "Open Source": 13,
    "Developer Tools": 14,
    "Science": 15,
    "Enterprise": 16,
    "Consumer": 17,
    "Education": 18,
    "Governance": 19,
}


SUPPRESSED_CHIPS_BY_CATEGORY: Dict[Category, set[str]] = {
    "Open Source": {"Open Source"},
    "Hardware": {"Hardware"},
    "Security": {"Security"},
}


def category_for(event_type: str, topics: Dict[str, float] | None) -> Category:
    if event_type in EVENT_CATEGORY:
        return EVENT_CATEGORY[event_type]

    topics = topics or {}
    ranked = sorted(topics.items(), key=lambda kv: kv[1], reverse=True)
    for topic, score in ranked:
        if score < 0.35:
            continue
        if topic == "research_methods":
            return "Research"
        if topic == "open_source":
            return "Open Source"
        if topic == "hardware_chips":
            return "Hardware"
        if topic == "startups_funding":
            return "Funding"
        if topic == "safety_policy":
            return "Policy"

    if any(topics.get(topic, 0.0) >= 0.42 for topic in ("llms", "multimodal", "agents", "robotics", "vision", "audio_speech", "enterprise_apps")):
        return "Product"

    return "General"


def _seed_from_event_type(event_type: str) -> tuple[list[str], list[str]]:
    core: list[str] = []
    context: list[str] = []

    if event_type in {"RESEARCH_PAPER", "BENCHMARK_RESULT"}:
        context.append("Science")
    if event_type == "OPEN_SOURCE_RELEASE":
        core.extend(["Open Source", "Developer Tools"])
    if event_type == "CHIP_HARDWARE":
        core.extend(["Hardware", "Infrastructure"])
    if event_type == "SECURITY_INCIDENT":
        core.append("Security")
    if event_type in {"POLICY_REGULATION", "GOVERNMENT_ACTION"}:
        context.append("Governance")

    return core, context


def _ordered_topic_items(topics: Dict[str, float] | None) -> Iterable[tuple[str, float]]:
    normalized = topics or {}
    return sorted(normalized.items(), key=lambda kv: kv[1], reverse=True)


def build_topic_chips(
    category: Category,
    event_type: str,
    topics: Dict[str, float] | None,
    *,
    title: str,
    summary: str | None = None,
    source_name: str | None = None,
    limit: int = 4,
) -> List[str]:
    core, context = _seed_from_event_type(event_type)
    text = " ".join(part for part in (title, summary or "", source_name or "") if part)

    for chip, bucket, pattern in KEYWORD_RULES:
        if pattern.search(text):
            if bucket == "core":
                core.append(chip)
            else:
                context.append(chip)

    for topic, score in _ordered_topic_items(topics):
        if score < 0.25:
            continue
        chips = INTERNAL_TOPIC_CHIPS.get(topic, ())
        for chip in chips:
            if chip in {"Developer Tools", "Enterprise", "Consumer", "Science", "Education", "Governance", "Infrastructure"}:
                context.append(chip)
            else:
                core.append(chip)

    hidden_equivalents = SUPPRESSED_CHIPS_BY_CATEGORY.get(category, set())
    merged: list[str] = []
    seen: set[str] = set()

    for chip in sorted(core, key=lambda value: CHIP_SORT_ORDER.get(value, 999)):
        if chip in hidden_equivalents or chip in seen:
            continue
        seen.add(chip)
        merged.append(chip)

    for chip in sorted(context, key=lambda value: CHIP_SORT_ORDER.get(value, 999)):
        if chip in hidden_equivalents or chip in seen:
            continue
        seen.add(chip)
        merged.append(chip)

    return merged[:limit]
