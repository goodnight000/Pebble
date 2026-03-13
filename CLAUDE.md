# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AIPulse is an AI news aggregation and intelligence digest application. It consists of a React frontend and a Python FastAPI backend that ingests, scores, clusters, and serves AI-related news from multiple sources.

## Development Commands

```bash
# Install dependencies
npm install

# Run both frontend and backend together (recommended)
npm run dev

# Run frontend only (Vite dev server on port 3000)
npm run dev:web

# Run Python backend only (FastAPI on port 8000)
npm run dev:ai

# Build for production
npm run build
```

The `npm run dev` command automatically:
- Creates a Python venv in `ai_news/.venv` if needed
- Installs Python dependencies from `ai_news/requirements-lite.txt`
- Runs `alembic upgrade head`
- Starts the FastAPI backend with uvicorn
- Starts the Vite frontend with API proxy to backend

Set `DATABASE_URL` before running `npm run dev` or `npm run dev:ai`. The dev scripts now treat it as the canonical database target and no longer fall back to SQLite repair/bootstrap.
These dev scripts also reject SQLite `DATABASE_URL` values explicitly; use Supabase Postgres.

## Architecture

### Frontend (React + TypeScript + Vite)
- Entry: `src/main.tsx` → `src/App.tsx`
- Uses `@/` path alias mapped to `src/`
- `src/services/aiService.ts` - API client with SSE subscription for real-time updates
- `src/types/index.ts` - TypeScript interfaces for NewsItem, DigestResponse, etc.
- `src/components/` - NewsCard, BreakingAlert components

### Backend (Python FastAPI)
Located in `ai_news/app/`:

**API Layer** (`api/`):
- `main.py` - FastAPI app setup, seeds sources and public-user prefs on startup
- `routes_api.py` - Main API endpoints: `/api/digest/today`, `/api/news`, `/api/news/weekly`, `/api/stream` (SSE), `/api/refresh`, `/api/translate`

**Data Layer**:
- `models.py` - SQLAlchemy models: Source, RawItem, Article, Cluster, User, UserPref, DailyDigest
- `db.py` - Database engine setup, session management
- Uses PostgreSQL as the primary runtime via `DATABASE_URL`
- Alembic migrations in `alembic/`

**Processing Pipeline** (`app/`):
- `ingestion/` - RSS/feed ingestion from sources
- `scraping/` - URL content extraction (trafilatura, readability, playwright for JS sites)
- `features/` - Entity extraction, topic classification, event type rules
- `clustering/` - FAISS-based article clustering
- `scoring/` - User-personalized scoring based on preferences
- `llm/` - LLM integration for digest summaries and translations
- `tasks/` - Background tasks (daily digest generation, urgent monitoring)

### Data Flow
1. Sources (RSS feeds, HN, Reddit, arxiv) → RawItem
2. RawItem → scrape full content → Article (with embeddings, event_type, topics, entities, global_score)
3. Articles → Cluster (group similar stories)
4. User preferences → personalized scoring → DigestResponse

## Environment Variables

Frontend reads via Vite:
- `VITE_API_PORT` - Backend API port (default 8000)

Backend (`ai_news/.env.example`):
- `DATABASE_URL` - Supabase PostgreSQL connection string (required for dev scripts)
- `SUPABASE_URL` - Supabase project URL for backend Storage/Realtime and frontend Realtime
- `SUPABASE_ANON_KEY` - Public browser key for frontend Realtime subscriptions
- `SUPABASE_SERVICE_ROLE_KEY` - Backend-only key for Storage uploads and Realtime broadcast publishing
- `SUPABASE_STORAGE_ENABLED` - Enables digest artifact uploads
- `SUPABASE_STORAGE_BUCKET_DIGESTS` - Bucket name for stored digest artifacts
- `SUPABASE_REALTIME_ENABLED` - Enables backend broadcast publishing and frontend config exposure
- `SUPABASE_REALTIME_CHANNEL_URGENT` - Channel name for `urgent_update`
- `SUPABASE_REALTIME_CHANNEL_CLUSTERS` - Channel name for `new_cluster`
- `SUPABASE_REALTIME_CHANNEL_DIGESTS` - Channel name for `digest_refresh`
- `VITE_SUPABASE_URL` - Browser Supabase project URL
- `VITE_SUPABASE_ANON_KEY` - Browser anon key
- `OPENROUTER_API_KEY` or `OPENAI_API_KEY` - For LLM-authored digests and translation
- `LLM_PROVIDER` - `openai` or `openrouter`
- `REDIS_URL`, `CELERY_BROKER_URL` - For production task queue (optional in dev)

Hosted environments should also set `DATABASE_URL` to the Supabase/Postgres target and run `alembic upgrade head` before starting the app process.

## Key Patterns

- Frontend uses EventSource for real-time updates via `/api/stream` SSE endpoint
- Backend auto-seeds initial sources from `app/config_entities.yml` on startup
- Articles scored 0-100 with significance thresholds (85+ = urgent, 55+ = show in feed)
- Support for EN/ZH translation via LLM endpoint at `/api/translate`

## Implementation Workflow

### Subagent-Driven Development
Always use subagent-driven development (`/subagent-driven-development`) when implementing multi-step features or changes that touch multiple files. Break work into independent tasks and run subagents in parallel where possible.

### Skill Selection Before Implementation
Before starting any implementation task, read through all available skills and select the ones relevant to the work. Common skills to consider:
- `/subagent-driven-development` — for parallelizing independent implementation tasks
- `/writing-plans` — for planning multi-step implementations before touching code
- `/test-driven-development` — when adding new modules or functions
- `/systematic-debugging` — when encountering bugs or test failures during implementation
- `/code-review-excellence` or `/requesting-code-review` — after completing implementation
- `/simplify` — review changed code for reuse, quality, and efficiency

Do not skip the skill selection step. Picking the right skills upfront avoids rework and ensures consistent quality.

### General Implementation Rules
- Always read existing code before modifying it. Understand the patterns in place before introducing new ones.
- Prefer editing existing files over creating new ones. Only create new files when the change represents genuinely new functionality.
- Maintain backward compatibility — new API fields should be optional, frontend should degrade gracefully when backend fields are absent.
- Follow existing naming conventions: snake_case in Python, camelCase in TypeScript, kebab-case in CSS classes.
- New backend modules go in the appropriate subdirectory under `ai_news/app/` (e.g., `clustering/`, `features/`, `tasks/`).
- New Alembic migrations must follow the sequential numbering pattern (`0006_`, `0007_`, etc.) and reference the correct `down_revision`.
- When porting logic between frontend and backend (e.g., TypeScript → Python), keep the algorithm semantics identical so behavior is consistent regardless of which side executes it.
- Run `npm run build` to verify TypeScript compilation after frontend changes.
- Keep Python imports lazy where possible in hot paths (API request handlers) to avoid startup cost.
