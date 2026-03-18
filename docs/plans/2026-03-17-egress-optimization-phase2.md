# Egress Optimization Phase 2: Architecture Changes

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce remaining Supabase egress by ~2GB/day via smarter caching, lazy-loading embeddings, and skip-if-unchanged background tasks.

**Architecture:** Three independent changes: (1) add user_id to digest cache keys for correctness, (2) two-phase query in MMR selection to avoid loading all embeddings, (3) guard background tasks with change-detection to skip no-op runs.

**Tech Stack:** Python/FastAPI/SQLAlchemy, NumPy, FAISS

---

## Task 1: Add user_id to Digest Cache Key

**Files:**
- Modify: `ai_news/app/api/routes_api.py:577`

**Context:** The `/digest/today` cache key is `api_digest_today:{date}:{locale}`. Since digest responses are personalized per user (via UserPref scores), the key must include user_id to avoid cross-user data leakage. Currently safe because there's only a public_user_id, but this is a correctness fix for future-proofing.

**Step 1: Update cache key to include user_id**

In `ai_news/app/api/routes_api.py` line 577, change:
```python
    cache_key = f"api_digest_today:{now.date().isoformat()}:{locale}"
```
to:
```python
    cache_key = f"api_digest_today:{settings.public_user_id}:{now.date().isoformat()}:{locale}"
```

The `settings` variable is already available (line 573: `settings = get_settings()`).

**Step 2: Verify no other references to old cache key pattern**

Search for `api_digest_today` in the codebase to check if any cache invalidation code references the old key pattern. If so, update it too.

**Step 3: Verify syntax**

Run: `cd "/Users/charleszheng/Desktop/Ideas/AI digest" && python3 -m py_compile ai_news/app/api/routes_api.py && echo "OK"`
Expected: `OK`

---

## Task 2: Lazy-Load Embeddings for Top-N MMR Candidates

**Files:**
- Modify: `ai_news/app/api/routes_api.py:257-410` (`_select_articles`)
- Modify: `ai_news/app/api/routes_api.py:413-510` (`_select_weekly_top`)
- Modify: `ai_news/app/api/routes_compat.py` (equivalent functions)
- Modify: `ai_news/app/api/routes_news.py:142-219` (`get_today`, `get_week`)

**Context:** Currently, `_select_articles()` loads ALL article embeddings (1.5KB each) from the DB, scores them, then passes ALL to MMR which selects the top 30. If there are 300 candidate articles, that's 450KB of embeddings transferred when only ~60 are needed.

The revised approach:
1. Query articles WITH `defer(Article.embedding)` — no embedding loaded
2. Score all candidates using user preferences (no embedding needed for scoring)
3. Take top 60 by rank_score (pre-filter)
4. Load embeddings ONLY for those 60 articles via a second targeted query
5. Run MMR on those 60 to select final 30

**Step 1: Restructure `_select_articles()` in routes_api.py**

In `ai_news/app/api/routes_api.py`, the function `_select_articles` (starting around line 257):

**1a.** Add `defer(Article.embedding)` to the query options at line 277:
```python
        .options(defer(Article.html), defer(Article.text), defer(Article.embedding), defer(Article.llm_reasoning))
```

**1b.** In the for-loop (line 301+), REMOVE the embedding decode and the `if embedding is None: continue` guard. Replace lines 357-359:
```python
        embedding = _decode_embedding_or_none(article.embedding)
        if embedding is None:
            continue
```
with nothing — just delete those 3 lines. The embedding is no longer accessed in the loop.

**1c.** Remove `"_embedding": embedding,` from the payload dict at line 385. Instead, store the article ID for later embedding lookup:
```python
            "_article_id": article.id,
```

**1d.** After scoring and sorting (after line 392: `items_sorted = sorted(...)`) but BEFORE MMR selection (line 393), insert the embedding loading phase:

```python
    # Lazy-load embeddings for top-N candidates only
    mmr_candidate_count = min(len(items_sorted), limit * 2)  # e.g., 60 for limit=30
    mmr_candidates = items_sorted[:mmr_candidate_count]
    if mmr_candidates:
        candidate_article_ids = [item["_article_id"] for item in mmr_candidates]
        embedding_rows = (
            db.query(Article.id, Article.embedding)
            .filter(Article.id.in_(candidate_article_ids))
            .all()
        )
        embedding_map = {}
        for art_id, raw_emb in embedding_rows:
            emb = _decode_embedding_or_none(raw_emb)
            if emb is not None:
                embedding_map[str(art_id)] = emb

        # Attach embeddings to candidates; drop any without valid embedding
        for item in mmr_candidates:
            item["_embedding"] = embedding_map.get(item["id"])
        mmr_candidates = [item for item in mmr_candidates if item["_embedding"] is not None]
```

**1e.** Change the MMR call at line 393 from:
```python
    selected = _safe_mmr_select(items_sorted, limit=limit, score_key="_rank_score")
```
to:
```python
    selected = _safe_mmr_select(mmr_candidates, limit=limit, score_key="_rank_score")
```

**1f.** In the serendipity section (line 396-402), the `global_candidates` filter draws from `items_sorted`. These items won't have `_embedding` set, but that's fine — serendipity items bypass MMR. Just ensure they don't break _safe_mmr_select by only being appended AFTER MMR.

**1g.** In the cleanup section (line 407-409), also pop `_article_id`:
```python
    for item in selected:
        item.pop("_embedding", None)
        item.pop("_rank_score", None)
        item.pop("_article_id", None)
```

**Step 2: Apply same restructure to `_select_weekly_top()` in routes_api.py**

Same pattern as Step 1, applied to the `_select_weekly_top` function (line 413+). The key differences:
- The query is at line 425-434
- The for-loop with embedding decode is at lines 439+
- Same lazy-load pattern: defer embedding, score without embedding, take top N, load embeddings for N only, run MMR

**Step 3: Apply same restructure to routes_compat.py equivalents**

Apply the same changes to:
- `_select_articles()` in routes_compat.py (equivalent lines ~265-400)
- `_select_weekly_top()` in routes_compat.py (equivalent lines ~405-510)

**Step 4: Apply to routes_news.py `get_today()` and `get_week()`**

These functions have the embedding pattern inline (not in a shared helper). Apply the same two-phase approach:
- `get_today()` at lines 142-219
- `get_week()` at lines 231-310

For each:
1. Add `defer(Article.embedding)` to query options
2. Remove `embedding = _decode_embedding_or_none(article.embedding)` and `if embedding is None: continue`
3. Remove `payload["_embedding"] = embedding`
4. Add `payload["_article_id"] = str(article.id)` instead
5. After sorting, load embeddings for top-N only
6. Run MMR on the enriched top-N
7. Clean up `_article_id` from response

**Step 5: Verify syntax**

Run:
```bash
cd "/Users/charleszheng/Desktop/Ideas/AI digest"
python3 -m py_compile ai_news/app/api/routes_api.py
python3 -m py_compile ai_news/app/api/routes_compat.py
python3 -m py_compile ai_news/app/api/routes_news.py
echo "ALL OK"
```
Expected: `ALL OK`

---

## Task 3: Skip-if-Unchanged Background Tasks

**Files:**
- Modify: `ai_news/app/tasks/pipeline.py:911-916` (`rebuild_faiss_index`)
- Modify: `ai_news/app/tasks/pipeline.py:1326-1400` (`run_relationship_inference`)
- Modify: `ai_news/app/clustering/cluster.py:15-16` (add tracking vars)

**Context:** Background tasks run on fixed intervals even when nothing has changed. Adding simple change-detection guards skips no-op runs.

### Step 1: Add change tracking to cluster.py

In `ai_news/app/clustering/cluster.py`, after line 16 (`LAST_BUILT_AT: datetime | None = None`), add:
```python
LAST_CLUSTER_COUNT: int = 0
```

In `rebuild_index()` (line 27), after `INDEX.rebuild(emb_matrix, ids)` (line 49), add:
```python
    global LAST_CLUSTER_COUNT
    LAST_CLUSTER_COUNT = len(ids)
```

### Step 2: Add skip guard to rebuild_faiss_index in pipeline.py

In `ai_news/app/tasks/pipeline.py`, modify `rebuild_faiss_index()` (line 911):

```python
def rebuild_faiss_index():
    from app.clustering.cluster import LAST_BUILT_AT, LAST_CLUSTER_COUNT, rebuild_index

    with session_scope() as session:
        # Skip rebuild if cluster count hasn't changed since last build
        from app.models import Cluster
        cutoff = utcnow() - timedelta(days=7)
        current_count = session.query(Cluster).filter(Cluster.last_seen_at >= cutoff).count()
        if LAST_BUILT_AT is not None and current_count == LAST_CLUSTER_COUNT:
            return  # No new clusters, skip rebuild
        rebuild_index(session, lookback_days=7)
```

### Step 3: Add skip guard to run_relationship_inference in pipeline.py

In `ai_news/app/tasks/pipeline.py`, at the start of `run_relationship_inference()` (line 1326), add a change-detection guard. Track the latest `last_seen_at` from clusters and skip if unchanged:

After the existing cluster query (lines 1344-1350), before the `if len(clusters) < 2:` check, add:

```python
        # Skip if no cluster changes since last run
        import hashlib
        cluster_fingerprint = hashlib.md5(
            ",".join(sorted(str(c.id) for c in clusters)).encode()
        ).hexdigest()
```

Then add a module-level variable at the top of the function scope or as a module global:
```python
_LAST_RELATIONSHIP_FINGERPRINT: str | None = None
```

And the skip check:
```python
        global _LAST_RELATIONSHIP_FINGERPRINT
        if cluster_fingerprint == _LAST_RELATIONSHIP_FINGERPRINT:
            log.info("run_relationship_inference: no cluster changes, skipping")
            return
        # ... existing code ...
        # At the end of the function, after successful completion:
        _LAST_RELATIONSHIP_FINGERPRINT = cluster_fingerprint
```

### Step 4: Verify entity-resolution runs before daily digest

In `ai_news/app/tasks/daily_digest.py`, the `run_daily_digest()` function (line 270) already calls `_refresh_entity_resolution(session)` at line 277. This is already correct — no change needed.

### Step 5: Verify syntax

Run:
```bash
cd "/Users/charleszheng/Desktop/Ideas/AI digest"
python3 -m py_compile ai_news/app/clustering/cluster.py
python3 -m py_compile ai_news/app/tasks/pipeline.py
echo "ALL OK"
```
Expected: `ALL OK`

---

## Verification Checklist

After all tasks:

1. `python3 -m py_compile` passes for all modified files
2. `npm run build` still succeeds (no Python changes affect frontend)
3. Cache key includes user_id: grep for `api_digest_today:` and verify format
4. `defer(Article.embedding)` is now present in `_select_articles` and `_select_weekly_top`
5. Embedding lazy-load queries use `Article.id.in_(candidate_article_ids)`
6. `LAST_CLUSTER_COUNT` is tracked and checked in `rebuild_faiss_index`
7. `_LAST_RELATIONSHIP_FINGERPRINT` is checked in `run_relationship_inference`
