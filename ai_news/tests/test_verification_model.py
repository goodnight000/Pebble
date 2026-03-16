import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath("ai_news"))

from app.scoring.time_decay import compute_urgent
from app.scoring.verification import (
    VerificationInputs,
    compute_verification,
    legacy_trust_label_for_state,
)


def _article(
    *,
    final_url: str,
    text: str,
    source_authority: float = 0.7,
    source_kind: str = "rss",
    source_name: str = "Test Source",
    event_type: str = "OTHER",
    created_at: datetime | None = None,
):
    return VerificationInputs(
        cluster_articles=[],
        source_authority=source_authority,
        text=text,
        url=final_url,
        primary_entity=None,
        independent_sources=1,
        event_type=event_type,
        source_kind=source_kind,
        source_name=source_name,
        created_at=created_at or datetime.now(timezone.utc),
    )


class VerificationModelTests(unittest.TestCase):
    def test_github_repo_from_hacker_news_is_verified_artifact(self):
        result = compute_verification(
            _article(
                final_url="https://github.com/NVlabs/KernelBlaster",
                text="Introducing KernelBlaster, a CUDA code optimization framework with code and examples.",
                source_kind="hn",
                source_name="Hacker News",
                event_type="OPEN_SOURCE_RELEASE",
                source_authority=0.55,
            )
        )

        self.assertEqual(result.verification_mode, "artifact")
        self.assertEqual(result.verification_state, "verified_artifact")
        self.assertEqual(result.freshness_state, "fresh")
        self.assertGreaterEqual(result.verification_confidence, 60.0)
        self.assertIn(
            legacy_trust_label_for_state(result.verification_state, result.verification_confidence),
            {"likely", "confirmed"},
        )

    def test_official_blog_post_is_official_statement(self):
        result = compute_verification(
            _article(
                final_url="https://openai.com/index/gpt-5-4/",
                text="Today we are launching GPT-5.4 with improved coding and reasoning.",
                source_kind="rss",
                source_name="OpenAI Blog",
                event_type="MODEL_RELEASE",
                source_authority=1.0,
            )
        )

        self.assertEqual(result.verification_mode, "official_statement")
        self.assertEqual(result.verification_state, "official_statement")
        self.assertGreaterEqual(result.verification_confidence, 75.0)

    def test_single_source_report_stays_single_source(self):
        result = compute_verification(
            VerificationInputs(
                cluster_articles=[],
                source_authority=0.82,
                text="According to people familiar with the matter, the company may be raising a new round.",
                url="https://example.com/report",
                primary_entity="ExampleAI",
                independent_sources=1,
                event_type="STARTUP_FUNDING",
                source_kind="rss",
                source_name="Industry News",
                created_at=datetime.now(timezone.utc) - timedelta(hours=8),
            )
        )

        self.assertEqual(result.verification_mode, "reported_news")
        self.assertEqual(result.verification_state, "single_source_report")
        self.assertEqual(result.freshness_state, "maturing")
        self.assertLess(result.verification_confidence, 75.0)

    def test_community_post_without_linked_evidence_is_community_signal(self):
        result = compute_verification(
            _article(
                final_url="https://news.ycombinator.com/item?id=123",
                text="Interesting rumor in the comments about a stealth model launch.",
                source_kind="hn",
                source_name="Hacker News",
                source_authority=0.45,
            )
        )

        self.assertEqual(result.verification_mode, "community_post")
        self.assertEqual(result.verification_state, "community_signal")
        self.assertLessEqual(result.verification_confidence, 69.0)

    def test_corrected_item_is_not_left_in_trusted_state(self):
        result = compute_verification(
            _article(
                final_url="https://openai.com/index/gpt-5-4/",
                text="Correction: we updated this announcement to fix an inaccurate benchmark claim.",
                source_kind="rss",
                source_name="OpenAI Blog",
                event_type="MODEL_RELEASE",
                source_authority=1.0,
            )
        )

        self.assertEqual(result.verification_state, "corrected_or_retracted")
        self.assertIn(result.update_status, {"corrected", "retracted"})
        self.assertEqual(
            legacy_trust_label_for_state(result.verification_state, result.verification_confidence),
            "disputed",
        )

    def test_low_confidence_single_source_does_not_map_to_likely(self):
        self.assertEqual(legacy_trust_label_for_state("single_source_report", 72.0), "likely")
        self.assertEqual(legacy_trust_label_for_state("single_source_report", 55.0), "unverified")

    def test_reporting_about_retraction_is_not_itself_a_correction_notice(self):
        result = compute_verification(
            _article(
                final_url="https://example.com/reuters-style-report",
                text=(
                    "Reuters reports that the university said the paper was retracted last week "
                    "after concerns about fabricated results."
                ),
                source_kind="rss",
                source_name="Reuters",
                event_type="RESEARCH_PAPER",
                source_authority=0.95,
                created_at=datetime.now(timezone.utc) - timedelta(hours=12),
            )
        )

        self.assertNotEqual(result.verification_state, "corrected_or_retracted")
        self.assertEqual(result.update_status, "active")

    def test_compute_urgent_uses_verification_state(self):
        self.assertTrue(
            compute_urgent(
                90.0,
                1.0,
                1,
                False,
                trust_label="unverified",
                verification_state="verified_artifact",
                verification_confidence=82.0,
            )
        )
        self.assertFalse(
            compute_urgent(
                90.0,
                1.0,
                3,
                False,
                trust_label="likely",
                verification_state="community_signal",
                verification_confidence=65.0,
            )
        )
        self.assertFalse(
            compute_urgent(
                90.0,
                1.0,
                2,
                False,
                trust_label="official",
                verification_state="corrected_or_retracted",
                verification_confidence=88.0,
            )
        )


if __name__ == "__main__":
    unittest.main()
