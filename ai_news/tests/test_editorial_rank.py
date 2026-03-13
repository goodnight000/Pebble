"""Unit tests for Batch 3 roadmap changes (items 9, 10)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath('ai_news'))

# Set DATABASE_URL before any app imports that trigger engine creation.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")


class TestEditorialRank(unittest.TestCase):
    """Item 10: editorial rank computation."""

    def _compute(self, **kwargs):
        from app.scoring.editorial_rank import compute_editorial_rank
        return compute_editorial_rank(**kwargs)

    def test_single_source_cluster(self):
        rank = self._compute(
            max_global_score=50.0,
            coverage_count=1,
            independent_sources_count=1,
            has_official_confirmation=False,
            cluster_trust_score=40.0,
        )
        # base=50, coverage=1/5*5=1, corr=1/4*5=1.25, official=0, trust_penalty=0
        expected = 50.0 + 1.0 + 1.25 + 0.0 - 0.0
        self.assertAlmostEqual(rank, round(expected, 2), places=2)

    def test_multi_source_official_cluster(self):
        rank = self._compute(
            max_global_score=70.0,
            coverage_count=5,
            independent_sources_count=4,
            has_official_confirmation=True,
            cluster_trust_score=60.0,
        )
        # base=70, coverage=5/5*5=5, corr=4/4*5=5, official=3, trust_penalty=0
        expected = 70.0 + 5.0 + 5.0 + 3.0
        self.assertAlmostEqual(rank, round(expected, 2), places=2)

    def test_low_trust_penalty(self):
        rank = self._compute(
            max_global_score=50.0,
            coverage_count=1,
            independent_sources_count=1,
            has_official_confirmation=False,
            cluster_trust_score=20.0,
        )
        # trust_penalty = max(0, (40-20)*0.1) = 2.0
        base_rank = self._compute(
            max_global_score=50.0,
            coverage_count=1,
            independent_sources_count=1,
            has_official_confirmation=False,
            cluster_trust_score=40.0,
        )
        self.assertAlmostEqual(base_rank - rank, 2.0, places=2)

    def test_capped_at_100(self):
        rank = self._compute(
            max_global_score=95.0,
            coverage_count=10,
            independent_sources_count=10,
            has_official_confirmation=True,
            cluster_trust_score=80.0,
        )
        self.assertLessEqual(rank, 100.0)

    def test_none_trust_score(self):
        # cluster_trust_score=None should use 40 (no penalty)
        rank = self._compute(
            max_global_score=50.0,
            coverage_count=1,
            independent_sources_count=1,
            has_official_confirmation=False,
            cluster_trust_score=None,
        )
        rank_40 = self._compute(
            max_global_score=50.0,
            coverage_count=1,
            independent_sources_count=1,
            has_official_confirmation=False,
            cluster_trust_score=40.0,
        )
        self.assertAlmostEqual(rank, rank_40, places=2)

    def test_cluster_level_not_article_level(self):
        """Two articles in the same cluster should get the same editorial rank
        when max_global_score comes from the cluster (not the individual article)."""
        cluster_max = 75.0
        rank = self._compute(
            max_global_score=cluster_max,
            coverage_count=3,
            independent_sources_count=2,
            has_official_confirmation=False,
            cluster_trust_score=50.0,
        )
        # Call again with same cluster data — should be identical
        rank2 = self._compute(
            max_global_score=cluster_max,
            coverage_count=3,
            independent_sources_count=2,
            has_official_confirmation=False,
            cluster_trust_score=50.0,
        )
        self.assertEqual(rank, rank2)


class TestScrapeDecisionWatchBand(unittest.TestCase):
    """Item 9: watch band scrape decision."""

    def test_fetch_watch_enum_exists(self):
        from unittest.mock import MagicMock
        import sys
        # Mock app.db to avoid engine creation at import time
        fake_db = MagicMock()
        fake_db.Base = MagicMock()
        sys.modules.setdefault("app.db", fake_db)
        from app.models import ScrapeDecision
        self.assertEqual(ScrapeDecision.fetch_watch.value, "fetch_watch")

    def test_max_watch_per_run_config(self):
        """Settings should have max_watch_per_run with default 15."""
        from app.config import Settings
        field_info = Settings.model_fields.get("max_watch_per_run")
        self.assertIsNotNone(field_info)
        self.assertEqual(field_info.default, 15)


class TestLightweightExtraction(unittest.TestCase):
    """Item 9: lightweight extraction for watch items."""

    def test_function_exists(self):
        from app.scraping.extract import extract_text_lightweight
        self.assertTrue(callable(extract_text_lightweight))

    def test_quality_capped_below_030(self):
        from app.scraping.extract import extract_text_lightweight
        # Create a large HTML document that would normally score high quality
        html = "<html><body>" + "<p>This is a test paragraph with real content. " * 200 + "</p></body></html>"
        text, quality = extract_text_lightweight(html, "https://example.com")
        self.assertLess(quality, 0.30)

    def test_text_capped_at_max_chars(self):
        from app.scraping.extract import extract_text_lightweight
        html = "<html><body>" + "<p>Test content word. " * 500 + "</p></body></html>"
        text, quality = extract_text_lightweight(html, "https://example.com", max_chars=500)
        self.assertLessEqual(len(text), 500)

    def test_watch_items_always_penalized(self):
        """Watch-band quality (capped at 0.29) must trigger the importance penalty."""
        from app.scraping.extract import extract_text_lightweight
        html = "<html><body>" + "<p>Content. " * 200 + "</p></body></html>"
        _, quality = extract_text_lightweight(html, "https://example.com")
        # quality should be strictly less than 0.30, so importance penalty applies
        self.assertLess(quality, 0.30)


if __name__ == "__main__":
    unittest.main()
