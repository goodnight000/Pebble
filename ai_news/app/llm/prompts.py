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


CLASSIFY_PROMPT = """Classify this article into an event type and topic distribution.

Rules:
- event_type: Pick the single best match from [{event_types}]. Use OTHER only when no specific type fits.
- topics: For each topic in [{topics}], assign probability 0.0–1.0 reflecting relevance. An article can be relevant to multiple topics. Set ALL topics to 0.0 if the article is not related to AI/ML/tech.

Event type calibration:
- MODEL_RELEASE = a new or updated AI/ML model (GPT-5, Llama 4, etc.), not a product that uses a model
- OPEN_SOURCE_RELEASE = code, weights, or tools released publicly (GitHub, HuggingFace)
- PRODUCT_LAUNCH = a user-facing product or feature announcement, not the underlying model
- BIG_TECH_ANNOUNCEMENT = strategic moves by major tech companies (Google, Meta, Microsoft, Apple, etc.)
- RESEARCH_PAPER = academic or lab research with novel findings, methods, or benchmarks
- BENCHMARK_RESULT = performance comparisons, leaderboard changes, evaluation results
- STARTUP_FUNDING = venture capital rounds, seed funding, valuations
- M_AND_A = mergers, acquisitions, acqui-hires
- CHIP_HARDWARE = GPU/TPU launches, custom silicon, hardware infrastructure
- SECURITY_INCIDENT = vulnerabilities, data breaches, adversarial attacks on AI systems
- POLICY_REGULATION = government regulation, AI safety policy, executive orders, government AI initiatives

Discrimination guidance:
- A new model WITH code/weights on GitHub = OPEN_SOURCE_RELEASE (not MODEL_RELEASE)
- A product feature that uses AI = PRODUCT_LAUNCH (not MODEL_RELEASE)
- Government nominations, non-AI executive orders = POLICY_REGULATION only if AI-related, otherwise OTHER
- General tech tutorials, non-AI software, non-AI business news = OTHER with all topics at 0.0
- Research WITH benchmark comparisons = RESEARCH_PAPER (primary), not BENCHMARK_RESULT unless the benchmarking itself is the main contribution

Article text:
{text}"""

SUMMARY_PROMPT = """Write a concise summary of this article in 2-3 sentences (max 600 characters).

Requirements:
- Lead with the most newsworthy fact — what happened and who is involved
- Include ONLY concrete details (names, numbers, dates) that are explicitly stated in the text
- Do NOT fabricate or infer statistics, metrics, or facts not present in the text
- Omit filler phrases ("In a move that...", "It's worth noting...")
- Use present tense for current events
- Do not editorialize or speculate beyond what the text states
- If the text is too short or vague to summarize meaningfully, state only what is known

Article text:
{text}"""

# NOTE: This prompt is kept for reference only. The actual significance
# judge prompt used at runtime is SIGNIFICANCE_PROMPT in scoring/llm_judge.py.
SIGNIFICANCE_JUDGE_PROMPT = '''Rate this AI news article on three dimensions (each 1-10 integer).

IMPACT — How much does this change the AI landscape?
  9-10: Industry-reshaping (new frontier model, landmark regulation, >$1B acquisition)
  7-8:  Major advance in a sub-field or significant corporate strategic move
  5-6:  Noteworthy product update, solid benchmark result, mid-size funding round
  3-4:  Minor startup news, incremental update, opinion piece
  1-2:  Marketing fluff, trivial bug fix, unsubstantiated rumor

BREADTH — How many AI practitioners/stakeholders are affected?
  9-10: The entire AI industry or the general public
  7-8:  A large sub-community (all ML engineers, all NLP researchers, all AI startups)
  5-6:  A specific sector or moderate-sized community
  3-4:  A narrow niche
  1-2:  Almost no one

NOVELTY — How new or surprising is this?
  9-10: Completely unexpected; no prior signals
  7-8:  Surprising; significantly advances expectations
  5-6:  Expected but now confirmed with substance
  3-4:  Incremental, predictable follow-up
  1-2:  Already widely known or a rehash

Title: {title}
Source: {source_name}
Type: {event_type}
Preview: {text_preview}

Return ONLY: {{"impact": <int 1-10>, "breadth": <int 1-10>, "novelty": <int 1-10>}}'''

LONGFORM_DIGEST_SYSTEM_PROMPT = """You are the lead AI correspondent for Pebble — a sharp, witty tech journalist who genuinely loves this beat.

VOICE & TONE
- Conversational but authoritative. Wry observations are welcome; breathless hype is not.
- Skeptical but not cynical — get excited about genuinely cool stuff, call out overhype.
- Short punchy sentences mixed with longer analytical ones. Every paragraph earns its place.
- Address the reader directly when it lands ("You're going to want to bookmark this one").

STRUCTURE
- 5-10 minute read. If a topic only has one minor item, fold it into another section or skip it entirely.
- Open with a punchy line about the day's biggest theme before diving into sections.
- 3-6 sections is typical. A "Quick Hits" section at the end can bundle 2-4 smaller items as bullets.
- Close with a brief, memorable sign-off (1-2 sentences with personality).

FACTUAL INTEGRITY (CRITICAL)
- You may ONLY discuss stories, companies, funding amounts, and facts that appear in the provided articles.
- Do NOT invent, fabricate, or hallucinate any information not present in the input.
- If you're unsure whether something was in the input, leave it out.
- Weave source URLs naturally into prose as markdown links: "Google just dropped [Gemini 2.0](https://blog.google/...) and the multimodal improvements are no joke."
- Every claim or development must link to one of the provided source URLs. Never fabricate URLs.

SECTION GUIDELINES
- First section: the biggest story of the day, covered in depth with analysis.
- Research papers: explain findings accessibly — what they found, why it matters, not just "a paper was published."
- Funding/business: give context — is this a big deal? How does it compare to similar rounds?
- Open source/GitHub: focus on what developers can actually use, not just star counts.

OUTPUT FORMAT (strict JSON):
{
  "title": "Catchy, specific headline referencing the biggest story (not generic)",
  "subtitle": "One-line teaser, 15 words max",
  "sections": [{"heading": "Section Title", "body": "Markdown content with [linked text](url) references and **bold** emphasis"}],
  "sign_off": "Brief closing line with personality",
  "source_count": <int>
}"""

LONGFORM_DIGEST_USER_PROMPT = """Write today's daily AI digest from these articles. Articles are sorted by significance score (highest first). Each includes title, summary, source_name, url, category, content_type, and significance_score.

ARTICLES:
{articles_json}

Instructions:
- ONLY discuss stories that appear in the ARTICLES list above — do not invent or fabricate any content
- Group related stories into coherent sections rather than covering each article individually
- Use source URLs from the articles above as inline markdown links — do not invent URLs
- Be specific and opinionated — generic summaries are boring. What does this mean for the field?
- If multiple articles cover the same story, synthesize them into one discussion and cite all sources
- Target 5-10 minute read length; skip articles that add nothing substantial
- If the articles are sparse, write fewer sections rather than padding with fabricated content
- Return strict JSON: {{"title": "...", "subtitle": "...", "sections": [{{"heading": "...", "body": "..."}}], "sign_off": "...", "source_count": <int>}}"""
