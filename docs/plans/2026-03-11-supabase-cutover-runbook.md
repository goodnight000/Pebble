# Supabase Cutover Runbook

**Goal:** Cut AIPulse over to Supabase-backed Postgres, then enable Supabase Storage and Realtime in a controlled order with rollback points between each step.

## Required Environment Variables
- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`

## Feature Flags and Optional Variables
- `SUPABASE_STORAGE_ENABLED`
- `SUPABASE_STORAGE_BUCKET_DIGESTS`
- `SUPABASE_REALTIME_ENABLED`
- `SUPABASE_REALTIME_CHANNEL_URGENT`
- `SUPABASE_REALTIME_CHANNEL_CLUSTERS`
- `SUPABASE_REALTIME_CHANNEL_DIGESTS`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

## Recommended Initial Values
- `SUPABASE_STORAGE_ENABLED=false`
- `SUPABASE_REALTIME_ENABLED=false`
- `SUPABASE_STORAGE_BUCKET_DIGESTS=digests`
- `SUPABASE_REALTIME_CHANNEL_URGENT=urgent_update`
- `SUPABASE_REALTIME_CHANNEL_CLUSTERS=new_cluster`
- `SUPABASE_REALTIME_CHANNEL_DIGESTS=digest_refresh`

## Local Validation Sequence
1. Export the backend database target:
   - `export DATABASE_URL='postgresql+psycopg://...your-supabase-or-local-postgres...'`
2. Export Supabase backend/browser config if testing Storage or Realtime:
   - `export SUPABASE_URL='https://<project-ref>.supabase.co'`
   - `export SUPABASE_ANON_KEY='...'`
   - `export SUPABASE_SERVICE_ROLE_KEY='...'`
   - `export VITE_SUPABASE_URL="$SUPABASE_URL"`
   - `export VITE_SUPABASE_ANON_KEY="$SUPABASE_ANON_KEY"`
   - If this is a production/frontend build, set the `VITE_*` variables before `npm run build`
3. Keep feature flags off for the first DB validation:
   - `export SUPABASE_STORAGE_ENABLED='false'`
   - `export SUPABASE_REALTIME_ENABLED='false'`
4. Run local verification:
   - `cd ai_news && ./.venv/bin/python -m unittest discover -s tests -v`
   - `cd .. && ./node_modules/.bin/tsx scripts/test-realtime-service.ts`
   - `npm run build`
5. Start the app:
   - `npm run dev`

## Hosted Migration Command
Run this before starting the hosted app process:

```bash
cd ai_news && DATABASE_URL='<your-supabase-db-url>' ./.venv/bin/alembic upgrade head
```

## Enablement Order
1. Database only
   - Set `DATABASE_URL`
   - Run Alembic
   - Start app with `SUPABASE_STORAGE_ENABLED=false` and `SUPABASE_REALTIME_ENABLED=false`
2. Storage
   - Create a private Supabase Storage bucket named `digests` first, or set `SUPABASE_STORAGE_BUCKET_DIGESTS` to the bucket you created
   - Set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_STORAGE_BUCKET_DIGESTS`
   - Turn on `SUPABASE_STORAGE_ENABLED=true`
   - Verify `daily_digests.storage_bucket` and `daily_digests.storage_path` are populated for new digests
3. Realtime
   - Set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`
   - Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`
   - Rebuild/restart the frontend after changing `VITE_*` values
   - Turn on `SUPABASE_REALTIME_ENABLED=true`
   - Verify `/api/news/realtime/config` returns enabled channel names
   - Verify frontend receives curated Realtime updates or cleanly falls back to SSE

## Rollback Posture
- If the database migration fails:
  - stop deployment
  - keep old runtime pointed at the previous database target
- If Storage causes issues:
  - set `SUPABASE_STORAGE_ENABLED=false`
  - keep database cutover in place
- If Realtime causes issues:
  - set `SUPABASE_REALTIME_ENABLED=false`
  - frontend will continue on SSE fallback

## Operator Checks
- `alembic upgrade head` completes cleanly
- app startup succeeds without `create_all()`
- `/v1/health` responds
- `/api/digest/today` responds
- `/api/news/realtime/config` matches expected flags and channel names
- new digests populate `storage_bucket` and `storage_path` when storage is enabled
- urgent and digest events appear in Realtime when enabled
