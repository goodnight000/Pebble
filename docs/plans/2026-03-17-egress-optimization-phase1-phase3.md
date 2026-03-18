# Egress Optimization: Phase 1 (Backend) + Phase 3 (Frontend) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce Supabase PostgreSQL egress from ~10GB/day to ~3GB/day via surgical backend query optimizations and frontend polling improvements.

**Architecture:** Phase 1 adds SQLAlchemy `defer()` to large columns in hot-path queries and slows aggressive polling intervals. Phase 3 wires the existing Supabase Realtime subscription into React state so the 30-min polling fallback can be extended to 5 minutes.

**Tech Stack:** Python/FastAPI/SQLAlchemy (backend), React/TypeScript (frontend), Supabase Realtime

---

## Phase 1: Backend API Fixes

### Task 1: SSE Polling Interval 15s → 60s

**Files:**
- Modify: `ai_news/app/api/routes_api.py:920`
- Modify: `ai_news/app/api/routes_compat.py` (equivalent SSE sleep line)

**Step 1: Change sleep interval in routes_api.py**

In `ai_news/app/api/routes_api.py` line 920, change:
```python
            await asyncio.sleep(15)
```
to:
```python
            await asyncio.sleep(60)
```

**Step 2: Change sleep interval in routes_compat.py**

Find the equivalent `asyncio.sleep(15)` in the SSE endpoint in `ai_news/app/api/routes_compat.py` (around line 670-690 area) and change to `asyncio.sleep(60)`.

**Step 3: Verify both files compile**

Run: `cd /Users/charleszheng/Desktop/Ideas/AI\ digest && python -c "import ai_news.app.api.routes_api; import ai_news.app.api.routes_compat; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add ai_news/app/api/routes_api.py ai_news/app/api/routes_compat.py
git commit -m "perf: increase SSE polling interval from 15s to 60s to reduce egress"
```

---

### Task 2: Defer `DailyDigest.longform_html` in Non-Longform Queries

**Files:**
- Modify: `ai_news/app/api/routes_api.py:601-608`
- Modify: `ai_news/app/api/routes_compat.py:563-570`
- Modify: `ai_news/app/tasks/daily_digest.py:314-321`

**Context:** The `longform_html` column (added in migration 0007) stores 2-10MB of rendered HTML per row. Three queries fetch DailyDigest without deferring this column, but none of them access `longform_html`. Two other queries (routes_api.py:738 for `/digest/daily` and daily_digest.py:396 for longform update) DO read `longform_html` and must NOT be deferred.

**Step 1: Add defer to `/digest/today` in routes_api.py**

In `ai_news/app/api/routes_api.py`, the query at line 601-608:
```python
    stored_rows = (
        db.query(DailyDigest)
        .filter(
            DailyDigest.user_id == settings.public_user_id,
            func.date(DailyDigest.date) == now.date(),
            DailyDigest.content_type.in_(content_types),
        )
        .all()
    )
```

Change to:
```python
    stored_rows = (
        db.query(DailyDigest)
        .options(defer(DailyDigest.longform_html))
        .filter(
            DailyDigest.user_id == settings.public_user_id,
            func.date(DailyDigest.date) == now.date(),
            DailyDigest.content_type.in_(content_types),
        )
        .all()
    )
```

Ensure `defer` is already imported from `sqlalchemy.orm` at the top of the file (it is — used on Article columns).

**Step 2: Add defer to `/digest/today` in routes_compat.py**

In `ai_news/app/api/routes_compat.py`, the equivalent query at line 563-570:
```python
    stored_rows = (
        db.query(DailyDigest)
        .filter(
            DailyDigest.user_id == settings.public_user_id,
            func.date(DailyDigest.date) == now.date(),
            DailyDigest.content_type.in_(content_types),
        )
        .all()
    )
```

Change to:
```python
    stored_rows = (
        db.query(DailyDigest)
        .options(defer(DailyDigest.longform_html))
        .filter(
            DailyDigest.user_id == settings.public_user_id,
            func.date(DailyDigest.date) == now.date(),
            DailyDigest.content_type.in_(content_types),
        )
        .all()
    )
```

**Step 3: Add defer to existence check in daily_digest.py**

In `ai_news/app/tasks/daily_digest.py`, the query at line 314-321:
```python
                existing = (
                    session.query(DailyDigest)
                    .filter(
                        DailyDigest.user_id == user.id,
                        func.date(DailyDigest.date) == now.date(),
                        DailyDigest.content_type == ct,
                    )
                    .first()
                )
```

Change to:
```python
                existing = (
                    session.query(DailyDigest)
                    .options(defer(DailyDigest.longform_html))
                    .filter(
                        DailyDigest.user_id == user.id,
                        func.date(DailyDigest.date) == now.date(),
                        DailyDigest.content_type == ct,
                    )
                    .first()
                )
```

Ensure `defer` is imported from `sqlalchemy.orm` at the top of `daily_digest.py`. If not, add it to the existing import line.

**Step 4: Verify — DO NOT defer in these two queries**

Confirm these queries are LEFT UNCHANGED:
- `ai_news/app/api/routes_api.py:737-744` — `/digest/daily` endpoint reads `row.longform_html` at line 758
- `ai_news/app/tasks/daily_digest.py:396-403` — longform upsert reads `existing_lf.longform_html` at line 409

**Step 5: Verify imports compile**

Run: `cd /Users/charleszheng/Desktop/Ideas/AI\ digest && python -c "from ai_news.app.api.routes_api import router; from ai_news.app.api.routes_compat import router; from ai_news.app.tasks.daily_digest import run_daily_digest; print('OK')"`
Expected: `OK`

**Step 6: Commit**

```bash
git add ai_news/app/api/routes_api.py ai_news/app/api/routes_compat.py ai_news/app/tasks/daily_digest.py
git commit -m "perf: defer DailyDigest.longform_html in queries that don't need it"
```

---

### Task 3: Defer `Article.embedding` in Non-MMR API Queries

**Files:**
- Modify: `ai_news/app/api/routes_api.py:276` (add embedding defer to `_select_articles`)
- Modify: `ai_news/app/api/routes_api.py:430` (add embedding defer to `_select_weekly_top`)
- Modify: `ai_news/app/api/routes_compat.py:277` (equivalent `_select_articles`)
- Modify: `ai_news/app/api/routes_compat.py:412` (equivalent `_select_weekly_top`)
- Modify: `ai_news/app/api/routes_news.py:151` (`/v1/news/today`)
- Modify: `ai_news/app/api/routes_news.py:243` (`/v1/news/week`)

**Context:** These queries currently defer `Article.html` and `Article.llm_reasoning` but NOT `Article.embedding` (1.5KB per row). However, the downstream code in `_select_articles` and the v1/news endpoints DO use `article.embedding` for MMR diversity selection. So we CANNOT simply defer it in these queries without breaking MMR.

**IMPORTANT — REVISED APPROACH:** Since `_select_articles()`, `_select_weekly_top()`, and the v1/news endpoints all use `article.embedding` for MMR, we CANNOT defer embedding in these queries. Instead, we should defer `Article.text` (which is NOT deferred in some of these queries but is never used in the API response building).

**Step 1: Add `defer(Article.text)` to `_select_articles` in routes_api.py**

In `ai_news/app/api/routes_api.py` line 276, the current options:
```python
        .options(defer(Article.html), defer(Article.llm_reasoning))
```

Change to:
```python
        .options(defer(Article.html), defer(Article.text), defer(Article.llm_reasoning))
```

**Step 2: Add `defer(Article.text)` to `_select_weekly_top` in routes_api.py**

In `ai_news/app/api/routes_api.py` line 430, the current options:
```python
        .options(defer(Article.html), defer(Article.llm_reasoning))
```

Change to:
```python
        .options(defer(Article.html), defer(Article.text), defer(Article.llm_reasoning))
```

**Step 3: Repeat for routes_compat.py**

Apply the same `defer(Article.text)` addition to:
- `ai_news/app/api/routes_compat.py:277` — `.options(defer(Article.html), defer(Article.llm_reasoning))`
- `ai_news/app/api/routes_compat.py:412` — `.options(defer(Article.html), defer(Article.llm_reasoning))`

**Step 4: Add `defer(Article.text)` to routes_news.py `/v1/news/today`**

In `ai_news/app/api/routes_news.py` line 151:
```python
        .options(defer(Article.html), defer(Article.llm_reasoning))
```

Change to:
```python
        .options(defer(Article.html), defer(Article.text), defer(Article.llm_reasoning))
```

**Step 5: Add `defer(Article.text)` to routes_news.py `/v1/news/week`**

In `ai_news/app/api/routes_news.py` line 243:
```python
        .options(defer(Article.html), defer(Article.llm_reasoning))
```

Change to:
```python
        .options(defer(Article.html), defer(Article.text), defer(Article.llm_reasoning))
```

**Step 6: Verify — these queries already defer embedding (no change needed)**

Confirm these are already correct:
- `routes_api.py:843` — SSE endpoint already defers `Article.embedding` ✓
- `routes_compat.py:681` — SSE compat already defers `Article.embedding` ✓
- `routes_news.py:322` — `/v1/news/urgent` already defers `Article.text` and `Article.embedding` ✓
- `routes_graph.py:215` — graph endpoint already defers `Article.embedding` ✓
- `routes_graph.py:460` — topic-trends already defers `Article.embedding` ✓

**Step 7: Verify compile**

Run: `cd /Users/charleszheng/Desktop/Ideas/AI\ digest && python -c "from ai_news.app.api.routes_api import router; from ai_news.app.api.routes_compat import router; from ai_news.app.api.routes_news import router; print('OK')"`
Expected: `OK`

**Step 8: Commit**

```bash
git add ai_news/app/api/routes_api.py ai_news/app/api/routes_compat.py ai_news/app/api/routes_news.py
git commit -m "perf: defer Article.text in API queries that never use full text content"
```

---

### Task 4: Defer `Article.embedding` in Signal Map Endpoint

**Files:**
- Modify: `ai_news/app/api/routes_signal_map.py:201-207`

**Context:** The signal map endpoint batch-loads member articles without deferring `Article.embedding`. The PCA projection at line 289 uses `cluster.centroid_embedding`, not per-article embeddings. The article data is only used for building article payload dicts (id, title, url, source, score, trust_label, event_type, summary at lines 270-283).

**Step 1: Add defer to member_rows query**

In `ai_news/app/api/routes_signal_map.py` lines 201-207:
```python
    member_rows = (
        db.query(ClusterMember, Article, RawItem, Source)
        .join(Article, ClusterMember.article_id == Article.id)
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .join(Source, RawItem.source_id == Source.id)
        .filter(ClusterMember.cluster_id.in_(cluster_ids))
        .all()
    )
```

Change to:
```python
    member_rows = (
        db.query(ClusterMember, Article, RawItem, Source)
        .join(Article, ClusterMember.article_id == Article.id)
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .join(Source, RawItem.source_id == Source.id)
        .options(defer(Article.html), defer(Article.text), defer(Article.embedding), defer(Article.llm_reasoning))
        .filter(ClusterMember.cluster_id.in_(cluster_ids))
        .all()
    )
```

Ensure `defer` is imported from `sqlalchemy.orm` at the top of the file. Check if it's already imported; if not, add it.

**Step 2: Verify compile**

Run: `cd /Users/charleszheng/Desktop/Ideas/AI\ digest && python -c "from ai_news.app.api.routes_signal_map import router; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add ai_news/app/api/routes_signal_map.py
git commit -m "perf: defer large Article columns in signal map member query"
```

---

### Task 5: Reduce Background Task Intervals

**Files:**
- Modify: `ai_news/app/tasks/inline_scheduler.py:101-112`

**Step 1: Update intervals**

In `ai_news/app/tasks/inline_scheduler.py`, change lines 105, 107, 109, 112:

From:
```python
    loop.create_task(_run_periodic("sitemap-poll", 1800.0, run_sitemap_poll, initial_delay=75))
    ...
    loop.create_task(_run_periodic("social-poll", 1800.0, run_social_poll, initial_delay=135))
    ...
    loop.create_task(_run_periodic("rebuild-faiss", 1800.0, rebuild_faiss_index, initial_delay=15))
    ...
    loop.create_task(_run_periodic("relationship-inference", 3600.0, run_relationship_inference, initial_delay=210))
```

To:
```python
    loop.create_task(_run_periodic("sitemap-poll", 3600.0, run_sitemap_poll, initial_delay=75))
    ...
    loop.create_task(_run_periodic("social-poll", 3600.0, run_social_poll, initial_delay=135))
    ...
    loop.create_task(_run_periodic("rebuild-faiss", 3600.0, rebuild_faiss_index, initial_delay=15))
    ...
    loop.create_task(_run_periodic("relationship-inference", 10800.0, run_relationship_inference, initial_delay=210))
```

Summary of changes:
- `sitemap-poll`: 1800 → 3600 (30min → 1hr)
- `social-poll`: 1800 → 3600 (30min → 1hr)
- `rebuild-faiss`: 1800 → 3600 (30min → 1hr)
- `relationship-inference`: 3600 → 10800 (1hr → 3hr)

Leave unchanged: `priority-poll` (300s), `normal-poll` (3600s), `arxiv-poll` (10800s), `github-poll` (21600s), `twitter-poll` (10800s), `urgent-notify` (300s), `entity-resolution` (21600s), `daily-digest` (daily at 6AM).

**Step 2: Verify compile**

Run: `cd /Users/charleszheng/Desktop/Ideas/AI\ digest && python -c "from ai_news.app.tasks.inline_scheduler import start_scheduler; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add ai_news/app/tasks/inline_scheduler.py
git commit -m "perf: reduce background task frequencies to lower DB egress"
```

---

## Phase 3: Frontend Fixes

### Task 6: Wire Realtime Subscription to App State

**Files:**
- Modify: `src/App.tsx:126-133`

**Context:** The `AIService.subscribe()` method (aiService.ts:107-170) is fully implemented and handles both Supabase Realtime and SSE fallback. However, it is NEVER called from `App.tsx`. The app currently relies solely on `setInterval` polling every 30 minutes. We need to:
1. Call `aiService.subscribe()` to connect realtime events to `setDigest`
2. Reduce the polling interval from 30min to 5min as an absolute fallback
3. Keep the initial `loadNewsForLocale(language)` call for first load

**Step 1: Update the useEffect in App.tsx**

In `src/App.tsx`, replace lines 126-133:
```typescript
  useEffect(() => {
    void loadNewsForLocale(language);
    const intervalId = window.setInterval(() => {
      void loadNewsForLocale(language);
    }, DIGEST_REFRESH_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [language, loadNewsForLocale]);
```

With:
```typescript
  useEffect(() => {
    void loadNewsForLocale(language);

    const unsubscribe = aiService.subscribe((event) => {
      if (event.type === 'digest') {
        setDigest(event.data);
        setLastUpdated(new Date());
      }
    });

    // Fallback polling in case realtime and SSE both fail silently
    const intervalId = window.setInterval(() => {
      void loadNewsForLocale(language);
    }, DIGEST_REFRESH_INTERVAL_MS);

    return () => {
      unsubscribe();
      window.clearInterval(intervalId);
    };
  }, [language, loadNewsForLocale, aiService]);
```

**Step 2: Update the polling constant**

In `src/App.tsx` line 30, change:
```typescript
const DIGEST_REFRESH_INTERVAL_MS = 30 * 60 * 1000;
```

To:
```typescript
const DIGEST_REFRESH_INTERVAL_MS = 5 * 60 * 1000;
```

**Step 3: Verify TypeScript compiles**

Run: `cd /Users/charleszheng/Desktop/Ideas/AI\ digest && npx tsc --noEmit`
Expected: No errors

**Step 4: Verify build succeeds**

Run: `cd /Users/charleszheng/Desktop/Ideas/AI\ digest && npm run build`
Expected: Build succeeds

**Step 5: Commit**

```bash
git add src/App.tsx
git commit -m "perf: wire realtime subscription to App state, reduce fallback polling to 5min"
```

---

### Task 7: Add Cache-Control Headers to Digest Endpoints

**Files:**
- Modify: `ai_news/app/api/routes_api.py` — `/digest/today` and `/digest/archive` endpoints

**Context:** Adding `Cache-Control: max-age=300` tells the browser to serve cached responses for 5 minutes without making a network request. This is handled natively by browsers — no frontend code changes needed.

**Step 1: Add Cache-Control to `/digest/today` response**

In `ai_news/app/api/routes_api.py`, the `/digest/today` endpoint currently returns a dict (which FastAPI serializes as JSON). We need to wrap it in a `JSONResponse` with a `Cache-Control` header.

Find the function signature (around line 540-570) and the return at line 668-669. At the import section of the file, ensure `JSONResponse` is imported:
```python
from fastapi.responses import JSONResponse
```

Then change the return at line 668-669 from:
```python
    set_cached(cache_key, response, ttl=60 * 60 * 2)
    return response
```

To:
```python
    set_cached(cache_key, response, ttl=60 * 60 * 2)
    return JSONResponse(content=response, headers={"Cache-Control": "public, max-age=300"})
```

Also find the early cache-hit return (around line 576-579 area) and wrap it similarly:
```python
    if cached:
        return JSONResponse(content=cached, headers={"Cache-Control": "public, max-age=300"})
```

**Step 2: Add Cache-Control to `/digest/archive` response**

Find the `/digest/archive` endpoint return and wrap similarly with `Cache-Control: public, max-age=300`.

**Step 3: Verify compile**

Run: `cd /Users/charleszheng/Desktop/Ideas/AI\ digest && python -c "from ai_news.app.api.routes_api import router; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add ai_news/app/api/routes_api.py
git commit -m "perf: add Cache-Control headers to digest endpoints for browser caching"
```

---

## Verification Checklist

After all tasks are complete, verify:

1. **Backend compiles:** `python -c "from ai_news.app.api.main import app; print('OK')"`
2. **Frontend builds:** `npm run build`
3. **SSE interval:** Confirm `asyncio.sleep(60)` in both routes_api.py and routes_compat.py
4. **Deferred columns:** Grep for `defer(` in all route files to confirm correct placement
5. **Scheduler intervals:** Confirm new values in inline_scheduler.py
6. **Realtime wired:** Confirm `aiService.subscribe()` is called in App.tsx useEffect
7. **Polling interval:** Confirm `DIGEST_REFRESH_INTERVAL_MS = 5 * 60 * 1000` in App.tsx
8. **No regressions:** Run `npm run dev` and verify the app loads, shows digest, and refreshes
