<div align="center">

# Pebble

**AI news intelligence that cuts through the noise.**

An open-source news aggregation engine that ingests, scores, clusters, and visualizes AI-related news from 1,000+ configured feeds across 15 connector types — delivering a personalized daily digest instead of an endless feed.

[Getting Started](#getting-started) · [How It Works](#how-it-works) · [Features](#features) · [Architecture](#architecture) · [Configuration](#configuration)

</div>

---

## What is Pebble?

Pebble is a full-stack application that monitors the AI landscape in real time. It pulls from RSS feeds, HackerNews, Reddit, GitHub, ArXiv, HuggingFace, Twitter/X, Bluesky, and more — then applies a multi-signal scoring pipeline with LLM-augmented verification to surface the stories that actually matter.

Instead of scrolling through hundreds of links, you get:
- A **longform daily digest** — an LLM-authored briefing covering the day's most significant developments, with an archive of past digests
- A **live feed** with the top 12-15 stories, ranked and scored in real time
- A **Relationship Graph** that visualizes how story clusters connect through shared entities, event chains, and market adjacency
- **Breaking alerts** for genuinely important events (score 85+)
- **Bilingual support** (English/Chinese) with LLM-powered translation

## Getting Started

**Prerequisites:** Node.js 18+, Python 3.11+, PostgreSQL (via Supabase)

```bash
# 1. Clone the repo
git clone https://github.com/goodnight000/Pebble.git
cd Pebble

# 2. Install dependencies
npm install

# 3. Set your database connection
export DATABASE_URL='postgresql+psycopg://...'

# 4. (Optional) Enable LLM-authored digests
export LLM_PROVIDER=openrouter
export OPENROUTER_API_KEY=your-key-here

# 5. Run everything
npm run dev
```

`npm run dev` handles the rest automatically — creates a Python venv, installs backend dependencies, runs database migrations, and starts both the Vite frontend (port 3000) and FastAPI backend (port 8000).

The dev script rejects SQLite `DATABASE_URL` values — Supabase Postgres is required.

### Other Commands

| Command | Description |
|---------|-------------|
| `npm run dev:web` | Frontend only (Vite on port 3000) |
| `npm run dev:ai` | Backend only (FastAPI on port 8000) |
| `npm run build` | Production build |

## How It Works

### The Pipeline

Every ingestion cycle follows this flow:

```
Sources (RSS, HN, Reddit, GitHub, ArXiv, Twitter, Sitemap, ...)
  │
  ▼
RawItem (deduplicated by content hash)
  │
  ▼
Scrape full content (trafilatura → readability → Playwright fallback)
  │
  ▼
Feature extraction
  ├── 384-dim sentence embeddings
  ├── Event type classification (12 types)
  ├── Topic probabilities (12 topics)
  ├── Named entity extraction with tier lookup
  ├── Entity resolution & canonicalization
  └── Funding amount parsing
  │
  ▼
Global scoring (11 weighted signals → 0-100)
  │
  ▼
Verification & trust labeling
  │
  ▼
FAISS clustering (cosine similarity ≥ 0.86)
  │
  ▼
Relationship inference (LLM-augmented edge classification)
  │
  ▼
User-personalized scoring → Daily Digest
```

### Scoring: How Articles Get Ranked

Every article receives a **global score** (0-100) computed from 11 weighted signals:

| Signal | Weight | What it measures |
|--------|--------|-----------------|
| Entity Prominence | 15% | Tier of the companies/orgs mentioned (OpenAI = T1, etc.) |
| Event Impact | 15% | Type of event (model release = 1.0, general news = 0.4) |
| Source Authority | 12% | How trustworthy the source is (0-1 per source) |
| Corroboration | 12% | How many independent sources are reporting the same story |
| Social Velocity | 10% | HN points/hr + Reddit upvotes/hr + GitHub stars/hr |
| Cluster Velocity | 8% | How fast new articles are joining the cluster |
| Novelty | 8% | Inverse similarity to recent articles (rewards genuinely new info) |
| Event Rarity | 7% | How uncommon this event type is right now |
| Funding Amount | 5% | Normalized investment size for funding stories |
| Research Rigor | 5% | PDF presence, citation count for papers |
| Source Diversity | 3% | Number of unique sources in the cluster |

Bonus multipliers kick in for official sources (+10%), well-corroborated stories (+12%), and large funding rounds (+8%).

Additional scoring modules layer on top of the base score:
- **LLM Judge** — optional LLM-based re-scoring for borderline articles
- **Verification** — trust state assessment (confirmation level, freshness, evidence quality)
- **Time Decay** — per-event-type decay curves with configurable half-lives
- **User Score** — personalization adjustments based on user preferences

### Trust Labels

Each story gets a trust assessment based on source authority, corroboration, official confirmation, claim quality, and primary documentation:

| Label | Meaning |
|-------|---------|
| **Official** | From an official source domain, score ≥ 80 |
| **Confirmed** | 3+ independent sources, score ≥ 65 |
| **Likely** | 2+ sources, score ≥ 55 |
| **Developing** | Less than 6 hours old, still emerging |
| **Unverified** | Score below 40 |
| **Disputed** | Conflicting signals detected |

Articles also carry verification metadata: `verification_state`, `verification_confidence`, and `verification_signals` for more granular trust tracking.

### Personalization

Each user can configure preferences that adjust their personal score:

- **Domain weights** — boost or suppress research, startups, hardware, policy, etc.
- **Entity weights** — follow or block specific companies
- **Topic weights** — fine-tune 12 topic categories
- **Source weights** — prefer or ignore specific sources
- **Credibility bias** — favor official sources vs. community discussion
- **Hype tolerance** — weight social velocity higher or lower
- **Recency bias** — configurable time-decay half-life

## Features

### Daily Digest (Default View)

The landing page shows an LLM-authored longform daily briefing:
- Narrative-style coverage of the day's most significant AI developments
- Organized into thematic sections with inline source links
- Archive navigation with prev/next buttons and a date picker
- Generated daily at 6:00 AM UTC (with catch-up on server restart if missed)
- Can be manually triggered via `POST /v1/admin/digest/generate`

### Live Feed

A real-time scored feed with:
- Significance score and trust badge per story
- Category labels (Research, Product, Company, Funding, Policy, Open Source, Hardware, Security)
- Content type filters (All / News / Research / GitHub)
- LLM-generated headline and executive summary per content type
- Weekly digest view (top stories over 7 days)

### Relationship Graph

A force-directed visualization of the current news landscape showing how story clusters relate:

- **Edge types:**
  - *Shared Entity* (solid) — clusters mention the same companies/people
  - *Event Chain* (dashed) — causal or temporal sequence (follow-up, reaction)
  - *Market Adjacency* (dotted) — competitive or alternative relationship
  - *Embedding Similarity* — semantically related clusters
- **LLM-augmented inference** — relationship labels are classified by LLM (follow-up, reaction, competing, unrelated) with batch processing and caching
- **Cluster details** — click any node for headline, trust label, key entities with tier badges, and article list

### Breaking Alerts

When an article scores 85+ with 2+ independent sources and is less than 6 hours old, it triggers a breaking alert — a prominent banner with pulsing animation. Only shows for trusted items (official/confirmed/likely).

### Real-Time Updates

Two mechanisms for live updates:
1. **Server-Sent Events (SSE)** — always available via `/api/stream`
2. **Supabase Realtime** — optional WebSocket channels for urgent updates, new clusters, and digest refreshes

The frontend tries Realtime first and falls back to SSE automatically.

### Entity Resolution

Automatic deduplication and canonicalization of named entities across articles. Entity resolution runs periodically and on each digest generation, grouping aliases (e.g., "Google DeepMind" / "DeepMind") into canonical forms stored in `EntityCanonMap`.

### Bilingual Support

Full English/Chinese interface with:
- All UI labels, navigation, status messages, and trust labels translated
- LLM-powered translation of digest headlines and summaries
- Language persisted in localStorage
- Backend returns translation status so the UI can show appropriate loading states

## Architecture

```
┌──────────────────────────────────────────────┐
│  Frontend (React 19 + TypeScript + Vite)     │
│                                              │
│  App.tsx (tabs: digest, live, weekly,        │
│           history, map)                      │
│  ├── DailyDigestPage (default view)          │
│  ├── NewsCard (scored articles)              │
│  ├── BreakingAlert (urgent items)            │
│  ├── RelationshipGraph                       │
│  │   ├── RelationshipGraphCanvasV2 (D3)      │
│  │   └── RelationshipGraphPanel (details)    │
│  └── i18n/ (EN/ZH)                          │
│                                              │
│  Services:                                   │
│  ├── aiService.ts (API client + SSE)         │
│  └── realtimeService.ts (Supabase WS)        │
└──────────────┬───────────────────────────────┘
               │ HTTP / SSE / WebSocket
┌──────────────▼───────────────────────────────┐
│  Backend (Python FastAPI)                    │
│                                              │
│  API Layer:                                  │
│  ├── /api/digest/today    (card-style)       │
│  ├── /api/digest/daily    (longform)         │
│  ├── /api/digest/archive  (date list)        │
│  ├── /api/news            (live feed)        │
│  ├── /api/news/weekly     (weekly digest)    │
│  ├── /api/stream          (SSE)              │
│  ├── /api/translate       (LLM translation)  │
│  ├── /v1/graph/*          (cluster graph)    │
│  └── /v1/admin/*          (admin triggers)   │
│                                              │
│  Processing:                                 │
│  ├── Ingestion (15 connector types)          │
│  ├── Scraping (trafilatura + Playwright)     │
│  ├── Features (entities, topics, events)     │
│  ├── Entity Resolution (canonicalization)    │
│  ├── Embeddings (sentence-transformers)      │
│  ├── Clustering (FAISS IVFFlat)              │
│  ├── Relationship Inference (LLM-augmented)  │
│  ├── Scoring (11-signal + verification)      │
│  └── LLM (digests, translation, judging)     │
│                                              │
│  Tasks:                                      │
│  ├── Pipeline (ingest → score → cluster)     │
│  ├── Daily Digest (longform + per-type)      │
│  ├── Urgent Monitor (alert on score ≥ 85)    │
│  ├── Relationship Inference (hourly)         │
│  └── Entity Resolution (periodic)            │
│                                              │
│  Scheduling:                                 │
│  ├── Celery Beat (production)                │
│  └── Inline Scheduler (dev, with catch-up)   │
└──────────────┬───────────────────────────────┘
               │
┌──────────────▼───────────────────────────────┐
│  PostgreSQL (Supabase)                       │
│  Sources · RawItems · Articles · Clusters    │
│  Users · UserPrefs · DailyDigests            │
│  EntityCanonMaps                             │
│                                              │
│  Optional:                                   │
│  ├── Supabase Storage (digest artifacts)     │
│  ├── Supabase Realtime (WebSocket events)    │
│  ├── Redis (caching + Celery broker)         │
│  └── Celery (production task queue)          │
└──────────────────────────────────────────────┘
```

### Data Sources

Pebble ingests from 1,000+ configured feeds across 15 connector types:

| Connector | Description | Examples |
|-----------|-------------|---------|
| RSS | 1,000+ feeds | OpenAI, Anthropic, Google DeepMind, Meta AI, NVIDIA, Microsoft, MIT News, etc. |
| HackerNews | Top + new stories | Via HN API |
| Reddit | AI-related subreddits | Via PRAW |
| GitHub | Trending repos + releases | Via GitHub API |
| GitHub Trending | Daily trending repositories | Language-filtered |
| ArXiv | Research papers | CS.AI, CS.CL, CS.LG |
| HuggingFace | Daily papers | Via HF API |
| Semantic Scholar | Academic papers | Citation-enriched |
| Twitter/X | AI community posts | Via Twitter API |
| Bluesky | AI community posts | Via AT Protocol |
| Mastodon | Fediverse AI discussion | Via Mastodon.py |
| Sitemap | Site-wide crawling | XML sitemap discovery |
| Wayback | Historical fallback | Internet Archive lookups |
| NVD | Security vulnerabilities | CVE feeds |
| Congress | AI-related legislation | Via Congress API |

Each source has a configured authority score (0-1), rate limit, and optional priority polling flag.

## Configuration

### Required

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (Supabase format, no SQLite) |

### LLM (Optional but recommended)

| Variable | Description |
|----------|-------------|
| `LLM_PROVIDER` | `openai` or `openrouter` |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `OPENAI_MODEL` | Model name (default: `gpt-4o-mini`) |
| `OPENROUTER_MODEL` | Model name (default: `google/gemini-3-flash-preview`) |

### Supabase Realtime & Storage (Optional)

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Public browser key |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend-only key |
| `SUPABASE_REALTIME_ENABLED` | Enable WebSocket events |
| `SUPABASE_STORAGE_ENABLED` | Enable digest artifact uploads |

### Source API Keys (Optional)

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | GitHub API (higher rate limits) |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | Reddit OAuth |
| `CONGRESS_API_KEY` | US Congress API |
| `SEMANTIC_SCHOLAR_API_KEY` | Academic paper enrichment |

### Hosted Deployment

For production environments:
1. Set `DATABASE_URL` to your Supabase PostgreSQL target
2. Run `alembic upgrade head` before starting the app
3. Enable Supabase Storage and Realtime after migration is verified
4. Configure Celery with Redis for background task processing (`CELERY_BROKER_URL`, `REDIS_URL`)

## Tech Stack

**Frontend:** React 19, TypeScript, Vite, D3.js, DOMPurify, Lucide icons, Supabase JS SDK

**Backend:** FastAPI, SQLAlchemy 2.0, sentence-transformers, FAISS, trafilatura, Playwright, Alembic

**Infrastructure:** PostgreSQL (Supabase), Redis (optional), Celery (optional), Supabase Realtime/Storage (optional)

## License

This is proprietary software. All rights reserved.
