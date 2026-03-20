"""Source-level verification tests for egress optimization changes.

These tests read the actual source files and verify that the correct
patterns (deferred columns, lazy-load embeddings, polling intervals,
cache headers, skip-if-unchanged guards, etc.) are present. No running
database is required.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.abspath("ai_news"))

# Set DATABASE_URL before any app imports that trigger engine creation.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _read_source(relative_path: str) -> str:
    """Read a source file relative to project root."""
    full_path = os.path.join(PROJECT_ROOT, relative_path)
    with open(full_path, "r") as f:
        return f.read()


# Preload sources used across multiple test classes.
_ROUTES_API = _read_source("ai_news/app/api/routes_api.py")
_ROUTES_COMPAT = _read_source("ai_news/app/api/routes_compat.py")
_ROUTES_SIGNAL_MAP = _read_source("ai_news/app/api/routes_signal_map.py")
_PIPELINE = _read_source("ai_news/app/tasks/pipeline.py")
_INLINE_SCHEDULER = _read_source("ai_news/app/tasks/inline_scheduler.py")
_APP_TSX = _read_source("src/App.tsx")
_DAILY_DIGEST_PAGE = _read_source("src/components/DailyDigestPage.tsx")


# ===================================================================
# 1. Deferred columns are configured correctly
# ===================================================================


class TestDeferredColumns(unittest.TestCase):
    """Verify that SQLAlchemy defer() calls target the right columns in the
    right query sites."""

    def test_select_articles_uses_load_only(self):
        """_select_articles must use load_only() to whitelist columns,
        which implicitly excludes html, text, embedding, and llm_reasoning."""
        select_fn = _ROUTES_API[_ROUTES_API.index("def _select_articles"):]
        select_fn = select_fn[:select_fn.index("\ndef _select_weekly_top")]
        self.assertIn(
            "load_only(",
            select_fn,
            "routes_api._select_articles should use load_only()",
        )
        # Verify key columns are included in the .options() block
        options_start = select_fn.index(".options(")
        options_end = select_fn.index(".filter(", options_start)
        options_block = select_fn[options_start:options_end]
        for col in ("Article.id", "Article.final_url", "Article.summary",
                     "Article.event_type", "Article.topics", "Article.entities"):
            self.assertIn(
                col,
                options_block,
                f"routes_api._select_articles load_only must include {col}",
            )
        # Verify large columns are NOT in load_only options block
        for col in ("Article.html", "Article.text", "Article.embedding", "Article.llm_reasoning"):
            self.assertNotIn(
                col,
                options_block,
                f"routes_api._select_articles options must NOT include {col}",
            )

    def test_sse_endpoint_uses_load_only(self):
        """The SSE /stream endpoint must use load_only() to whitelist columns."""
        sse_section = _ROUTES_API[_ROUTES_API.index("async def compat_stream"):]
        self.assertIn(
            "load_only(",
            sse_section,
            "SSE endpoint query must use load_only()",
        )
        # Verify large columns are NOT referenced in the SSE query options
        # (they should be excluded by load_only whitelist)
        for col in ("Article.html", "Article.text", "Article.embedding", "Article.llm_reasoning"):
            self.assertNotIn(
                col,
                sse_section,
                f"SSE endpoint must NOT include {col} in load_only",
            )

    def test_signal_map_defers_all_large_cols(self):
        """routes_signal_map member_rows query must defer html, text,
        embedding, and llm_reasoning."""
        for col in ("Article.html", "Article.text", "Article.embedding", "Article.llm_reasoning"):
            self.assertIn(
                f"defer({col})",
                _ROUTES_SIGNAL_MAP,
                f"Signal map member_rows query must defer {col}",
            )

    def test_digest_today_defers_longform_html(self):
        """/digest/today should defer DailyDigest.longform_html so it is not
        loaded when only headline + executive_summary are needed."""
        # Look for the pattern in the compat_digest_today function
        digest_today_section = _ROUTES_API[_ROUTES_API.index("def compat_digest_today"):]
        digest_today_section = digest_today_section[:digest_today_section.index("\n@router.")]
        self.assertIn(
            "defer(DailyDigest.longform_html)",
            digest_today_section,
            "/digest/today must defer DailyDigest.longform_html",
        )

    def test_digest_daily_does_NOT_defer_longform_html(self):
        """/digest/daily reads longform_html, so it must NOT defer it."""
        digest_daily_section = _ROUTES_API[_ROUTES_API.index("def digest_daily"):]
        # Cut to next route or end of file
        next_route = digest_daily_section.find("\n@router.", 1)
        if next_route != -1:
            digest_daily_section = digest_daily_section[:next_route]
        self.assertNotIn(
            "defer(DailyDigest.longform_html)",
            digest_daily_section,
            "/digest/daily must NOT defer DailyDigest.longform_html (it reads it)",
        )

    def test_compat_select_articles_uses_load_only(self):
        """routes_compat._select_articles must use load_only() to whitelist columns."""
        select_fn = _ROUTES_COMPAT[_ROUTES_COMPAT.index("def _select_articles"):]
        select_fn = select_fn[:select_fn.index("\ndef _select_weekly_top")]
        self.assertIn(
            "load_only(",
            select_fn,
            "routes_compat._select_articles should use load_only()",
        )
        # Scope to the .options() block only (lazy-load query uses Article.embedding separately)
        options_start = select_fn.index(".options(")
        options_end = select_fn.index(".filter(", options_start)
        options_block = select_fn[options_start:options_end]
        for col in ("Article.html", "Article.text", "Article.embedding", "Article.llm_reasoning"):
            self.assertNotIn(
                col,
                options_block,
                f"routes_compat._select_articles options must NOT include {col}",
            )

    def test_compat_sse_uses_load_only(self):
        """routes_compat SSE endpoint must use load_only() to whitelist columns."""
        sse_section = _ROUTES_COMPAT[_ROUTES_COMPAT.index("async def compat_stream"):]
        self.assertIn(
            "load_only(",
            sse_section,
            "routes_compat SSE endpoint must use load_only()",
        )
        for col in ("Article.html", "Article.text", "Article.embedding", "Article.llm_reasoning"):
            self.assertNotIn(
                col,
                sse_section,
                f"routes_compat SSE endpoint must NOT include {col} in load_only",
            )


# ===================================================================
# 2. Lazy-load embedding pattern
# ===================================================================


class TestLazyLoadEmbeddings(unittest.TestCase):
    """Verify the lazy-load embedding pattern: payloads store _article_id
    instead of embedding, and embeddings are loaded in a separate query
    for top-N MMR candidates only."""

    def test_select_articles_stores_article_id_not_embedding(self):
        """The payload dict should have '_article_id' but NOT '_embedding'
        assigned directly from the Article object in the initial loop."""
        # Find the payload dict construction in _select_articles
        select_fn = _ROUTES_API[_ROUTES_API.index("def _select_articles"):]
        select_fn = select_fn[:select_fn.index("\ndef _select_weekly_top")]
        self.assertIn(
            '"_article_id": article.id',
            select_fn,
            "Payload must include _article_id for deferred embedding lookup",
        )
        # The initial payload dict should NOT have _embedding
        # (it's added later from the lazy-load query)
        payload_block_start = select_fn.index("payload = {")
        payload_block_end = select_fn.index("}", payload_block_start + len("payload = {"))
        payload_block = select_fn[payload_block_start:payload_block_end]
        self.assertNotIn(
            '"_embedding": ',
            payload_block,
            "Initial payload should NOT include _embedding (it is lazy-loaded later)",
        )

    def test_select_articles_has_lazy_load_query(self):
        """Verify the lazy-load embedding query pattern exists:
        db.query(Article.id, Article.embedding).filter(Article.id.in_(candidate_article_ids))"""
        self.assertIn(
            "db.query(Article.id, Article.embedding)",
            _ROUTES_API,
            "Lazy-load embedding query must select Article.id and Article.embedding",
        )
        self.assertIn(
            "Article.id.in_(candidate_article_ids)",
            _ROUTES_API,
            "Lazy-load embedding query must filter by candidate_article_ids",
        )

    def test_select_articles_cleans_up_article_id(self):
        """After MMR selection, _article_id must be popped from results."""
        self.assertIn(
            'item.pop("_article_id", None)',
            _ROUTES_API,
            "_article_id must be cleaned up from final results",
        )

    def test_mmr_receives_mmr_candidates_not_items_sorted(self):
        """_safe_mmr_select must receive mmr_candidates (filtered top-N)
        rather than all items_sorted."""
        self.assertRegex(
            _ROUTES_API,
            r"_safe_mmr_select\(\s*mmr_candidates\s*,",
            "_safe_mmr_select must be called with mmr_candidates, not items_sorted",
        )

    def test_compat_has_lazy_load_pattern(self):
        """routes_compat should also use the lazy-load embedding pattern."""
        self.assertIn(
            "db.query(Article.id, Article.embedding)",
            _ROUTES_COMPAT,
            "routes_compat must also lazy-load embeddings",
        )
        self.assertIn(
            'item.pop("_article_id", None)',
            _ROUTES_COMPAT,
            "routes_compat must clean up _article_id",
        )


# ===================================================================
# 3. Summary fallback doesn't access article.text
# ===================================================================


class TestSummaryFallback(unittest.TestCase):
    """Verify that display routes use the shared blurb helper and do not
    lazy-load article.text in API handlers."""

    def test_no_article_text_fallback_in_routes_api(self):
        """routes_api.py must not contain article.text[:240] as a summary
        fallback (article.text is deferred)."""
        self.assertNotIn(
            "article.text[:240]",
            _ROUTES_API,
            "routes_api must not access article.text[:240] (text is deferred)",
        )

    def test_no_article_text_fallback_in_routes_compat(self):
        """routes_compat.py must not contain article.text[:240] as a summary
        fallback (article.text is deferred)."""
        self.assertNotIn(
            "article.text[:240]",
            _ROUTES_COMPAT,
            "routes_compat must not access article.text[:240] (text is deferred)",
        )

    def test_summary_uses_shared_blurb_helper(self):
        """Summary fallback should be delegated to build_article_blurb()."""
        pattern = "build_article_blurb("
        self.assertIn(
            pattern,
            _ROUTES_API,
            "routes_api summary must use build_article_blurb()",
        )
        self.assertIn(
            pattern,
            _ROUTES_COMPAT,
            "routes_compat summary must use build_article_blurb()",
        )


# ===================================================================
# 4. SSE polling interval
# ===================================================================


class TestSSEPollingInterval(unittest.TestCase):
    """Verify SSE endpoints sleep for 60 seconds between polls."""

    def test_sse_sleep_is_60_seconds(self):
        """routes_api SSE endpoint must use asyncio.sleep(60)."""
        self.assertIn(
            "asyncio.sleep(60)",
            _ROUTES_API,
            "routes_api SSE endpoint must sleep for 60 seconds",
        )

    def test_sse_sleep_is_60_in_compat(self):
        """routes_compat SSE endpoint must also use asyncio.sleep(60)."""
        self.assertIn(
            "asyncio.sleep(60)",
            _ROUTES_COMPAT,
            "routes_compat SSE endpoint must sleep for 60 seconds",
        )


# ===================================================================
# 5. Background task intervals
# ===================================================================


class TestBackgroundTaskIntervals(unittest.TestCase):
    """Verify that inline_scheduler.py uses the correct intervals for
    background polling tasks."""

    def test_sitemap_poll_interval_is_3600(self):
        """Sitemap poll should run every 3600 seconds (1 hour)."""
        self.assertRegex(
            _INLINE_SCHEDULER,
            r'"sitemap-poll"\s*,\s*3600\.0',
            'sitemap-poll interval must be 3600.0 seconds',
        )

    def test_social_poll_interval_is_3600(self):
        """Social poll should run every 3600 seconds (1 hour)."""
        self.assertRegex(
            _INLINE_SCHEDULER,
            r'"social-poll"\s*,\s*3600\.0',
            'social-poll interval must be 3600.0 seconds',
        )

    def test_rebuild_faiss_interval_is_21600(self):
        """pgvector backfill should run every 21600 seconds (6 hours)."""
        self.assertRegex(
            _INLINE_SCHEDULER,
            r'"rebuild-faiss"\s*,\s*21600\.0',
            'rebuild-faiss interval must be 21600.0 seconds',
        )

    def test_relationship_inference_interval_is_10800(self):
        """Relationship inference should run every 10800 seconds (3 hours)."""
        self.assertRegex(
            _INLINE_SCHEDULER,
            r'"relationship-inference"\s*,\s*10800\.0',
            'relationship-inference interval must be 10800.0 seconds',
        )


# ===================================================================
# 6. Cache key includes user_id
# ===================================================================


class TestCacheKeyFormat(unittest.TestCase):
    """Verify the cache key patterns include user identification."""

    def test_digest_cache_key_includes_user_id(self):
        """The /digest/today cache key must include settings.public_user_id
        to prevent cross-user cache collisions."""
        self.assertRegex(
            _ROUTES_API,
            r'api_digest_today:\{settings\.public_user_id\}:',
            '/digest/today cache key must include settings.public_user_id',
        )


# ===================================================================
# 7. Skip-if-unchanged guards
# ===================================================================


class TestSkipIfUnchangedGuards(unittest.TestCase):
    """Verify that pipeline tasks use skip guards to avoid redundant work."""

    def test_faiss_rebuild_has_skip_guard(self):
        """rebuild_faiss_index must compare LAST_CLUSTER_COUNT to skip
        when cluster count is unchanged."""
        self.assertIn(
            "LAST_CLUSTER_COUNT",
            _PIPELINE,
            "rebuild_faiss_index must reference LAST_CLUSTER_COUNT for skip guard",
        )
        # Verify the comparison pattern
        self.assertRegex(
            _PIPELINE,
            r'current_count\s*==\s*LAST_CLUSTER_COUNT',
            "rebuild_faiss_index must compare current_count to LAST_CLUSTER_COUNT",
        )

    def test_faiss_guard_filters_by_centroid_embedding(self):
        """The FAISS skip guard query must filter for clusters that have a
        centroid embedding (not all clusters)."""
        self.assertIn(
            "Cluster.centroid_embedding.isnot(None)",
            _PIPELINE,
            "FAISS guard query must filter by Cluster.centroid_embedding.isnot(None)",
        )

    def test_relationship_inference_has_fingerprint_guard(self):
        """run_relationship_inference must compare _LAST_RELATIONSHIP_FINGERPRINT
        to skip when no cluster changes occurred."""
        self.assertIn(
            "_LAST_RELATIONSHIP_FINGERPRINT",
            _PIPELINE,
            "run_relationship_inference must reference _LAST_RELATIONSHIP_FINGERPRINT",
        )
        # Verify the comparison
        self.assertRegex(
            _PIPELINE,
            r'cluster_fingerprint\s*==\s*_LAST_RELATIONSHIP_FINGERPRINT',
            "run_relationship_inference must compare fingerprint to skip when unchanged",
        )

    def test_relationship_fingerprint_includes_coverage(self):
        """The relationship fingerprint hash must include coverage_count
        (not just cluster IDs) so that membership changes trigger a re-run."""
        # The fingerprint uses f"{c.id}:{c.coverage_count}:{c.last_seen_at}"
        self.assertRegex(
            _PIPELINE,
            r'c\.id.*c\.coverage_count',
            "Relationship fingerprint must include coverage_count",
        )


# ===================================================================
# 8. Cache-Control headers
# ===================================================================


class TestCacheControlHeaders(unittest.TestCase):
    """Verify that API responses include proper Cache-Control headers."""

    def test_digest_today_has_cache_control(self):
        """/digest/today must return Cache-Control: public, max-age=300."""
        digest_today_section = _ROUTES_API[_ROUTES_API.index("def compat_digest_today"):]
        next_route = digest_today_section.find("\n@router.", 1)
        if next_route != -1:
            digest_today_section = digest_today_section[:next_route]
        self.assertIn(
            'max-age=300',
            digest_today_section,
            "/digest/today must include Cache-Control max-age=300",
        )
        self.assertIn(
            "Cache-Control",
            digest_today_section,
            "/digest/today must set the Cache-Control header",
        )

    def test_digest_archive_has_cache_control(self):
        """/digest/archive must also return Cache-Control with max-age."""
        archive_section = _ROUTES_API[_ROUTES_API.index("def digest_archive"):]
        next_route = archive_section.find("\n@router.", 1)
        if next_route != -1:
            archive_section = archive_section[:next_route]
        self.assertIn(
            'max-age=3600',
            archive_section,
            "/digest/archive must include Cache-Control max-age=3600",
        )
        self.assertIn(
            "Cache-Control",
            archive_section,
            "/digest/archive must set the Cache-Control header",
        )

    def test_digest_daily_has_cache_control(self):
        """/digest/daily should return Cache-Control because longform is stable per day."""
        digest_daily_section = _ROUTES_API[_ROUTES_API.index("def digest_daily"):]
        next_route = digest_daily_section.find("\ndef ", 1)
        if next_route != -1:
            digest_daily_section = digest_daily_section[:next_route]
        self.assertIn(
            "Cache-Control",
            digest_daily_section,
            "/digest/daily must set the Cache-Control header",
        )


# ===================================================================
# 9. Frontend polling interval
# ===================================================================


class TestFrontendPolling(unittest.TestCase):
    """Verify the frontend refresh interval and realtime wiring."""

    def test_polling_interval_is_5_minutes(self):
        """DIGEST_REFRESH_INTERVAL_MS should be 5 * 60 * 1000 (300000ms)."""
        self.assertIn(
            "DIGEST_REFRESH_INTERVAL_MS = 5 * 60 * 1000",
            _APP_TSX,
            "Frontend polling interval must be DIGEST_REFRESH_INTERVAL_MS = 5 * 60 * 1000",
        )

    def test_realtime_subscribe_is_wired(self):
        """The App useEffect should call aiService.subscribe() for realtime
        updates."""
        self.assertIn(
            "aiService.subscribe(",
            _APP_TSX,
            "App.tsx must call aiService.subscribe() for realtime updates",
        )


# ===================================================================
# 10. Startup path should avoid longform digest fetches
# ===================================================================


class TestFrontendStartupPath(unittest.TestCase):
    """Verify the default app path avoids the expensive longform digest."""

    def test_default_tab_is_live(self):
        """App should land on the live feed, not the longform digest tab."""
        self.assertIn(
            "const [activeTab, setActiveTab] = useState<AppTab>('live')",
            _APP_TSX,
            "App.tsx should default activeTab to 'live' to avoid startup longform fetches",
        )

    def test_daily_digest_archive_is_not_refetched_on_date_change(self):
        """Archive metadata should not refetch on every selectedDate change."""
        archive_effect_section = _DAILY_DIGEST_PAGE[_DAILY_DIGEST_PAGE.index("useEffect(() => {"):]
        archive_effect_section = archive_effect_section[archive_effect_section.index("aiService.fetchDigestArchive()"):]
        archive_effect_section = archive_effect_section[:archive_effect_section.index(");", archive_effect_section.index("}, [")) + 3]
        self.assertNotIn(
            "selectedDate",
            archive_effect_section,
            "DailyDigestPage archive fetch should not depend on selectedDate",
        )

    def test_load_news_for_locale_does_not_eagerly_fetch_weekly(self):
        """The live hot path should not preload weekly data on every digest refresh."""
        load_news_section = _APP_TSX[_APP_TSX.index("const loadNewsForLocale"):]
        load_news_section = load_news_section[:load_news_section.index("const refreshNews")]
        self.assertNotIn(
            "loadWeeklyTop(locale)",
            load_news_section,
            "loadNewsForLocale should not eagerly fetch weekly data",
        )


# ===================================================================
# 11. Relationship inference should defer heavy article columns
# ===================================================================


class TestRelationshipInferenceEgress(unittest.TestCase):
    """Verify relationship inference avoids loading large article blobs."""

    def test_relationship_inference_defers_heavy_article_columns(self):
        relationship_section = _PIPELINE[_PIPELINE.index("def run_relationship_inference"):]
        relationship_section = relationship_section[:relationship_section.index("if not llm_candidates:")]
        for col in ("Article.html", "Article.text", "Article.embedding", "Article.llm_reasoning"):
            self.assertIn(
                f"defer({col})",
                relationship_section,
                f"run_relationship_inference must defer {col}",
            )


class TestLongformArtifactPath(unittest.TestCase):
    """Verify longform digest reads can avoid Postgres HTML blobs."""

    def test_digest_daily_uses_storage_path_when_present(self):
        digest_daily_section = _ROUTES_API[_ROUTES_API.index("def digest_daily"):]
        next_route = digest_daily_section.find("\ndef ", 1)
        if next_route != -1:
            digest_daily_section = digest_daily_section[:next_route]
        self.assertIn(
            "row.storage_path",
            digest_daily_section,
            "/digest/daily should check for a storage-backed longform artifact",
        )
        self.assertIn(
            "load_longform_digest_artifact",
            digest_daily_section,
            "/digest/daily should load longform content from artifact storage before DB fallback",
        )


if __name__ == "__main__":
    unittest.main()
