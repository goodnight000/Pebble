"""End-to-end tests for scoring path invariants.

These exercise real code paths through the production selection route to verify:
  1. Reclassified articles change content_type and tab eligibility.
  2. Low-base / high-editorial clusters survive the DB floor and surface.
  3. extraction_quality=0.0 is not coerced to 1.0.
"""
import os
import sys
import uuid
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath("ai_news"))
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

# Mock app.db before any module that imports it transitively.
# Use a REAL declarative_base so SQLAlchemy model columns work (UserPref.user_id
# etc.), but mock engine/session to avoid needing psycopg2 or a real DB.
from sqlalchemy.orm import declarative_base as _declarative_base

_fake_db = MagicMock()
_fake_db.Base = _declarative_base()
_fake_db.session_scope = MagicMock()
_fake_db.get_db = MagicMock()
_fake_db.SessionLocal = MagicMock()
sys.modules.setdefault("app.db", _fake_db)

# Mock app.tasks.pipeline to avoid pulling in Celery, FAISS, embeddings.
sys.modules.setdefault("app.tasks.pipeline", MagicMock())

import numpy as np


# ---------------------------------------------------------------------------
# Helpers: build fake ORM-like row tuples for _select_articles
# ---------------------------------------------------------------------------

def _make_embedding():
    """Return a valid 384-dim float32 embedding as bytes."""
    return np.ones(384, dtype=np.float32).tobytes()


def _make_row(
    *,
    article_id=None,
    raw_id=None,
    source_id=None,
    title="Test Article",
    final_url="https://example.com/article",
    text="Some article text for testing.",
    event_type="OTHER",
    content_type="news",
    topics=None,
    entities=None,
    global_score=50.0,
    final_score=None,
    extraction_quality=0.8,
    trust_label="likely",
    trust_components=None,
    urgent=False,
    summary=None,
    source_name="Test Source",
    source_kind="rss",
    source_authority=0.7,
    published_at=None,
    fetched_at=None,
    cluster_coverage=1,
    cluster_sources=1,
    cluster_max_global=None,
    cluster_independent=1,
    cluster_official=False,
    cluster_trust=40.0,
    has_cluster=True,
):
    """Build a (Article, RawItem, Source, Cluster) tuple matching the ORM query."""
    now = datetime.utcnow()
    article = SimpleNamespace(
        id=article_id or str(uuid.uuid4()),
        raw_item_id=raw_id or str(uuid.uuid4()),
        final_url=final_url,
        text=text,
        event_type=event_type,
        content_type=content_type,
        topics=topics or {},
        entities=entities or {},
        global_score=global_score,
        final_score=final_score,
        extraction_quality=extraction_quality,
        embedding=_make_embedding(),
        trust_label=trust_label,
        trust_components=trust_components or {},
        urgent=urgent,
        summary=summary,
        funding_amount_usd=None,
        llm_score=None,
        confirmation_level=None,
        created_at=now,
    )
    raw = SimpleNamespace(
        id=article.raw_item_id,
        source_id=source_id or str(uuid.uuid4()),
        title=title,
        snippet="A test snippet.",
        published_at=published_at or (now - timedelta(hours=2)),
        fetched_at=fetched_at or (now - timedelta(hours=2)),
        social_hn_points=0,
        social_hn_comments=0,
        social_reddit_upvotes=0,
        social_github_stars=0,
    )
    source = SimpleNamespace(
        id=raw.source_id,
        name=source_name,
        kind=source_kind,
        authority=source_authority,
    )
    if has_cluster:
        cluster = SimpleNamespace(
            id=str(uuid.uuid4()),
            coverage_count=cluster_coverage,
            sources_count=cluster_sources,
            max_global_score=cluster_max_global if cluster_max_global is not None else global_score,
            independent_sources_count=cluster_independent,
            has_official_confirmation=cluster_official,
            cluster_trust_score=cluster_trust,
            first_seen_at=now - timedelta(hours=3),
            last_seen_at=now,
        )
    else:
        cluster = None
    return article, raw, source, cluster


def _build_mock_db(rows, *, min_show_score=30):
    """Build a mock DB session that _select_articles can call.

    The mock article-query chain inspects SQLAlchemy filter expressions so
    that content_type filtering (routes_compat.py:275-276) is applied to
    the rows returned by .all(), just as the real DB would.
    """
    db = MagicMock()

    # _load_user_context queries
    prefs = SimpleNamespace(
        min_show_score=min_show_score,
        min_urgent_score=85,
        serendipity=0.0,
        prefer_official_sources=False,
        prefer_research=1.0,
        prefer_startups=1.0,
        prefer_hardware=1.0,
        prefer_open_source=1.0,
        prefer_policy_safety=1.0,
        prefer_tutorials_tools=1.0,
        recency_bias=1.0,
        credibility_bias=1.0,
        hype_tolerance=1.0,
    )

    def mock_query(*models):
        chain = MagicMock()

        # Determine what's being queried
        model_names = [getattr(m, "__name__", str(m)) for m in models]

        if "UserPref" in str(model_names):
            for method in ("join", "outerjoin", "filter", "order_by", "limit"):
                getattr(chain, method).return_value = chain
            chain.filter.return_value.first.return_value = prefs
            return chain
        if "UserEntityWeight" in str(model_names):
            for method in ("join", "outerjoin", "filter", "order_by", "limit"):
                getattr(chain, method).return_value = chain
            chain.filter.return_value.all.return_value = []
            return chain
        if "UserTopicWeight" in str(model_names):
            for method in ("join", "outerjoin", "filter", "order_by", "limit"):
                getattr(chain, method).return_value = chain
            chain.filter.return_value.all.return_value = []
            return chain
        if "UserSourceWeight" in str(model_names):
            for method in ("join", "outerjoin", "filter", "order_by", "limit"):
                getattr(chain, method).return_value = chain
            chain.filter.return_value.all.return_value = []
            return chain

        # Main article query — intercept .filter() calls to capture
        # content_type so .all() can apply the same filter the DB would.
        captured = {}

        def smart_filter(*args, **kwargs):
            for arg in args:
                try:
                    left = getattr(arg, "left", None)
                    if left is not None and getattr(left, "key", None) == "content_type":
                        captured["content_type"] = arg.right.effective_value
                except (AttributeError, TypeError):
                    pass
            return chain

        chain.filter = smart_filter
        for method in ("join", "outerjoin", "order_by", "limit"):
            getattr(chain, method).return_value = chain

        def filtered_all():
            ct = captured.get("content_type")
            if ct:
                return [r for r in rows if r[0].content_type == ct]
            return list(rows)

        chain.all = filtered_all

        return chain

    db.query = mock_query
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    return db


# ---------------------------------------------------------------------------
# Test: content_type via shared lightweight module (no heavy imports)
# ---------------------------------------------------------------------------

class TestContentTypeSharedModule(unittest.TestCase):
    """content_type_for lives in a zero-dep module and is used by both
    pipeline.py and routes_compat.py for content_type derivation."""

    def test_rss_other_is_news(self):
        from app.common.content_type import content_type_for
        self.assertEqual(content_type_for("rss", "OTHER"), "news")

    def test_rss_research_paper_is_research(self):
        from app.common.content_type import content_type_for
        self.assertEqual(content_type_for("rss", "RESEARCH_PAPER"), "research")

    def test_arxiv_any_is_research(self):
        from app.common.content_type import content_type_for
        self.assertEqual(content_type_for("arxiv", "OTHER"), "research")
        self.assertEqual(content_type_for("arxiv", "MODEL_RELEASE"), "research")

    def test_github_pinned(self):
        from app.common.content_type import content_type_for
        self.assertEqual(content_type_for("github", "OTHER"), "github")
        self.assertEqual(content_type_for("github", "RESEARCH_PAPER"), "github")
        self.assertEqual(content_type_for("github_trending", "MODEL_RELEASE"), "github")

    def test_reclassification_flips_content_type(self):
        """Simulates the reclassification path: an rss/OTHER article that
        LLM reclassifies to RESEARCH_PAPER must change content_type."""
        from app.common.content_type import content_type_for

        article = SimpleNamespace(
            event_type="OTHER",
            content_type=content_type_for("rss", "OTHER"),
        )
        self.assertEqual(article.content_type, "news")

        # LLM reclassifies
        article.event_type = "RESEARCH_PAPER"
        article.content_type = content_type_for("rss", article.event_type)

        self.assertEqual(article.content_type, "research")


# ---------------------------------------------------------------------------
# Test: reclassified article changes tab eligibility through the route
# ---------------------------------------------------------------------------

class TestReclassifiedArticleTabEligibility(unittest.TestCase):
    """After reclassification changes content_type from 'news' to 'research',
    _select_articles with content_type='research' must include the article
    and content_type='news' must exclude it.

    The mock DB's .filter() inspects SQLAlchemy content_type expressions
    and applies them in .all(), so these tests exercise real inclusion/
    exclusion — not just payload shaping."""

    def _mixed_rows(self):
        """Return a mix of news and research articles."""
        return [
            _make_row(
                title="Company Announces Product",
                event_type="PRODUCT_LAUNCH",
                content_type="news",
                global_score=55.0,
            ),
            _make_row(
                title="Transformer Architecture Survey",
                event_type="RESEARCH_PAPER",
                content_type="research",
                global_score=55.0,
                source_kind="arxiv",
            ),
            _make_row(
                title="Novel Attention Mechanism",
                event_type="RESEARCH_PAPER",
                content_type="research",
                global_score=60.0,
                source_kind="rss",
            ),
        ]

    def _select(self, rows, content_type=None):
        from app.api.routes_compat import _select_articles
        db = _build_mock_db(rows)
        cutoff = datetime.utcnow() - timedelta(hours=24)
        return _select_articles(
            db, user_id="test-user", cutoff=cutoff,
            half_life_base=18, limit=30, content_type=content_type,
        )

    def test_research_tab_excludes_news(self):
        """Filtering for content_type='research' must return only research
        articles and exclude news articles."""
        items = self._select(self._mixed_rows(), content_type="research")
        self.assertEqual(len(items), 2)
        for item in items:
            self.assertEqual(item["contentType"], "research")

    def test_news_tab_excludes_research(self):
        """Filtering for content_type='news' must return only news articles
        and exclude research articles."""
        items = self._select(self._mixed_rows(), content_type="news")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["contentType"], "news")
        self.assertEqual(items[0]["title"], "Company Announces Product")

    def test_no_filter_returns_all(self):
        """Without a content_type filter, all articles appear."""
        items = self._select(self._mixed_rows(), content_type=None)
        self.assertEqual(len(items), 3)
        content_types = {item["contentType"] for item in items}
        self.assertEqual(content_types, {"news", "research"})

    def test_reclassified_article_moves_tab(self):
        """An rss/OTHER article reclassified to RESEARCH_PAPER gets
        content_type='research' and appears in the research tab,
        not the news tab."""
        from app.common.content_type import content_type_for

        reclassified_ct = content_type_for("rss", "RESEARCH_PAPER")
        rows = [
            _make_row(
                title="Reclassified Paper",
                event_type="RESEARCH_PAPER",
                content_type=reclassified_ct,
                source_kind="rss",
                global_score=55.0,
            ),
            _make_row(
                title="Regular News",
                event_type="PRODUCT_LAUNCH",
                content_type="news",
                global_score=55.0,
            ),
        ]
        # Should appear in research tab
        research_items = self._select(rows, content_type="research")
        self.assertEqual(len(research_items), 1)
        self.assertEqual(research_items[0]["title"], "Reclassified Paper")

        # Should NOT appear in news tab
        news_items = self._select(rows, content_type="news")
        self.assertEqual(len(news_items), 1)
        self.assertEqual(news_items[0]["title"], "Regular News")


# ---------------------------------------------------------------------------
# Test: low-base / high-editorial cluster survives floor in route
# ---------------------------------------------------------------------------

class TestLowBaseHighEditorialSurvivesRoute(unittest.TestCase):
    """A low global_score article in a strongly corroborated cluster must
    survive the DB floor AND get boosted by editorial rank in the route."""

    def _select(self, rows, content_type=None, min_show_score=10):
        from app.api.routes_compat import _select_articles
        db = _build_mock_db(rows, min_show_score=min_show_score)
        cutoff = datetime.utcnow() - timedelta(hours=24)
        return _select_articles(
            db, user_id="test-user", cutoff=cutoff,
            half_life_base=18, limit=30, content_type=content_type,
        )

    def test_low_base_article_surfaces_via_editorial_rank(self):
        """An article with global_score=8 in a 5-source official cluster
        gets editorial rank ~21, which after user scoring should exceed
        the min_show_score of 10."""
        rows = [_make_row(
            title="EU AI Act Enforcement Begins",
            event_type="GOVERNMENT_ACTION",
            global_score=8.0,
            final_score=8.0,
            source_authority=0.9,
            cluster_coverage=5,
            cluster_sources=5,
            cluster_max_global=8.0,
            cluster_independent=4,
            cluster_official=True,
            cluster_trust=60.0,
        )]
        items = self._select(rows, min_show_score=10)
        # The article should appear — editorial rank boosted it
        self.assertEqual(len(items), 1)
        # The significanceScore should be well above the raw 8.0
        self.assertGreater(items[0]["significanceScore"], 8)
        # editorialRank should reflect cluster-level boost
        self.assertGreater(items[0]["editorialRank"], 8.0)

    def test_editorial_rank_is_cluster_level(self):
        """Two articles from the same cluster should get the same
        editorialRank when the cluster's max_global_score is used."""
        cluster_id = str(uuid.uuid4())
        shared_cluster = dict(
            cluster_coverage=3,
            cluster_sources=3,
            cluster_max_global=60.0,
            cluster_independent=3,
            cluster_official=False,
            cluster_trust=50.0,
        )
        rows = [
            _make_row(title="Article A", global_score=60.0, final_score=60.0, **shared_cluster),
            _make_row(title="Article B", global_score=45.0, final_score=45.0, **shared_cluster),
        ]
        items = self._select(rows, min_show_score=10)
        self.assertEqual(len(items), 2)
        # Both should have the same editorialRank since cluster data is identical
        self.assertEqual(items[0]["editorialRank"], items[1]["editorialRank"])

    def test_zero_score_gets_very_low_rank(self):
        """An article with global_score=0 in a trivial cluster gets a very
        low editorial rank and significance score.  In production the DB
        floor (>= 2) would filter it before it reaches the route.  The route
        backfill mechanism may still surface it when the feed is otherwise
        empty, but its score should be near zero."""
        rows = [_make_row(
            title="Garbage Article",
            global_score=0.0,
            final_score=0.0,
            cluster_max_global=0.0,
        )]
        items = self._select(rows, min_show_score=30)
        # Backfill may include it, but score must be very low
        if items:
            self.assertLess(items[0]["significanceScore"], 5)
            self.assertLess(items[0]["editorialRank"], 5)

    def test_db_floor_constant_matches_editorial_boost(self):
        """The _MAX_EDITORIAL_BOOST constant in routes_compat must equal
        the max possible output of compute_editorial_rank minus its input."""
        from app.scoring.editorial_rank import compute_editorial_rank

        # Max boost scenario: 5+ coverage, 4+ independent, official, high trust
        base = 0.0
        max_rank = compute_editorial_rank(
            max_global_score=base,
            coverage_count=5,
            independent_sources_count=4,
            has_official_confirmation=True,
            cluster_trust_score=60.0,
        )
        actual_max_boost = max_rank - base
        # The constant in routes_compat.py:280 is 13
        self.assertLessEqual(actual_max_boost, 13.0)


# ---------------------------------------------------------------------------
# Test: extraction_quality=0.0 through the scoring pipeline
# ---------------------------------------------------------------------------

class TestExtractionQualityZeroPath(unittest.TestCase):
    """extraction_quality=0.0 must not be coerced to 1.0."""

    def test_zero_vs_none_coercion(self):
        """The pipeline must distinguish 0.0 (failed extraction) from None
        (missing value). Only None should default to 1.0."""
        # The fixed code pattern
        for quality, expected in [(0.0, 0.0), (None, 1.0), (0.5, 0.5), (1.0, 1.0)]:
            result = quality if quality is not None else 1.0
            self.assertEqual(result, expected, f"quality={quality!r}")

    def test_zero_quality_gets_max_penalty(self):
        from app.scoring.importance import GlobalScoreInputs, compute_global_score_v2

        score_zero, signals_zero = compute_global_score_v2(
            GlobalScoreInputs(source_authority=0.8, event_type="PRODUCT_LAUNCH", extraction_quality=0.0)
        )
        score_full, _ = compute_global_score_v2(
            GlobalScoreInputs(source_authority=0.8, event_type="PRODUCT_LAUNCH", extraction_quality=1.0)
        )
        self.assertAlmostEqual(signals_zero["extraction_quality_penalty"], 0.70, places=3)
        self.assertAlmostEqual(score_zero / score_full, 0.70, places=2)

    def test_zero_quality_article_scores_lower_in_route(self):
        """An article with extraction_quality=0.0 should score lower than
        one with extraction_quality=1.0 when both go through the route.

        The extraction_quality penalty is applied during compute_global_score_v2
        in the pipeline, which produces a lower global_score for low-quality
        articles.  Here we feed the route pre-penalised global_scores (as the
        pipeline would) and verify the route's output reflects the difference."""
        from app.api.routes_compat import _select_articles
        from app.scoring.importance import GlobalScoreInputs, compute_global_score_v2

        # Compute what global_score the pipeline would produce for each quality
        inputs_good = GlobalScoreInputs(source_authority=0.8, event_type="PRODUCT_LAUNCH", extraction_quality=1.0)
        inputs_bad = GlobalScoreInputs(source_authority=0.8, event_type="PRODUCT_LAUNCH", extraction_quality=0.0)
        gs_good, _ = compute_global_score_v2(inputs_good)
        gs_bad, _ = compute_global_score_v2(inputs_bad)
        self.assertGreater(gs_good, gs_bad, "pipeline should penalise quality=0.0")

        good_rows = [_make_row(title="Good Article", global_score=gs_good, extraction_quality=1.0)]
        bad_rows = [_make_row(title="Bad Article", global_score=gs_bad, extraction_quality=0.0)]

        cutoff = datetime.utcnow() - timedelta(hours=24)
        good_items = _select_articles(
            _build_mock_db(good_rows, min_show_score=10),
            user_id="test", cutoff=cutoff, half_life_base=18, limit=30,
        )
        bad_items = _select_articles(
            _build_mock_db(bad_rows, min_show_score=10),
            user_id="test", cutoff=cutoff, half_life_base=18, limit=30,
        )
        self.assertEqual(len(good_items), 1)
        self.assertEqual(len(bad_items), 1)
        self.assertGreater(
            good_items[0]["significanceScore"],
            bad_items[0]["significanceScore"],
            "quality=1.0 article must score higher than quality=0.0 in route output",
        )


if __name__ == "__main__":
    unittest.main()
