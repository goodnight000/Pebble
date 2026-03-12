from __future__ import annotations

EVENT_TYPES = [
    "MODEL_RELEASE",
    "CHIP_HARDWARE",
    "BIG_TECH_ANNOUNCEMENT",
    "STARTUP_FUNDING",
    "M_AND_A",
    "OPEN_SOURCE_RELEASE",
    "RESEARCH_PAPER",
    "BENCHMARK_RESULT",
    "SECURITY_INCIDENT",
    "POLICY_REGULATION",
    "PRODUCT_LAUNCH",
    "OTHER",
]

TOPICS = [
    "llms",
    "multimodal",
    "agents",
    "robotics",
    "vision",
    "audio_speech",
    "hardware_chips",
    "open_source",
    "startups_funding",
    "enterprise_apps",
    "safety_policy",
    "research_methods",
]


CLASSIFY_PROMPT = """
You are a classifier. Return JSON only with keys: event_type, topics.
- event_type must be one of: {event_types}
- topics is a map from topic to probability (0..1) for each topic in: {topics}
Input text:
{text}
"""

SUMMARY_PROMPT = """
Summarize the following text in <= 600 characters. Be factual and concise.
Text:
{text}
"""

SIGNIFICANCE_JUDGE_PROMPT = '''You are an AI news significance evaluator. Rate this article on three dimensions (each 0-100):

**Impact**: How much will this affect the AI field, industry, or society?
- 90-100: Paradigm shift (new SOTA model, major regulation, >$1B deal)
- 70-89: Significant advancement or major corporate move
- 50-69: Notable but incremental progress
- 30-49: Minor update or niche interest
- 0-29: Trivial or routine

**Breadth**: How many people/organizations does this affect?
- 90-100: Entire AI industry or general public
- 70-89: Multiple major organizations or a large community
- 50-69: A specific sector or moderate community
- 30-49: A niche group
- 0-29: Very few people

**Novelty**: How new/surprising is this information?
- 90-100: Completely unexpected, no prior signals
- 70-89: Significant new information
- 50-69: Expected but now confirmed
- 30-49: Incremental update to known story
- 0-29: Already widely known

Article:
Title: {title}
Source: {source_name}
Type: {event_type}
Preview: {text_preview}

Respond with ONLY a JSON object:
{{"impact": <int>, "breadth": <int>, "novelty": <int>}}'''
