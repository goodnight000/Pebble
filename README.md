<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# Run and deploy your AI Studio app

This contains everything you need to run your app locally.

View your app in AI Studio: https://ai.studio/apps/drive/1t19mAwD_0-2QYhHyR7aOnMCRsih56Uyi

## Run Locally

**Prerequisites:** Node.js, Python 3.11+


1. Install dependencies:
   `npm install`
2. Set `DATABASE_URL` to your Supabase Postgres target:
   - `export DATABASE_URL='postgresql+psycopg://...'`
3. (Optional) Set `OPENROUTER_API_KEY` or `OPENAI_API_KEY` for LLM-written digests + zh translation.
4. Run the app + backend:
   `npm run dev`

### Backend (Live Ingestion)
The backend runs on `http://localhost:8000` (FastAPI) and streams new items over SSE.

Required env vars:
- `DATABASE_URL` (must point at Supabase Postgres; SQLite URLs are not supported)

Optional env vars:
- `PY_API_PORT` (default 8000)
- `PUBLIC_USER_ID` (stable “default user” for `/api/*` endpoints)
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_STORAGE_ENABLED`
- `SUPABASE_STORAGE_BUCKET_DIGESTS`
- `SUPABASE_REALTIME_ENABLED`
- `SUPABASE_REALTIME_CHANNEL_URGENT`
- `SUPABASE_REALTIME_CHANNEL_CLUSTERS`
- `SUPABASE_REALTIME_CHANNEL_DIGESTS`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `LLM_PROVIDER` (`openai` or `openrouter`)
- `OPENROUTER_MODEL` / `OPENAI_MODEL`

The backend now runs `alembic upgrade head` during local startup, and the dev scripts no longer treat SQLite repair/bootstrap as the primary path.

### Hosted Setup
- Deployed environments also set `DATABASE_URL` to the Supabase/Postgres target.
- Run `alembic upgrade head` before app startup in hosted environments so the schema is current before FastAPI boots.
- Enable Supabase Storage and Realtime with feature flags after the database migration is complete and verified.
