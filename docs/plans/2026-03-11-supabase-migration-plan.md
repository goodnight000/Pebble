# Supabase Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate AIPulse to Supabase as the primary platform by moving the app to Supabase Postgres, adding backend-owned Supabase Storage for durable digest artifacts, and adding backend-published Supabase Realtime events with a safe frontend rollout path.

**Architecture:** Keep FastAPI as the control plane and only writer. Alembic becomes the sole schema authority, Supabase Postgres becomes the only primary relational database, Storage is limited to blob artifacts, and Realtime carries curated events rather than raw table subscriptions. Existing REST and SSE behavior remains available during rollout to reduce cutover risk.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic, psycopg, Supabase Postgres, Supabase Storage, Supabase Realtime, React 19, TypeScript, Vite.

---

### Task 1: Add failing tests for Supabase-first runtime assumptions

**Files:**
- Create: `ai_news/tests/test_supabase_runtime.py`
- Modify: `ai_news/app/config.py`
- Modify: `ai_news/app/api/main.py`
- Modify: `ai_news/app/db.py`

**Step 1: Write the failing test**
- Add backend tests that assert:
  - startup bootstrap does not call `Base.metadata.create_all()`
  - Supabase-related settings can be parsed from env
  - runtime fails fast when a Supabase feature flag is enabled without the required env vars
  - database bootstrap behavior no longer assumes SQLite-only defaults

**Step 2: Run test to verify it fails**
Run: `cd ai_news && ./.venv/bin/python -m unittest tests.test_supabase_runtime -v`
Expected: FAIL because current startup still calls `create_all()` and config does not yet expose Supabase integration settings.

**Step 3: Write minimal implementation**
- Add new settings fields for Supabase URL, anon key, service role key, bucket names, and feature flags.
- Extract startup bootstrap helpers so they can be tested directly.
- Remove implicit schema creation from the startup path.

**Step 4: Run test to verify it passes**
Run: `cd ai_news && ./.venv/bin/python -m unittest tests.test_supabase_runtime -v`
Expected: PASS.

### Task 2: Convert local runtime and scripts from SQLite-first to Alembic-first

**Files:**
- Modify: `scripts/dev.ts`
- Modify: `scripts/dev-ai.ts`
- Modify: `ai_news/app/db.py`
- Modify: `ai_news/alembic/env.py`
- Modify: `README.md`
- Modify: `CLAUDE.md`

**Step 1: Write the failing test**
- Extend `ai_news/tests/test_supabase_runtime.py` or add a second focused test module to assert:
  - local startup commands prefer `alembic upgrade head`
  - `DATABASE_URL` is treated as the canonical database target
  - SQLite repair/bootstrap commands are no longer the primary happy path

**Step 2: Run test to verify it fails**
Run: `cd ai_news && ./.venv/bin/python -m unittest tests.test_supabase_runtime -v`
Expected: FAIL because current dev scripts still default to SQLite and run a SQLite-specific repair script.

**Step 3: Write minimal implementation**
- Replace the schema repair/bootstrap step in the dev scripts with Alembic migration execution.
- Keep any SQLite compatibility only if required for isolated tests, not as the default app runtime.
- Update docs so local setup and hosted setup both describe Supabase/Postgres-first behavior.

**Step 4: Run verification**
Run: `cd ai_news && ./.venv/bin/python -m unittest tests.test_supabase_runtime -v`
Run: `npm run build`
Expected: PASS and successful frontend build.

### Task 3: Add a backend Supabase integration layer

**Files:**
- Create: `ai_news/app/integrations/supabase.py`
- Create: `ai_news/tests/test_supabase_integration.py`
- Modify: `ai_news/app/config.py`

**Step 1: Write the failing test**
- Add backend tests that assert:
  - the integration layer builds a backend client only when required env vars exist
  - service-role-only operations are not available when the service role key is absent
  - bucket and channel names resolve from settings predictably

**Step 2: Run test to verify it fails**
Run: `cd ai_news && ./.venv/bin/python -m unittest tests.test_supabase_integration -v`
Expected: FAIL because no Supabase integration layer exists yet.

**Step 3: Write minimal implementation**
- Add a small backend integration module that owns Supabase client creation and configuration checks.
- Keep all Supabase-specific logic behind narrow helper functions instead of spreading credentials and URL assembly across routes/tasks.

**Step 4: Run test to verify it passes**
Run: `cd ai_news && ./.venv/bin/python -m unittest tests.test_supabase_integration -v`
Expected: PASS.

### Task 4: Persist digest artifacts in Supabase Storage

**Files:**
- Create: `ai_news/app/services/digest_storage.py`
- Create: `ai_news/tests/test_digest_storage.py`
- Modify: `ai_news/app/tasks/daily_digest.py`
- Modify: `ai_news/app/models.py`
- Create: `ai_news/alembic/versions/0005_digest_storage_artifacts.py`

**Step 1: Write the failing test**
- Add tests that assert:
  - a digest payload can be serialized into an artifact body
  - storage upload metadata is returned in a stable format
  - `DailyDigest` rows can hold object reference metadata without breaking existing reads

**Step 2: Run test to verify it fails**
Run: `cd ai_news && ./.venv/bin/python -m unittest tests.test_digest_storage -v`
Expected: FAIL because no storage service or digest storage metadata exists yet.

**Step 3: Write minimal implementation**
- Add a migration that stores artifact reference fields on `daily_digests` such as bucket/path or equivalent minimal metadata.
- Persist generated digest artifacts to a private Supabase Storage bucket from the backend.
- Keep relational digest metadata in Postgres and avoid moving hot-path query data into Storage.

**Step 4: Run verification**
Run: `cd ai_news && ./.venv/bin/python -m unittest tests.test_digest_storage -v`
Run: `cd ai_news && ./.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS.

### Task 5: Publish curated backend events to Supabase Realtime

**Files:**
- Create: `ai_news/app/services/realtime_events.py`
- Create: `ai_news/tests/test_realtime_events.py`
- Modify: `ai_news/app/tasks/pipeline.py`
- Modify: `ai_news/app/tasks/daily_digest.py`
- Modify: `ai_news/app/api/routes_news.py`

**Step 1: Write the failing test**
- Add tests that assert:
  - `urgent_update`, `new_cluster`, and `digest_refresh` payloads are normalized and compact
  - disabled Realtime mode is a no-op
  - enabled Realtime mode calls the backend publisher helper with the expected channel/event contract

**Step 2: Run test to verify it fails**
Run: `cd ai_news && ./.venv/bin/python -m unittest tests.test_realtime_events -v`
Expected: FAIL because no Realtime service exists yet.

**Step 3: Write minimal implementation**
- Add a backend Realtime publisher service.
- Publish curated events from digest generation and live ingestion paths.
- Preserve existing SSE behavior so clients can continue to function during rollout.

**Step 4: Run verification**
Run: `cd ai_news && ./.venv/bin/python -m unittest tests.test_realtime_events -v`
Run: `cd ai_news && ./.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS.

### Task 6: Add a frontend Supabase Realtime client with safe fallback

**Files:**
- Create: `src/services/realtimeService.ts`
- Create: `scripts/test-realtime-service.ts`
- Modify: `src/services/aiService.ts`
- Modify: `src/App.tsx`
- Modify: `package.json`

**Step 1: Write the failing test**
- Add a small `tsx` verification script that asserts:
  - Realtime subscriptions are skipped cleanly when public Supabase env vars are absent
  - channel names and event mapping are stable
  - the service can coexist with the existing SSE-based feed updates

**Step 2: Run test to verify it fails**
Run: `./node_modules/.bin/tsx scripts/test-realtime-service.ts`
Expected: FAIL because no frontend Realtime service exists yet.

**Step 3: Write minimal implementation**
- Add `@supabase/supabase-js`.
- Add a narrow frontend Realtime service that subscribes only to the curated public channels.
- Keep `aiService.ts` and `App.tsx` compatible with the current API/SSE path when Realtime is unavailable or disabled.

**Step 4: Run verification**
Run: `./node_modules/.bin/tsx scripts/test-realtime-service.ts`
Run: `npm run build`
Expected: PASS and successful build.

### Task 7: Prepare the hosted cutover and operator runbook

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Create: `docs/plans/2026-03-11-supabase-cutover-runbook.md`

**Step 1: Write the failing test expectation**
- No code test is required here; the deliverable is a concrete operator runbook with exact env vars and command order.

**Step 2: Write minimal implementation**
- Document:
  - required env vars
  - local validation sequence
  - hosted migration command
  - rollback posture
  - feature-flag order for enabling Storage and Realtime

**Step 3: Stop for operator input**
- Ask the user for:
  - `DATABASE_URL`
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY`
  - `SUPABASE_SERVICE_ROLE_KEY`
  - chosen bucket names
- Ask the user to run the hosted migration command only after the migration files are reviewed.

### Task 8: Final review and full verification

**Files:**
- Review: `ai_news/app/config.py`
- Review: `ai_news/app/db.py`
- Review: `ai_news/app/api/main.py`
- Review: `ai_news/app/tasks/daily_digest.py`
- Review: `ai_news/app/tasks/pipeline.py`
- Review: `ai_news/app/services/digest_storage.py`
- Review: `ai_news/app/services/realtime_events.py`
- Review: `src/services/realtimeService.ts`
- Review: `src/services/aiService.ts`
- Review: `src/App.tsx`

**Step 1: Request code review**
- Use a review pass focused on migration safety, startup regressions, secret handling, and fallback behavior.

**Step 2: Apply fixes**
- Fix important findings before cutover.

**Step 3: Final verification**
Run: `cd ai_news && ./.venv/bin/python -m unittest discover -s tests -v`
Run: `./node_modules/.bin/tsx scripts/test-realtime-service.ts`
Run: `npm run build`
Expected: PASS across backend tests, Realtime service verification, and frontend build.

### Hosted migration hand-off

I will need your Supabase env vars at the start of Task 7, not earlier.

I will need you to run the hosted migration command after Task 7 is complete and after we review the generated Alembic migration files together. The expected hosted command will be this shape:

Run: `cd ai_news && DATABASE_URL='<your-supabase-db-url>' ./.venv/bin/alembic upgrade head`

If you prefer using the Supabase SQL editor instead of a direct DB connection, I will adapt the hand-off at that point.
