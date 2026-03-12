# Supabase Migration Design

**Goal:** Make Supabase the platform backbone for AIPulse by moving the primary database to Supabase Postgres, adopting Supabase Storage for durable blob artifacts, and adopting Supabase Realtime for curated live events, while keeping FastAPI as the application control plane.

**Problem:** The backend is currently split between PostgreSQL-shaped schema definitions and a SQLite-first runtime. Local scripts default to SQLite, startup calls `Base.metadata.create_all()` instead of trusting Alembic, and the frontend relies on backend SSE only. That combination increases drift risk and makes a safe Supabase cutover harder than it needs to be.

**Approved Direction:** Use a backend-owned Supabase architecture. FastAPI remains the only writer and orchestration layer. Supabase Postgres becomes the only primary relational database. Supabase Storage is used for durable artifact payloads, not hot-path relational data. Supabase Realtime is used for curated event broadcasts, with existing SSE preserved during rollout as a compatibility path.

## Principles
- Make Alembic the single schema authority.
- Keep secrets server-side.
- Avoid public table subscriptions until auth and RLS exist.
- Preserve current API contracts during rollout.
- Use Supabase features where they add operational value, not as a reason to split core logic across too many systems.
- Prefer staged migration over a big-bang rewrite.

## Target Architecture
### Database
- Replace SQLite as the default runtime with Supabase Postgres via `DATABASE_URL`.
- Keep SQLAlchemy + Alembic as the application schema and query layer.
- Remove startup `create_all()` so runtime cannot silently diverge from migrations.
- Keep the current backend query model and ranking logic intact unless Postgres-specific fixes are required.

### Storage
- Use Supabase Storage for durable blob artifacts only.
- First storage use case: persist generated digest artifacts and exports outside relational rows.
- Keep article metadata, user preferences, ranking signals, source records, and clustering state in Postgres.
- Prefer private buckets with backend-managed upload/signing over public buckets.

### Realtime
- Publish curated backend events to Supabase Realtime channels:
  - `urgent_update`
  - `new_cluster`
  - `digest_refresh`
- Do not expose raw table change feeds directly to the client yet.
- Keep the existing SSE endpoint during rollout so the frontend can fail over cleanly if Realtime wiring is incomplete or temporarily disabled.

### Auth
- Supabase Auth is deferred.
- No RLS-dependent client-write path will be introduced in this migration.
- The design should leave room for a later move from `PUBLIC_USER_ID` to authenticated Supabase users.

## Scope
### In scope
- Postgres-first backend runtime
- Alembic-only schema bootstrapping
- Supabase client configuration on the backend
- Storage integration for digest/export artifacts
- Realtime event publishing from backend workflows
- Optional frontend Realtime subscription path with SSE fallback
- Updated local/dev scripts and operational docs

### Out of scope
- Supabase Auth login flows
- Full replacement of backend APIs with direct client database access
- RLS policy rollout for anonymous/public users
- Moving embeddings or FAISS index storage into Supabase-specific vector/search features

## Key Backend Changes
- `ai_news/app/config.py`
  - add Supabase settings for project URL, anon key, service role key, bucket names, and feature flags
- `ai_news/app/db.py`
  - remove SQLite-special assumptions from the default path
  - tune Postgres engine creation for Supabase-compatible pooling and connection reuse
- `ai_news/app/api/main.py`
  - stop calling `Base.metadata.create_all()`
  - keep startup bootstrap limited to safe application initialization and seed behavior
- `scripts/dev.ts` and `scripts/dev-ai.ts`
  - stop silently defaulting to SQLite
  - run Alembic migrations instead of schema repair/bootstrap logic as the primary setup path

## Data Model Notes
- Existing Alembic history is already largely Postgres-oriented.
- `0001_initial` uses PostgreSQL UUID and JSONB types; later migrations partially added dialect flexibility for SQLite.
- The migration should normalize the project around Postgres rather than keep dual-dialect behavior as a first-class concern.
- Storage adoption likely requires adding metadata columns to `daily_digests` for stored object references.

## Realtime Contract
- Backend publishes compact event payloads, not full hydrated article tables.
- Event payloads should contain stable IDs and enough summary data for the UI to react without forcing a full-page reload.
- The frontend should treat Realtime as an enhancement layer and continue to support polling/SSE fallback until production confidence is high.

## Rollout Plan
### Phase 1: Normalize local and backend runtime
- Remove SQLite-first defaults.
- Make migrations mandatory.
- Keep SSE as-is.

### Phase 2: Add backend Supabase integrations
- Add Storage uploads for digest artifacts.
- Add Realtime publish hooks for curated events.

### Phase 3: Add frontend Realtime consumption
- Subscribe to curated channels when env vars are present.
- Preserve existing REST/SSE path as fallback.

### Phase 4: Hosted cutover
- Point `DATABASE_URL` at Supabase.
- Run Alembic migrations against the Supabase project.
- Validate seed/bootstrap behavior, ingest, digest generation, and live updates.

## Verification
- Backend unit tests continue to pass under a Postgres-oriented config surface.
- New tests cover:
  - no implicit `create_all()` startup path
  - required Supabase env/config validation
  - storage artifact persistence contract
  - realtime event payload generation/publishing
- Frontend build passes and Realtime wiring degrades cleanly when env vars are absent.

## Operator Hand-off
### Env vars I will need later
- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- storage bucket names to use for artifacts

I do not need these until the code path is ready for integration testing.

### When I will need you to run migrations
- After I generate and review the hosted migration sequence.
- Specifically at the hosted cutover step, when the Alembic migration chain is ready to run against the Supabase project.
- I do not need you to run anything yet.
