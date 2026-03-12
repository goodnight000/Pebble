# Algorithm Design: Importance Score + Trust Score

This document defines the two core scoring algorithms for AIPulse: the importance score (how significant is this news?) and the trust score (how reliable is this information?).

---

## Part 1: Importance Score (0-100)

### Architecture: Three-Stage Cascade

```
Stage 1: Pre-Score (cheap, title-only)
    → Runs on ALL ingested items
    → Purpose: decide what's worth scraping
    → Items scoring ≥ 40 proceed to Stage 2

Stage 2: Rule-Based Global Score (after full scrape + feature extraction)
    → Runs on all scraped articles
    → Purpose: objective significance ranking
    → Top ~50 items/day proceed to Stage 3

Stage 3: LLM Judge (semantic significance assessment)
    → Runs on top candidates only
    → Purpose: catch nuance that formulas miss
    → Final score = blend of Stage 2 + Stage 3
```

---

### Stage 1: Pre-Score (0-100)

Lightweight filter that runs on title + metadata only, before full content scraping.

**Formula:**

```python
pre_score = 100 * clamp01(
    0.35 * source_authority
    + 0.30 * ai_relevance          # embedding similarity to AI topic anchors
    + 0.20 * keyword_score          # presence of signal keywords in title
    + 0.15 * social_score           # log-normalized HN/Reddit/GitHub signals
)
```

**Scrape decision:**

| Pre-Score | Decision | Reason |
|---|---|---|
| ≥ 70 | `fetch_full_priority` | High confidence this matters |
| ≥ 40 | `fetch_full` | Worth investigating |
| < 40 | `skip` | Likely noise, store headline only |

**Override rules:**
- `source.always_scrape = true` → always `fetch_full` regardless of score
- AI relevance ≥ 0.75 AND title contains release/launch/acquire/announce keywords → force `fetch_full`

---

### Stage 2: Rule-Based Global Score (0-100)

Runs after full article content is scraped, features are extracted, and the article is assigned to a cluster.

#### Input Signals

**Signal 1: Entity Prominence (weight: 0.15)**

Who is the story about? Stories about frontier AI labs score higher than unknown startups.

```python
ENTITY_TIERS = {
    # Tier 1: Frontier labs (0.95-1.0)
    "OpenAI": 1.0, "Google": 0.98, "DeepMind": 0.98,
    "Anthropic": 0.97, "Meta": 0.96, "Microsoft": 0.95,

    # Tier 2: Major players (0.80-0.94)
    "NVIDIA": 0.92, "Apple": 0.90, "Amazon": 0.88,
    "Mistral": 0.85, "xAI": 0.85, "Hugging Face": 0.85,
    "Cohere": 0.82, "Stability AI": 0.82,

    # Tier 3: Notable (0.60-0.79)
    "AMD": 0.75, "Intel": 0.72, "Together AI": 0.70,

    # Default for unrecognized entities
    "_default": 0.40,
}

def entity_prominence_score(entities: dict) -> float:
    """Score based on the most prominent entity in the article."""
    if not entities:
        return 0.3
    max_prominence = 0.0
    for entity, frequency_weight in entities.items():
        tier = ENTITY_TIERS.get(entity, ENTITY_TIERS["_default"])
        prominence = tier * min(frequency_weight, 1.0)
        max_prominence = max(max_prominence, prominence)
    return max_prominence
```

**Signal 2: Event Impact (weight: 0.15)**

Fixed importance ceiling per event type.

```python
EVENT_IMPACT = {
    "MODEL_RELEASE":          1.00,
    "CHIP_HARDWARE":          0.95,
    "SECURITY_INCIDENT":      0.90,
    "BIG_TECH_ANNOUNCEMENT":  0.85,
    "POLICY_REGULATION":      0.80,
    "M_AND_A":                0.80,
    "STARTUP_FUNDING":        0.70,
    "OPEN_SOURCE_RELEASE":    0.70,
    "BENCHMARK_RESULT":       0.65,
    "RESEARCH_PAPER":         0.60,
    "PRODUCT_LAUNCH":         0.60,
    "GOVERNMENT_ACTION":      0.80,   # NEW: executive orders, regulatory actions
    "OTHER":                  0.40,
}
```

**Signal 3: Source Authority (weight: 0.12)**

Direct from config, 0.0 to 1.0. OpenAI blog = 1.0, TechCrunch = 0.85, Reddit = 0.60.

```python
def authority_score(authority: float) -> float:
    return clamp01(authority)
```

**Signal 4: Corroboration (weight: 0.12)**

How many independent sources cover this story? Uses Wilson confidence interval rather than raw log-norm for statistical rigor at low counts.

```python
def corroboration_score(independent_sources: int) -> float:
    """Wilson-inspired confidence: accounts for uncertainty at low N."""
    if independent_sources <= 0:
        return 0.0
    p = min(independent_sources / 8.0, 1.0)
    z = 1.64  # 90% confidence
    n = max(independent_sources, 1)
    lower = (p + z*z/(2*n) - z * math.sqrt((p*(1-p) + z*z/(4*n)) / n)) / (1 + z*z/n)
    return max(0.0, lower)
```

**Signal 5: Social Velocity (weight: 0.10)**

Points *per hour*, not just total points. 100 HN points in 1 hour is more significant than 100 points in 24 hours.

```python
def social_velocity_score(raw: RawItem, age_hours: float) -> float:
    """Engagement rate across platforms, combined (not max)."""
    hn_velocity = (raw.social_hn_points or 0) / max(age_hours, 0.1)
    reddit_velocity = (raw.social_reddit_upvotes or 0) / max(age_hours, 0.1)
    github_velocity = (raw.social_github_stars or 0) / max(age_hours, 0.1)

    # Normalize per platform, then combine with diminishing returns
    hn_norm = log_norm(hn_velocity, 200)       # 200 pts/hr = viral on HN
    reddit_norm = log_norm(reddit_velocity, 500)
    github_norm = log_norm(github_velocity, 100)

    # Weighted combination (not max — captures cross-platform signal)
    combined = 0.45 * hn_norm + 0.30 * reddit_norm + 0.25 * github_norm
    return clamp01(combined)
```

**Signal 6: Cluster Velocity (weight: 0.08)**

How fast is this story accumulating coverage? A story going from 1 to 10 articles in 2 hours is breaking news.

```python
def cluster_velocity_score(cluster) -> float:
    if not cluster or cluster.coverage_count <= 1:
        return 0.0
    span_hours = max(
        (cluster.last_seen_at - cluster.first_seen_at).total_seconds() / 3600,
        0.1
    )
    velocity = (cluster.coverage_count - 1) / span_hours
    return log_norm(velocity, 10.0)  # 10 articles/hour = max
```

**Signal 7: Novelty (weight: 0.08)**

Inverse similarity to recent *high-scoring* articles. Being a duplicate of important news is worse than duplicating noise.

```python
def improved_novelty_score(
    embedding: np.ndarray,
    recent_embeddings: np.ndarray,
    recent_scores: np.ndarray,
) -> float:
    if recent_embeddings.shape[0] == 0:
        return 1.0
    similarities = recent_embeddings @ embedding
    # Weight by score: duplicating a 90-score article is worse than duplicating a 30-score
    score_weights = recent_scores / 100.0
    weighted_sim = similarities * score_weights
    max_weighted_sim = float(np.max(weighted_sim))
    if max_weighted_sim >= 0.85:
        return 0.0  # near-duplicate of important article
    # Sigmoid falloff centered at 0.7
    novelty = 1.0 / (1.0 + math.exp(10 * (max_weighted_sim - 0.7)))
    return clamp01(novelty)
```

**Signal 8: Event Rarity (weight: 0.07)**

How often does this type of event happen? Model releases from OpenAI are rare (~monthly). Another AI wrapper startup raising seed is weekly. Rarer events deserve more attention.

```python
def event_rarity_score(event_type: str, entity: str | None, session) -> float:
    """Frequency-based rarity over the last 90 days."""
    cutoff = utcnow() - timedelta(days=90)
    total = session.query(Article).join(RawItem).filter(RawItem.fetched_at >= cutoff).count()
    same_type = (
        session.query(Article).join(RawItem)
        .filter(RawItem.fetched_at >= cutoff, Article.event_type == event_type)
        .count()
    )
    if total == 0:
        return 0.5
    base_rate = max(same_type / total, 1e-6)
    # -log2(rate) gives surprise in bits, normalized to [0,1]
    surprise_bits = -math.log2(base_rate)
    max_surprise = -math.log2(1e-6)
    return min(1.0, surprise_bits / max_surprise)
```

**Signal 9: Funding Magnitude (weight: 0.05)**

Only relevant for funding stories. Log-scaled.

```python
def funding_score(amount: int | None) -> float:
    if not amount:
        return 0.0
    return log_norm(amount, 5_000_000_000)
```

**Signal 10: Research Rigor (weight: 0.05)**

Quality indicators for research content.

```python
def research_rigor_score(source_kind: str, text: str) -> float:
    if source_kind == "arxiv":
        return 0.90
    lowered = text.lower()
    if "arxiv:" in lowered or "doi.org/" in lowered:
        return 0.70
    if any(token in lowered for token in ["we propose", "experiments", "dataset", "ablation"]):
        return 0.55
    return 0.35
```

**Signal 11: Source Diversity (weight: 0.03)**

Ratio of unique sources to total articles in cluster. Higher = more editorial independence.

```python
def source_diversity_score(cluster) -> float:
    if not cluster or cluster.coverage_count <= 1:
        return 0.5
    return cluster.sources_count / cluster.coverage_count
```

#### Global Score Formula

```python
def compute_global_score_v2(inputs: GlobalScoreInputs) -> float:
    base01 = clamp01(
        0.15 * entity_prominence_score(inputs.entities)
        + 0.15 * event_impact_score(inputs.event_type)
        + 0.12 * authority_score(inputs.source_authority)
        + 0.12 * corroboration_score(inputs.independent_sources)
        + 0.10 * social_velocity_score(inputs.raw, inputs.age_hours)
        + 0.08 * cluster_velocity_score(inputs.cluster)
        + 0.08 * improved_novelty_score(inputs.embedding, inputs.recent_embeddings, inputs.recent_scores)
        + 0.07 * event_rarity_score(inputs.event_type, inputs.primary_entity, inputs.session)
        + 0.05 * funding_score(inputs.funding_amount_usd)
        + 0.05 * research_rigor_score(inputs.source_kind, inputs.text)
        + 0.03 * source_diversity_score(inputs.cluster)
    )

    score = 100 * base01

    # Multiplicative modifiers
    if is_official_source(inputs.final_url):
        score *= 1.10

    if inputs.event_type in HIGH_IMPACT_EVENTS and inputs.independent_sources >= 3:
        score *= 1.12

    if inputs.funding_amount_usd and inputs.funding_amount_usd >= 1_000_000_000:
        score *= 1.08

    return min(100, round(score, 2))
```

#### Config (in config_sources.yml)

```yaml
weights:
  global:
    entity_prominence: 0.15
    event_impact: 0.15
    authority: 0.12
    corroboration: 0.12
    social_velocity: 0.10
    cluster_velocity: 0.08
    novelty: 0.08
    event_rarity: 0.07
    funding: 0.05
    research_rigor: 0.05
    source_diversity: 0.03
  modifiers:
    official_boost: 1.10
    confirmed_impact_boost: 1.12
    big_money_boost: 1.08
```

---

### Stage 3: LLM Judge

For articles scoring ≥ 40 after Stage 2 (~50 items/day), a fast/cheap LLM rates significance.

#### Prompt

```
You are an AI industry analyst. Score this news article's significance.

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

Return ONLY valid JSON:
{"impact": N, "breadth": N, "novelty": N, "reasoning": "one sentence"}
```

#### LLM Score Conversion

```python
def llm_significance_score(impact: int, breadth: int, novelty: int) -> float:
    raw = 0.50 * impact + 0.25 * breadth + 0.25 * novelty
    return max(0, min(100, (raw - 1) * 100 / 9))
```

#### Final Blending

```python
def compute_final_score(rule_score: float, llm_score: float | None) -> float:
    if llm_score is None:
        return rule_score
    return min(100, round(0.60 * rule_score + 0.40 * llm_score, 2))
```

**Model choice**: GPT-4o-mini, Gemini Flash, or Haiku. ~$0.001-0.003 per article.
At ~50 articles/day = ~$0.05-0.15/day = ~$2-5/month.

---

### Time Decay for Ranking

Time decay affects the *displayed order*, not the stored importance score. Different event types decay at different rates.

```python
EVENT_HALFLIFE_HOURS = {
    "SECURITY_INCIDENT":      6,
    "MODEL_RELEASE":         24,
    "BIG_TECH_ANNOUNCEMENT": 24,
    "OPEN_SOURCE_RELEASE":   24,
    "PRODUCT_LAUNCH":        24,
    "STARTUP_FUNDING":       36,
    "M_AND_A":               36,
    "POLICY_REGULATION":     48,
    "GOVERNMENT_ACTION":     48,
    "BENCHMARK_RESULT":      48,
    "RESEARCH_PAPER":        72,
    "OTHER":                 18,
}

def rank_score(importance_score: float, event_type: str, age_hours: float) -> float:
    halflife = EVENT_HALFLIFE_HOURS.get(event_type, 18)
    return importance_score * (2 ** (-age_hours / halflife))
```

### Urgent Flag

```python
def compute_urgent(global_score: float, age_hours: float, independent_sources: int, is_official: bool) -> bool:
    return (
        global_score >= 85
        and age_hours <= 6
        and (independent_sources >= 2 or is_official)
    )
```

---

## Part 2: Trust Score (0-100, with labels)

Trust score measures how reliable a piece of information is. It is independent from importance — a story can be highly important but unverified.

**Applies to**: News items only.
**Does NOT apply to**: GitHub repos, research papers (these are directly verifiable).

---

### Five Components

#### Component 1: Corroboration (weight: 0.30)

The strongest trust signal. Multiple independent sources reporting the same thing dramatically increases confidence.

**Key**: We measure *independent* sources, not raw article count.

```python
def estimate_independent_sources(cluster_articles: list) -> int:
    """Detect wire echoes and collapse to truly independent sources."""
    source_orgs = set()
    texts = []
    for article in cluster_articles:
        source_orgs.add(article.source.name)
        texts.append(article.text[:500] if article.text else "")

    independent_count = len(source_orgs)

    # Detect wire echoes: if most articles share >60% text with the first
    if len(texts) >= 2:
        from difflib import SequenceMatcher
        reference = texts[0]
        echo_count = sum(
            1 for t in texts[1:]
            if t and SequenceMatcher(None, reference, t).ratio() > 0.60
        )
        if echo_count > len(texts) * 0.6:
            independent_count = max(1, independent_count // 2)

    # Detect attribution chains: "according to Reuters"
    attribution_sources = set()
    for article in cluster_articles:
        if not article.text:
            continue
        for pattern in [
            r"according\s+to\s+(\w+(?:\s+\w+)?)",
            r"as\s+(?:first\s+)?reported\s+by\s+(\w+(?:\s+\w+)?)",
        ]:
            match = re.search(pattern, article.text[:1000], re.I)
            if match:
                attribution_sources.add(match.group(1).lower())

    # If most articles attribute to the same original source, penalize
    if attribution_sources and len(attribution_sources) == 1:
        independent_count = max(1, independent_count - len(cluster_articles) // 2)

    return independent_count


def corroboration_trust_score(independent_sources: int, avg_authority: float) -> float:
    """Corroboration component of trust score."""
    if independent_sources <= 0:
        return 0.1
    source_factor = math.log(1 + independent_sources) / math.log(1 + 10)
    source_factor = min(1.0, source_factor)
    quality_weighted = source_factor * (0.5 + 0.5 * avg_authority)
    return quality_weighted
```

#### Component 2: Official Confirmation (weight: 0.25)

Has the primary entity confirmed this?

```python
def official_confirmation_score(cluster_articles: list, official_domains: list, primary_entity: str | None) -> tuple[float, str]:
    """Returns (score, confirmation_level)."""
    has_official_source = False
    has_press_release = False
    has_entity_confirmation = False

    for article in cluster_articles:
        domain = urlparse(article.final_url).netloc
        if any(domain.endswith(od) for od in official_domains):
            has_official_source = True

        text_lower = (article.text or "").lower()
        if any(phrase in text_lower for phrase in [
            "press release", "we are pleased to announce",
            "today we released", "today we are launching",
            "we are open-sourcing", "we are excited to share",
        ]):
            has_press_release = True

        if primary_entity:
            entity_lower = primary_entity.lower()
            if re.search(rf"{re.escape(entity_lower)}\s+(?:said|confirmed|announced|stated)", text_lower):
                has_entity_confirmation = True

    if has_official_source or has_press_release:
        return 1.0, "official"
    elif has_entity_confirmation:
        return 0.75, "attributed"
    elif any(
        re.search(r"\b(?:sources?|people)\s+(?:say|said|familiar|close)", (a.text or "").lower())
        for a in cluster_articles
    ):
        return 0.25, "unattributed"
    else:
        return 0.05, "rumor"
```

#### Component 3: Source Authority (weight: 0.20)

Credibility of the reporting source, with a boost for primary sources.

```python
def source_trust_score(source_authority: float, is_primary_source: bool) -> float:
    score = source_authority
    if is_primary_source:
        score = min(1.0, score * 1.15)
    return score
```

#### Component 4: Claim Quality (weight: 0.15)

Linguistic analysis of the article text. All regex-based — no ML required.

```python
HEDGE_PATTERNS = [
    r"\breportedly\b", r"\ballegedly\b", r"\bapparently\b",
    r"\bsupposedly\b", r"\brumor(?:ed|s)?\b", r"\bpossibly\b",
    r"\bmight\b", r"\bcould\b(?!\s+not)", r"\bmay\b(?!\s+not)",
    r"\bseems?\s+to\b", r"\bappears?\s+to\b",
    r"\bsources?\s+(?:say|said|claim|suggest)\b",
    r"\baccording\s+to\s+(?:unnamed|anonymous)\b",
    r"\bpeople\s+familiar\s+with\b",
    r"\bunconfirmed\b", r"\bspeculat(?:e|ed|ion)\b",
]

STRONG_ATTRIBUTION_PATTERNS = [
    r"\bannounced\s+(?:in\s+)?(?:a\s+)?(?:press\s+release|blog\s+post|statement)\b",
    r"\baccording\s+to\s+(?:the\s+)?(?:company|official|spokesperson|CEO|CTO)\b",
    r"\bconfirmed\s+(?:by|to|in)\b",
    r"\bin\s+(?:a|an)\s+(?:SEC|regulatory)\s+filing\b",
    r"\bofficial(?:ly)?\b",
]

SPECIFICITY_PATTERNS = [
    r"\$[\d,.]+\s*(?:million|billion|M|B)\b",       # dollar amounts
    r"\b\d+(?:\.\d+)?%\b",                          # percentages
    r"\bversion\s+\d+\b",                            # version numbers
    r"\b\d+\s*(?:parameters?|params?|tokens?)\b",    # model sizes
]

def claim_quality_score(text: str) -> tuple[float, float, float, float]:
    """Returns (overall_score, hedging_ratio, attribution_ratio, specificity_score)."""
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if len(s.strip()) > 10]
    if not sentences:
        return 0.5, 0.5, 0.0, 0.0

    n = len(sentences)

    hedge_count = sum(
        1 for sent in sentences
        if any(re.search(p, sent, re.I) for p in HEDGE_PATTERNS)
    )
    hedging_ratio = hedge_count / n

    attr_count = sum(
        1 for sent in sentences
        if any(re.search(p, sent, re.I) for p in STRONG_ATTRIBUTION_PATTERNS)
    )
    attribution_ratio = attr_count / n

    specificity_hits = sum(len(re.findall(p, text, re.I)) for p in SPECIFICITY_PATTERNS)
    specificity_score = min(1.0, specificity_hits / max(1, n * 0.3))

    overall = (
        0.50 * (1.0 - hedging_ratio)
        + 0.30 * attribution_ratio
        + 0.20 * specificity_score
    )
    return clamp01(overall), hedging_ratio, attribution_ratio, specificity_score
```

#### Component 5: Primary Document (weight: 0.10)

Does the article link to a verifiable artifact?

```python
PRIMARY_DOCUMENT_PATTERNS = [
    r"arxiv\.org/abs/\d{4}\.\d+",             # arxiv paper
    r"github\.com/[\w-]+/[\w-]+/releases",     # GitHub release
    r"doi\.org/",                               # DOI
    r"sec\.gov/",                               # SEC filing
    r"pypi\.org/project/",                      # PyPI package
    r"huggingface\.co/[\w-]+/[\w-]+",           # HF model card
]

def has_primary_document(text: str, url: str) -> bool:
    combined = f"{url} {text[:2000]}"
    return any(re.search(p, combined, re.I) for p in PRIMARY_DOCUMENT_PATTERNS)
```

---

### Composite Trust Score Formula

```python
def compute_trust_score(inputs: TrustScoreInputs) -> tuple[float, str]:
    """Returns (trust_score 0-100, trust_label)."""

    source_cred = source_trust_score(inputs.source_authority, inputs.is_primary_source)
    corroboration = corroboration_trust_score(inputs.independent_sources, inputs.avg_authority)
    confirmation, confirmation_level = official_confirmation_score(
        inputs.cluster_articles, inputs.official_domains, inputs.primary_entity
    )
    claim_qual, hedging, attribution, specificity = claim_quality_score(inputs.text)
    primary_doc = 1.0 if inputs.has_primary_document else 0.0

    raw_score = (
        0.20 * source_cred
        + 0.30 * corroboration
        + 0.25 * confirmation
        + 0.15 * claim_qual
        + 0.10 * primary_doc
    )

    trust_score = round(100 * raw_score, 1)

    # Content-type adjustments
    if inputs.event_type == "RESEARCH_PAPER" and inputs.has_primary_document:
        trust_score = max(trust_score, 65.0)
    if inputs.event_type == "OPEN_SOURCE_RELEASE" and inputs.has_primary_document:
        trust_score = max(trust_score, 70.0)

    # Developing story penalty
    if inputs.is_still_developing and inputs.hours_since_first_report < 2:
        trust_score *= 0.90

    trust_score = min(100.0, trust_score)

    # Determine label
    label = _determine_label(trust_score, inputs, confirmation_level)

    return trust_score, label
```

---

### Trust Labels

```python
def _determine_label(trust_score: float, inputs, confirmation_level: str) -> str:
    # Check for disputed first (sources actively disagree)
    if inputs.has_contradictory_sources:
        return "disputed"

    # Official: primary entity published confirmation
    if confirmation_level == "official":
        return "official"

    # Confirmed: high score + multiple independent sources
    if trust_score >= 75 and inputs.independent_sources >= 3:
        return "confirmed"

    # Likely: decent score + some corroboration
    if trust_score >= 55 and inputs.independent_sources >= 2:
        return "likely"

    # Developing: recent story still accumulating sources
    if inputs.is_still_developing and inputs.hours_since_first_report < 6:
        return "developing"

    # Likely (lower bar): 2+ sources
    if inputs.independent_sources >= 2:
        return "likely"

    # Unverified: everything else
    if trust_score < 40:
        return "unverified"

    return "developing"
```

### Label Display

| Label | Score Range | Color | Icon | Meaning |
|---|---|---|---|---|
| Official | 80-100 | Green | Shield ✓ | Primary entity confirmed |
| Confirmed | 65-79 | Blue | ✓✓ | 3+ independent sources, high authority |
| Likely | 50-64 | Teal | ✓ | 2+ sources or strong attribution |
| Developing | 35-49 | Yellow | Clock | Story < 6 hours old, still unfolding |
| Unverified | 0-34 | Gray | ? | Single source, no corroboration |
| Disputed | any | Red | ⚠ | Sources actively disagree |

**Raw numeric score is NOT shown to users.** Only the label + explainability tooltip.

### Explainability Tooltip

On hover/tap of the trust badge:

```
Confirmed — 4 independent sources
├── OpenAI Blog (official announcement)
├── TechCrunch
├── Reuters
└── The Verge
Claim specificity: High (model name, benchmark numbers cited)
Hedging: Low (3% of statements hedged)
```

---

### Trust Score Config (in config_sources.yml)

```yaml
trust:
  weights:
    source_authority: 0.20
    corroboration: 0.30
    official_confirmation: 0.25
    claim_quality: 0.15
    primary_document: 0.10
  labels:
    official_min_score: 80
    confirmed_min_score: 65
    confirmed_min_sources: 3
    likely_min_score: 55
    likely_min_sources: 2
    developing_max_age_hours: 6
    unverified_max_score: 40
  content_type_floors:
    RESEARCH_PAPER_with_doc: 65
    OPEN_SOURCE_RELEASE_with_doc: 70
  echo_detection:
    text_similarity_threshold: 0.60
    developing_penalty: 0.90
```

---

## Part 3: How Both Scores Interact

### Storage

```python
# Article model fields:
global_score: Float          # 0-100 importance (Stage 2)
llm_score: Float | None      # 0-100 LLM judge (Stage 3)
final_score: Float            # 0-100 blended (0.6*global + 0.4*llm)
trust_score: Float | None     # 0-100 trust (only for news items)
trust_label: Text | None      # "official"/"confirmed"/"likely"/"developing"/"unverified"/"disputed"
trust_components: JSON | None  # breakdown for explainability tooltip
urgent: Boolean               # final_score >= 85 AND age <= 6h AND sources >= 2
```

### Display

```
┌────────────────────────────────────────────────────────┐
│  [85] OpenAI Releases GPT-5              [Official ✓]  │
│                                                        │
│  Summary: OpenAI announced GPT-5 today, claiming...    │
│  Source: openai.com • 3 hours ago                      │
│  Topics: LLMs, Benchmarks                              │
└────────────────────────────────────────────────────────┘
```

- **[85]** = importance score (objective significance)
- **[Official ✓]** = trust label (how reliable)

### Digest Ordering

The evening digest is sorted by `rank_score` (importance with time decay). Trust label appears as a badge but does not affect ordering.

The LLM digest writer is instructed to note trust levels:
- "OpenAI officially announced GPT-5 today..." (official)
- "According to unconfirmed reports, Google is in acquisition talks..." (unverified)
- "Multiple outlets report that the EU AI Act enforcement begins..." (confirmed)

### Urgent Alerts

Urgent alerts require BOTH:
- Importance score ≥ 85
- Trust label of "official", "confirmed", or "likely" (NOT "unverified" or "developing")

This prevents sending urgent notifications for unverified rumors.

---

## Part 4: Schema Changes

### Article Model Additions

```python
# New columns on Article:
entity_prominence: Float           # computed entity tier score
social_velocity: Float             # points-per-hour metric
cluster_velocity: Float            # articles-per-hour in cluster
event_rarity: Float                # historical frequency rarity
independent_sources: Integer       # truly independent source count
llm_score: Float | None            # LLM judge score
llm_reasoning: Text | None         # one-sentence LLM reasoning
final_score: Float                 # blended rule + LLM score
trust_score: Float | None          # 0-100 trust score
trust_label: Text | None           # label string
trust_components: JSON | None      # breakdown dict
hedging_ratio: Float | None        # linguistic signal
attribution_ratio: Float | None    # linguistic signal
specificity_score: Float | None    # linguistic signal
has_primary_document: Boolean       # links to paper/release/filing
confirmation_level: Text | None     # "official"/"attributed"/"unattributed"/"rumor"
```

### Cluster Model Additions

```python
# New columns on Cluster:
cluster_velocity: Float               # articles per hour
independent_sources_count: Integer     # after echo detection
has_official_confirmation: Boolean
cluster_trust_score: Float | None
cluster_trust_label: Text | None
```

---

## Part 5: Implementation Order

### Phase 1: Foundation (importance score redesign)
1. Add new columns to Article and Cluster models + migration
2. Implement entity prominence scoring with static tier list
3. Implement social velocity (points/hour instead of absolute)
4. Implement cluster velocity
5. Implement event rarity
6. Implement source diversity
7. Implement improved novelty (score-weighted)
8. Rewire `compute_global_score` to use new signals and weights
9. Add event-type-specific time decay to rank_score
10. Update API responses with new fields

### Phase 2: Trust score
11. Implement hedging/attribution/specificity analysis (regex-based)
12. Implement wire echo detection
13. Implement official confirmation detection
14. Implement primary document detection
15. Build `compute_trust_score` with all 5 components
16. Add trust label logic
17. Add trust fields to API responses
18. Build explainability tooltip data

### Phase 3: LLM judge
19. Build LLM significance prompt with calibration anchors
20. Implement 3-dimension scoring (impact, breadth, novelty)
21. Build blending logic (0.6 rule + 0.4 LLM)
22. Add LLM score trigger (only for articles scoring ≥ 40)
23. Update urgent flag to require trust label ≥ "likely"

### Phase 4: Tuning
24. Run pipeline on real data, review score distributions
25. Adjust weights based on observed output quality
26. Calibrate LLM prompt anchors based on actual scores
27. Tune trust label thresholds based on observed labels
