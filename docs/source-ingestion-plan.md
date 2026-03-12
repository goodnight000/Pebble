# Source Ingestion Architecture

This document defines how AIPulse gathers data from all sources — what connectors exist, what needs to be built, and exactly how each source type is handled.

---

## Overview

All sources flow through the same pipeline:

```
Source → Connector → CandidateItem → RawItem (DB) → Pre-Score → Scrape Decision → Article (DB)
```

Every connector implements the same interface:
```python
class Connector(Protocol):
    def fetch_candidates(self, now: datetime) -> List[CandidateItem]
```

CandidateItem is the universal format — regardless of whether data comes from RSS, an API, or a scraper, it normalizes to the same structure with: `source_id`, `external_id`, `url`, `title`, `snippet`, `author`, `published_at`, and social signal fields.

---

## What Already Exists

| Connector | File | Sources Covered |
|---|---|---|
| `RSSConnector` | `ingestion/rss.py` | 25+ RSS sources (blogs, news sites) |
| `ArxivConnector` | `ingestion/arxiv.py` | arxiv cs.AI/LG/CL/RO, stat.ML |
| `GitHubConnector` | `ingestion/github.py` | GitHub Search API (keyword-based) |
| `HackerNewsConnector` | `ingestion/hackernews.py` | HN via Algolia API |
| `RedditConnector` | `ingestion/reddit.py` | r/MachineLearning, r/LocalLLaMA, etc. |

---

## What Needs to Be Built

| Connector | Priority | Effort | Sources It Unlocks |
|---|---|---|---|
| `SitemapConnector` | High | ~100 lines | Anthropic, Meta AI, Apple ML, xAI, Cohere |
| `GitHubTrendingConnector` | High | ~80 lines | GitHub Trending page (daily/weekly viral repos) |
| `GitHubReleasesConnector` | Medium | ~60 lines | Release tracking for watchlist repos |
| `TwitterConnector` | Medium | ~120 lines | X/Twitter via twscrape (50-100 AI accounts) |
| `MastodonConnector` | Low | ~60 lines | sigmoid.social AI community |
| `BlueskyConnector` | Low | ~60 lines | AI researchers on Bluesky |
| `WaybackFallback` | Low | ~30 lines | Archived paywalled articles (opportunistic) |

Plus config-only additions (zero new code — just add entries to `config_sources.yml` using the existing `RSSConnector`).

---

## Tier 1: Primary Sources

### 1A. Company Blogs — RSS (Existing Connector)

**Method**: `RSSConnector` — poll RSS/Atom feeds.
**Polling frequency**: Every 15-30 min for priority sources, hourly for others.
**Already configured**: OpenAI, Google Research, DeepMind, NVIDIA, Microsoft AI, AWS ML, Hugging Face, Stability AI.

**Config additions needed** (use existing RSSConnector, just add to `config_sources.yml`):

```yaml
- name: "Mistral AI Blog"
  kind: "rss"
  feed_url: "https://mistral.ai/feed.xml"
  authority: 0.90
  always_scrape: true
  priority_poll: true
  enabled: true

- name: "Together AI Blog"
  kind: "rss"
  feed_url: "https://www.together.ai/blog/rss.xml"
  authority: 0.78
  priority_poll: false
  enabled: true
```

**Anthropic and Meta AI** — These do NOT have RSS feeds. They need the new `SitemapConnector` (see below).

### 1B. Company Blogs — Sitemap (New Connector)

**Method**: Parse XML sitemaps to detect new blog posts by `<lastmod>` date.
**Why**: Some major AI labs (Anthropic, Meta AI, Apple ML) have no RSS feed but all have sitemaps for SEO.

**Implementation**:

```python
# ingestion/sitemap.py
class SitemapConnector:
    """Discover new blog posts from XML sitemaps."""

    def __init__(self, source_id: str, sitemap_url: str, path_filter: str):
        self.source_id = source_id
        self.sitemap_url = sitemap_url
        self.path_filter = path_filter  # e.g., "/news/" or "/blog/"

    async def fetch_candidates(self, now: datetime) -> list[CandidateItem]:
        # 1. Fetch sitemap XML via httpx
        # 2. Parse <url> entries with lxml
        # 3. Filter by path_filter (only blog/news URLs)
        # 4. Filter by <lastmod> > cutoff (lookback window)
        # 5. For each new URL, fetch the page and extract title via <title> tag
        # 6. Return CandidateItems
```

**Sources this unlocks**:

| Source | Sitemap URL | Path Filter |
|---|---|---|
| Anthropic | `https://www.anthropic.com/sitemap.xml` | `/news/` or `/research/` |
| Meta AI | `https://ai.meta.com/sitemap.xml` | `/blog/` |
| Apple ML | `https://machinelearning.apple.com/sitemap.xml` | `/research/` |
| xAI | `https://x.ai/sitemap.xml` | `/blog/` |
| Cohere | `https://cohere.com/sitemap.xml` | `/blog/` |

**Polling frequency**: Every 30 minutes (sitemaps are lightweight XML).
**Cost**: $0.

---

### 1C. Government & Regulatory Sources — RSS (Existing Connector)

Most government sources with AI relevance have RSS feeds. These go through the existing `RSSConnector` with one important addition: **keyword post-filtering**. Government RSS feeds contain a lot of non-AI content, so we add a relevance check during pre-scoring to filter out unrelated items (the existing keyword scoring already handles this).

**Config additions** (all use existing RSSConnector):

```yaml
# === US Government ===
- name: "White House Briefing Room"
  kind: "rss"
  feed_url: "https://www.whitehouse.gov/briefing-room/feed/"
  authority: 0.95
  always_scrape: false
  priority_poll: false
  enabled: true

- name: "FTC Press Releases"
  kind: "rss"
  feed_url: "https://www.ftc.gov/feeds/press-releases.xml"
  authority: 0.92
  always_scrape: false
  priority_poll: false
  enabled: true

- name: "NIST News"
  kind: "rss"
  feed_url: "https://www.nist.gov/news-events/news/rss.xml"
  authority: 0.90
  always_scrape: false
  priority_poll: false
  enabled: true

# === EU ===
- name: "EU Commission Press Corner"
  kind: "rss"
  feed_url: "https://ec.europa.eu/commission/presscorner/api/rss"
  authority: 0.93
  always_scrape: false
  priority_poll: false
  enabled: true

- name: "EUR-Lex Legislation"
  kind: "rss"
  feed_url: "https://eur-lex.europa.eu/content/help/rss-feeds.html"
  authority: 0.90
  always_scrape: false
  priority_poll: false
  enabled: true

# === UK ===
- name: "UK GOV AI & Technology"
  kind: "rss"
  feed_url: "https://www.gov.uk/search/news-and-communications.atom?topics[]=artificial-intelligence"
  authority: 0.90
  always_scrape: false
  priority_poll: false
  enabled: true

# === China (English proxy sources) ===
- name: "DigiChina (Stanford)"
  kind: "rss"
  feed_url: "https://digichina.stanford.edu/feed/"
  authority: 0.85
  always_scrape: false
  priority_poll: false
  enabled: true

- name: "SCMP Tech"
  kind: "rss"
  feed_url: "https://www.scmp.com/rss/5/feed"
  authority: 0.80
  always_scrape: false
  priority_poll: false
  enabled: true

# === International Policy ===
- name: "OECD AI Policy Observatory"
  kind: "rss"
  feed_url: "https://oecd.ai/en/feed"
  authority: 0.85
  always_scrape: false
  priority_poll: false
  enabled: true

- name: "Brookings TechStream"
  kind: "rss"
  feed_url: "https://www.brookings.edu/topic/technology/feed/"
  authority: 0.82
  always_scrape: false
  priority_poll: false
  enabled: true

- name: "Lawfare"
  kind: "rss"
  feed_url: "https://www.lawfaremedia.org/feed"
  authority: 0.80
  always_scrape: false
  priority_poll: false
  enabled: true

- name: "CSIS Technology"
  kind: "rss"
  feed_url: "https://www.csis.org/topics/technology/feed"
  authority: 0.80
  always_scrape: false
  priority_poll: false
  enabled: true
```

**For China specifically**: We do NOT scrape Chinese government sites directly (CAC, MIIT). They block foreign IPs, have no APIs, and require translation. Instead, we monitor English-language proxy sources that digest Chinese AI policy: DigiChina (Stanford), South China Morning Post tech section, and ChinaTalk newsletter.

**For Middle East**: UAE AI Office and Saudi SDAIA update very infrequently (monthly). We'd add them via the `SitemapConnector` with weekly polling — not worth a high-frequency check.

**Polling frequency**: Hourly for all government sources. AI-related items are rare in these feeds, but when they appear (executive orders, EU AI Act updates), they're high-impact.
**Cost**: $0.

---

### 1D. Congress.gov API (New — lightweight custom connector)

The US Congress has a free API for tracking AI-related legislation.

```python
# ingestion/congress.py
class CongressConnector:
    """Track AI-related bills and legislation via Congress.gov API."""

    BASE = "https://api.congress.gov/v3"

    async def fetch_candidates(self, now: datetime) -> list[CandidateItem]:
        # GET /bill?query="artificial intelligence"&sort=updateDate+desc
        # Free API key required (register at api.congress.gov)
        # Rate limit: 5000 req/hour
        # Return bills as CandidateItems
```

**Polling frequency**: Daily (legislation moves slowly).
**Cost**: $0 (free API key).

---

### 1E. arxiv Papers (Existing Connector — Needs Fixes + Enrichment)

**Current state**: `ArxivConnector` works but defaults to only 10 results (cs.LG alone gets 100+ papers/day).

**Fixes needed**:
1. Add `max_results=200` and pagination to API queries
2. Add arxiv RSS feeds as a separate, simpler ingestion path

**Config additions** (existing RSSConnector — arxiv has RSS feeds too):

```yaml
- name: "arXiv cs.AI RSS"
  kind: "rss"
  feed_url: "https://rss.arxiv.org/rss/cs.AI"
  authority: 0.90
  always_scrape: false
  priority_poll: false
  enabled: true

- name: "arXiv cs.LG RSS"
  kind: "rss"
  feed_url: "https://rss.arxiv.org/rss/cs.LG"
  authority: 0.90
  always_scrape: false
  priority_poll: false
  enabled: true

- name: "arXiv cs.CL RSS"
  kind: "rss"
  feed_url: "https://rss.arxiv.org/rss/cs.CL"
  authority: 0.90
  always_scrape: false
  priority_poll: false
  enabled: true

- name: "Hugging Face Daily Papers"
  kind: "rss"
  feed_url: "https://huggingface.co/papers/rss"
  authority: 0.85
  always_scrape: false
  priority_poll: true
  enabled: true
```

**Enrichment (Phase 2)**: After ingesting arxiv papers, call the Semantic Scholar API (free, 1 req/sec unauthenticated, 10 req/sec with free key) to get:
- Citation count and velocity (how fast it's being cited)
- Influential citations flag
- TLDR summary
- This enrichment feeds into the importance scoring algorithm.

**Polling frequency**: arxiv RSS updates daily at ~20:00 UTC. API connector runs every 3 hours.
**Cost**: $0.

---

### 1F. GitHub — Trending + Releases (New Connectors)

**Current state**: `GitHubConnector` uses Search API with keyword queries. This finds repos but misses trending dynamics and releases.

**New connector 1 — GitHub Trending**:

```python
# ingestion/github_trending.py
class GitHubTrendingConnector:
    """Scrape GitHub Trending page for daily/weekly viral repos."""

    async def fetch_candidates(self, now: datetime) -> list[CandidateItem]:
        # 1. Fetch https://github.com/trending?since=daily
        # 2. Parse with BeautifulSoup (HTML structure is stable)
        # 3. Extract: repo name, description, language, stars today
        # 4. Filter for AI/ML repos (by language: Python, or by description keywords)
        # 5. Return CandidateItems with social_github_stars = stars_today
```

**New connector 2 — GitHub Release Tracking via Atom Feeds** (zero new code!):

Every GitHub repo has an Atom feed at `/{owner}/{repo}/releases.atom`. We just add these to `config_sources.yml` using the existing `RSSConnector`:

```yaml
- name: "Transformers Releases"
  kind: "rss"
  feed_url: "https://github.com/huggingface/transformers/releases.atom"
  authority: 0.85
  priority_poll: true
  enabled: true

- name: "LangChain Releases"
  kind: "rss"
  feed_url: "https://github.com/langchain-ai/langchain/releases.atom"
  authority: 0.80
  priority_poll: false
  enabled: true

- name: "llama.cpp Releases"
  kind: "rss"
  feed_url: "https://github.com/ggerganov/llama.cpp/releases.atom"
  authority: 0.82
  priority_poll: true
  enabled: true

- name: "vLLM Releases"
  kind: "rss"
  feed_url: "https://github.com/vllm-project/vllm/releases.atom"
  authority: 0.80
  priority_poll: false
  enabled: true

- name: "PyTorch Releases"
  kind: "rss"
  feed_url: "https://github.com/pytorch/pytorch/releases.atom"
  authority: 0.88
  priority_poll: true
  enabled: true

- name: "Ollama Releases"
  kind: "rss"
  feed_url: "https://github.com/ollama/ollama/releases.atom"
  authority: 0.78
  priority_poll: false
  enabled: true

- name: "Open WebUI Releases"
  kind: "rss"
  feed_url: "https://github.com/open-webui/open-webui/releases.atom"
  authority: 0.75
  priority_poll: false
  enabled: true
```

This watchlist should grow over time — add any major AI repo that releases frequently.

**Star velocity calculation (Phase 2)**: For repos found via search/trending, make a secondary API call to `GET /repos/{owner}/{repo}/stargazers` with `Accept: application/vnd.github.star+json` to get timestamps. Calculate stars gained in last 24h/7d. This feeds into importance scoring.

**Polling frequency**: Trending page: twice daily. Release feeds: every 30 min (Atom feeds are lightweight). Search API: every 6 hours.
**Cost**: $0 (GitHub API with free token = 5000 req/hr).

---

## Tier 2: Journalism & Newsletters

### 2A. Tech News — RSS (Existing Connector)

**Already configured**: TechCrunch, VentureBeat, The Verge, Wired, Ars Technica, MIT Tech Review.

**Additions needed**:

```yaml
- name: "Reuters Technology"
  kind: "rss"
  feed_url: "https://www.reuters.com/technology/rss"
  authority: 0.90
  always_scrape: false
  priority_poll: true
  enabled: true

- name: "NYT Technology"
  kind: "rss"
  feed_url: "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"
  authority: 0.88
  always_scrape: false
  priority_poll: false
  enabled: true

- name: "Bloomberg Technology"
  kind: "rss"
  feed_url: "https://feeds.bloomberg.com/technology/news.rss"
  authority: 0.90
  always_scrape: false
  priority_poll: false
  enabled: true
```

**Content extraction**: When RSS gives truncated content, the existing scraping pipeline handles it:
`trafilatura (primary) → readability-lxml (fallback) → Playwright (JS-heavy sites)`

This cascade is confirmed by research as the optimal approach. trafilatura has the best F1 score (~0.89) of any Python content extractor.

**Polling frequency**: Every 15 min for priority, every 30 min for others.
**Cost**: $0.

### 2B. AI Newsletters — Substack/Beehiiv RSS (Existing Connector)

Every Substack and Beehiiv newsletter exposes a free RSS feed with **full article text**. These are high-value, high-signal sources.

```yaml
- name: "Import AI (Jack Clark)"
  kind: "rss"
  feed_url: "https://importai.substack.com/feed"
  authority: 0.85
  always_scrape: false
  priority_poll: false
  enabled: true

- name: "One Useful Thing (Ethan Mollick)"
  kind: "rss"
  feed_url: "https://www.oneusefulthing.org/feed"
  authority: 0.80
  always_scrape: false
  priority_poll: false
  enabled: true

- name: "Simon Willison"
  kind: "rss"
  feed_url: "https://simonwillison.substack.com/feed"
  authority: 0.78
  always_scrape: false
  priority_poll: false
  enabled: true

- name: "Interconnects (Nathan Lambert)"
  kind: "rss"
  feed_url: "https://www.interconnects.ai/feed"
  authority: 0.78
  always_scrape: false
  priority_poll: false
  enabled: true

- name: "The Gradient"
  kind: "rss"
  feed_url: "https://thegradient.pub/rss/"
  authority: 0.75
  always_scrape: false
  priority_poll: false
  enabled: true

- name: "The Batch (deeplearning.ai)"
  kind: "rss"
  feed_url: "https://www.deeplearning.ai/the-batch/feed/"
  authority: 0.82
  always_scrape: false
  priority_poll: false
  enabled: true

- name: "TLDR AI Newsletter"
  kind: "rss"
  feed_url: "https://tldr.tech/ai/rss"
  authority: 0.72
  always_scrape: false
  priority_poll: false
  enabled: true
```

**Why these matter for paywalled content**: Newsletters like Import AI, The Batch, and TLDR AI legally summarize content from paywalled sources (Bloomberg, The Information, FT). By ingesting these, we get the key facts from paywalled stories without bypassing anything.

**Polling frequency**: Daily (newsletters are typically daily or weekly).
**Cost**: $0.

### 2C. Paywalled Sources — Headline + Signal Strategy

For hard-paywalled publications (The Information, Bloomberg, FT, The Economist), we **cannot and should not** get full article text for free. Instead:

**What we ingest**:
1. **Headlines + abstracts from RSS** — Bloomberg and FT RSS feeds give 1-2 sentences
2. **NYT Developer API** (free tier, 4000 req/day) — gives headlines, abstracts, lead paragraphs, keywords
3. **HN/Reddit discussion mining** — when a paywalled article gets discussed on HN, commenters summarize the key facts. We already ingest HN and Reddit; we cross-reference URLs from paywalled domains.
4. **Press wire RSS** — Many Bloomberg/FT stories originate from press releases on PRNewswire/BusinessWire. We catch them at the source.

**How paywalled items appear in the digest**:
- Show with headline + abstract (from RSS/API)
- Marked with "subscription required" indicator
- Link to original source
- Trust score and importance score still work — based on metadata, not full text
- If HN/Reddit discussions exist, we can incorporate those signals

**Config additions for press wires**:

```yaml
- name: "PRNewswire Tech"
  kind: "rss"
  feed_url: "https://www.prnewswire.com/rss/technology-latest-news.rss"
  authority: 0.65
  always_scrape: false
  priority_poll: false
  enabled: true

- name: "BusinessWire Tech"
  kind: "rss"
  feed_url: "https://feed.businesswire.com/rss/home/?rss=G1QFDERJXkJeGVgMXA=="
  authority: 0.65
  always_scrape: false
  priority_poll: false
  enabled: true
```

**Wayback Machine fallback** (opportunistic, Phase 2):

```python
# ingestion/wayback.py
async def check_wayback(url: str) -> str | None:
    """Check if a paywalled URL has been archived. Returns archive URL or None."""
    resp = await httpx.get(
        "https://archive.org/wayback/available",
        params={"url": url}
    )
    snapshot = resp.json().get("archived_snapshots", {}).get("closest", {})
    if snapshot.get("available") and snapshot.get("status") == "200":
        return snapshot["url"]
    return None
```

This runs after ingestion for paywalled items with high pre-scores. If an archived version exists, we fetch and extract it. Not reliable enough to depend on, but catches some articles.

**Cost**: $0.

---

## Tier 3: Community Signals

### 3A. Hacker News (Existing Connector)

**Current state**: Working well. Uses Algolia API with keyword queries.
**Cost**: $0 (no auth, ~10k req/hr).
**Polling frequency**: Every 5-10 minutes.

**Enhancement needed**: Track velocity (points over time). The HN API only gives current score, so we poll target stories every 15-30 min and compute rate:
```
velocity = (score_now - score_30min_ago) / 0.5  # points per hour
```

Fast-rising stories (>50 points/hr) are strong signals of breaking news.

### 3B. Reddit (Existing Connector)

**Current state**: Working, uses PRAW. Subreddits: MachineLearning, LocalLLaMA, OpenAI, singularity, artificial.
**Cost**: $0 (free OAuth tier, 100 req/min).
**Polling frequency**: Every 10-15 minutes.

**Alternative approach**: Reddit RSS feeds (no auth needed):
```
https://www.reddit.com/r/MachineLearning/top/.rss?t=day
```
Could use as a lightweight fallback if PRAW auth breaks.

### 3C. X/Twitter (New Connector)

**Method**: `twscrape` — open-source Python library using X's mobile API with authenticated accounts.

```python
# ingestion/twitter.py
class TwitterConnector:
    """Monitor AI accounts on X/Twitter via twscrape."""

    # Pool of 3-5 X accounts for rate limit distribution
    AI_ACCOUNTS = [
        "OpenAI", "AnthropicAI", "GoogleDeepMind", "xaboratory",
        "MetaAI", "huggingface", "MistralAI",
        "karpathy", "ylecun", "sama", "demaboratory",
        "DrJimFan", "emollick", "svpino",
        # ... up to 50-100 accounts
    ]

    async def fetch_candidates(self, now: datetime) -> list[CandidateItem]:
        # 1. For each account, fetch last 20 tweets
        # 2. Filter by recency (last 24h)
        # 3. Filter for AI relevance (keyword check on tweet text)
        # 4. Extract any linked URLs (tweets often link to articles/papers)
        # 5. Return CandidateItems with social signals (likes, retweets)
```

**Account pool management**:
- 3-5 X accounts in the pool (free to create)
- twscrape handles session rotation automatically
- ~500 tweets/15min per account = comfortably monitor 100 accounts every 2-4 hours

**Failure handling**:
- If twscrape breaks (X changes auth flow), fall back to `twikit` (alternative library)
- If both break, fall back to self-hosted RSSHub with X auth tokens
- Budget ~1-2 hours/month for maintenance

**Polling frequency**: Every 2-4 hours per account.
**Cost**: $0 (free accounts + free library).
**Dependencies**: `twscrape` (add to `requirements-lite.txt`).

### 3D. Mastodon (New Connector — Phase 2)

```python
# ingestion/mastodon.py
class MastodonConnector:
    """Track AI discussions on Mastodon via hashtag monitoring."""

    INSTANCES = ["sigmoid.social", "mastodon.social"]
    HASHTAGS = ["MachineLearning", "AI", "LLM", "NLP", "DeepLearning"]

    async def fetch_candidates(self, now: datetime) -> list[CandidateItem]:
        # Public API, no auth needed for hashtag timelines
        # GET https://sigmoid.social/api/v1/timelines/tag/MachineLearning
        # Rate limit: ~300 req/5min (generous)
```

**Cost**: $0.
**Dependencies**: `Mastodon.py` (add to `requirements-lite.txt`).

### 3E. Bluesky (New Connector — Phase 2)

```python
# ingestion/bluesky.py
class BlueskyConnector:
    """Track AI content on Bluesky via AT Protocol."""

    async def fetch_candidates(self, now: datetime) -> list[CandidateItem]:
        # Uses atproto library
        # Search for AI-related posts
        # client.app.bsky.feed.search_posts({'q': 'machine learning', 'limit': 25})
```

**Cost**: $0 (AT Protocol is free and open).
**Dependencies**: `atproto` (add to `requirements-lite.txt`).

### 3F. YouTube (Config-only — Existing Connector)

Every YouTube channel has an RSS feed. No new code needed:

```yaml
- name: "Two Minute Papers"
  kind: "rss"
  feed_url: "https://www.youtube.com/feeds/videos.xml?channel_id=UCbfYPyITQ-7l4upoX8nvctg"
  authority: 0.70
  priority_poll: false
  enabled: true

- name: "AI Explained"
  kind: "rss"
  feed_url: "https://www.youtube.com/feeds/videos.xml?channel_id=UCNJ1Ymd5yFuUPtn21xtRZQ"
  authority: 0.68
  priority_poll: false
  enabled: true
```

**Polling frequency**: Every 30-60 min.
**Cost**: $0.

---

## How Community Signals Integrate With News

Community sources (HN, Reddit, X, Mastodon, Bluesky) serve **two purposes**:

### 1. Discovery
Sometimes a paper, blog post, or GitHub repo surfaces on HN before any journalist covers it. The community connector discovers it, creates a CandidateItem, and it enters the normal pipeline.

### 2. Signal Boosting
When an article we already have from an RSS feed gets 500 HN points or trending on Reddit, that boosts its importance score. The pipeline detects this by matching URLs:

```
If CandidateItem.url matches an existing Article.final_url:
    → Don't create a duplicate
    → Update the Article's social signals (hn_points, reddit_upvotes, etc.)
    → Recalculate global_score with boosted social component
```

This is how a single-source blog post gets elevated when the community validates it.

---

## Content Extraction Pipeline

After a CandidateItem passes pre-scoring (score ≥ 40), it gets scraped for full content:

```
URL
 ↓
httpx fetch (respect robots.txt, rate limits)
 ↓
trafilatura extract (primary — F1 ~0.89)
 ↓ fails?
readability-lxml extract (fallback — F1 ~0.83)
 ↓ fails?
Playwright headless browser (last resort — JS-heavy sites)
 ↓
Clean text + metadata (title, author, date, language)
```

**Improvements to implement**:
1. **Conditional GET** (ETag/If-Modified-Since) — reduces bandwidth 70-90% for unchanged feeds. Biggest efficiency win.
2. **Domain-specific CSS selectors** for high-value sources where generic extraction struggles:
   ```python
   DOMAIN_SELECTORS = {
       "techcrunch.com": "article .article-content",
       "theverge.com": "article .duet--article--article-body-component",
   }
   ```
3. **Jitter on poll intervals** — add ±20% random variation to prevent thundering herd.
4. **Exponential backoff** on 429/503 errors.

---

## Polling Schedule

| Source Group | Interval | Task Name |
|---|---|---|
| Priority RSS (company blogs, major news) | 15 min | `run_priority_poll` |
| Normal RSS (newsletters, policy, YouTube) | 30 min | `run_normal_poll` |
| Government RSS | 60 min | `run_gov_poll` |
| Hacker News | 5-10 min | `run_hn_poll` |
| Reddit | 10-15 min | `run_reddit_poll` |
| X/Twitter | 2-4 hours | `run_twitter_poll` |
| arxiv (API + RSS) | 3 hours | `run_arxiv_poll` |
| GitHub (search + trending) | 6 hours | `run_github_poll` |
| GitHub releases (Atom) | 30 min | handled by `run_normal_poll` |
| Sitemaps (Anthropic, Meta, etc.) | 30 min | `run_sitemap_poll` |
| Mastodon/Bluesky | 15-30 min | `run_social_poll` |
| Congress.gov API | 24 hours | `run_gov_api_poll` |

---

## New Dependencies

```
# Add to requirements-lite.txt
twscrape>=0.12.0       # X/Twitter scraping
Mastodon.py>=1.8.0     # Mastodon API (Phase 2)
atproto>=0.0.50        # Bluesky AT Protocol (Phase 2)
lxml>=5.0.0            # Sitemap XML parsing (may already be present)
```

---

## Total Source Count After Implementation

| Category | Count | Method |
|---|---|---|
| Company blogs (RSS) | ~12 | Existing RSSConnector |
| Company blogs (Sitemap) | ~5 | New SitemapConnector |
| Government (RSS) | ~12 | Existing RSSConnector |
| Government (API) | 1 | New CongressConnector |
| Tech journalism (RSS) | ~10 | Existing RSSConnector |
| AI newsletters (RSS) | ~7 | Existing RSSConnector |
| Press wires (RSS) | ~2 | Existing RSSConnector |
| Policy think tanks (RSS) | ~4 | Existing RSSConnector |
| arxiv (API + RSS) | ~4 | Existing ArxivConnector + RSS |
| GitHub (Search + Trending + Releases) | ~10+ | Existing + new connectors |
| Hacker News | 1 | Existing HNConnector |
| Reddit | 5 subreddits | Existing RedditConnector |
| X/Twitter | 50-100 accounts | New TwitterConnector |
| Mastodon | 2 instances | New MastodonConnector |
| Bluesky | 1 | New BlueskyConnector |
| YouTube (RSS) | ~3-5 | Existing RSSConnector |
| **Total unique sources** | **~80-130** | |

---

## Total Cost

| Component | Monthly Cost |
|---|---|
| All RSS feeds | $0 |
| All APIs (HN, GitHub, arxiv, Reddit, Semantic Scholar, Congress.gov, NYT) | $0 |
| X/Twitter (twscrape + free accounts) | $0 |
| Mastodon + Bluesky | $0 |
| YouTube RSS | $0 |
| Content extraction (trafilatura, readability) | $0 |
| LLM costs (scoring + summarization, ~50 items/day) | ~$5-15 |
| **Total** | **~$5-15/month** |

---

## Implementation Order

### Phase 1: Quick Wins (config-only, no new code)
1. Add all new RSS sources to `config_sources.yml` (newsletters, government, policy, YouTube, GitHub releases)
2. Fix arxiv connector pagination (change max_results to 200)
3. Enable Anthropic and Meta AI sources (currently disabled)

### Phase 2: Core New Connectors
4. Build `SitemapConnector` for Anthropic, Meta AI, Apple ML, xAI, Cohere
5. Build `GitHubTrendingConnector` for daily trending repos
6. Build `TwitterConnector` via twscrape
7. Implement conditional GET (ETag/If-Modified-Since) for RSS polling

### Phase 3: Enrichment & Secondary Sources
8. Add Semantic Scholar API enrichment for arxiv papers
9. Build `MastodonConnector` and `BlueskyConnector`
10. Add Wayback Machine fallback for paywalled articles
11. Add `CongressConnector` for US legislation tracking
12. Implement HN velocity tracking (polling + rate calculation)
