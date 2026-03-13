"""Unit tests for Batch 2 roadmap changes (items 6, 7, 8)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath('ai_news'))


class TestExtractionQualityPenalty(unittest.TestCase):
    """Item 6: extraction_quality soft penalty in global scoring."""

    def _compute(self, extraction_quality: float) -> tuple[float, dict]:
        from app.scoring.importance import GlobalScoreInputs, compute_global_score_v2

        inputs = GlobalScoreInputs(
            source_authority=0.8,
            event_type="PRODUCT_LAUNCH",
            extraction_quality=extraction_quality,
        )
        return compute_global_score_v2(inputs)

    def test_no_penalty_above_030(self):
        score, signals = self._compute(0.50)
        self.assertAlmostEqual(signals["extraction_quality_penalty"], 1.0, places=3)

    def test_no_penalty_at_quality_100(self):
        score, signals = self._compute(1.0)
        self.assertAlmostEqual(signals["extraction_quality_penalty"], 1.0, places=3)

    def test_penalty_at_quality_030(self):
        # quality=0.30 is the boundary — should get penalty
        _, signals = self._compute(0.30)
        expected_penalty = 0.70 + 0.30 * (0.30 / 0.30)
        self.assertAlmostEqual(signals["extraction_quality_penalty"], round(expected_penalty, 4), places=3)
        self.assertAlmostEqual(expected_penalty, 1.0, places=2)

    def test_penalty_at_quality_015(self):
        _, signals = self._compute(0.15)
        expected_penalty = 0.70 + 0.30 * (0.15 / 0.30)
        self.assertAlmostEqual(signals["extraction_quality_penalty"], round(expected_penalty, 4), places=3)
        self.assertAlmostEqual(expected_penalty, 0.85, places=2)

    def test_penalty_at_quality_000(self):
        _, signals = self._compute(0.0)
        self.assertAlmostEqual(signals["extraction_quality_penalty"], 0.70, places=3)

    def test_score_reduced_by_penalty(self):
        score_good, _ = self._compute(1.0)
        score_bad, _ = self._compute(0.0)
        self.assertGreater(score_good, score_bad)
        # quality=0.0 should give 0.70x the score
        self.assertAlmostEqual(score_bad / score_good, 0.70, places=2)

    def test_default_extraction_quality(self):
        from app.scoring.importance import GlobalScoreInputs
        inputs = GlobalScoreInputs()
        self.assertEqual(inputs.extraction_quality, 1.0)

    def test_watch_band_quality_gets_penalty(self):
        """Watch-band items (quality capped at 0.29) must always be penalized."""
        _, signals = self._compute(0.29)
        self.assertLess(signals["extraction_quality_penalty"], 1.0)

    def test_quality_zero_not_coerced(self):
        """extraction_quality=0.0 must apply penalty, not be treated as 1.0."""
        score_zero, signals_zero = self._compute(0.0)
        score_good, signals_good = self._compute(1.0)
        self.assertAlmostEqual(signals_zero["extraction_quality_penalty"], 0.70, places=3)
        self.assertLess(score_zero, score_good)


class TestBidirectionalJudge(unittest.TestCase):
    """Item 8: bidirectional LLM judge scoring."""

    def _compute(self, rule, llm, **kwargs):
        from app.scoring.llm_judge import compute_final_score
        return compute_final_score(rule, llm, **kwargs)

    def test_none_llm_returns_rule(self):
        self.assertEqual(self._compute(60.0, None), 60.0)

    def test_upward_boost_unchanged(self):
        # LLM=80, rule=60 → blended=0.7*60+0.3*80=66 > 60 → 66
        result = self._compute(60.0, 80.0)
        self.assertAlmostEqual(result, 66.0, places=2)

    def test_downward_correction_basic(self):
        # LLM=20, rule=60 → blended=0.7*60+0.3*20=48 < 60
        # delta=12, no guardrails → final=48
        result = self._compute(60.0, 20.0)
        self.assertAlmostEqual(result, 48.0, places=2)

    def test_official_confirmation_caps_delta(self):
        # LLM=0, rule=60 → blended=42, delta=18 → capped at 5 for official
        result = self._compute(60.0, 0.0, confirmation_level="official")
        self.assertAlmostEqual(result, 55.0, places=2)

    def test_trusted_label_halves_delta(self):
        # LLM=20, rule=60 → blended=48, delta=12 → halved to 6
        result = self._compute(60.0, 20.0, trust_label="confirmed")
        self.assertAlmostEqual(result, 54.0, places=2)

    def test_max_drop_15(self):
        # LLM=0, rule=100 → blended=70, delta=30 → capped at 15
        result = self._compute(100.0, 0.0)
        self.assertAlmostEqual(result, 85.0, places=2)

    def test_official_plus_trusted(self):
        # LLM=0, rule=60 → blended=42, delta=18
        # official cap: min(18, 5) = 5
        # trusted halve: 5 * 0.5 = 2.5
        # max cap: min(2.5, 15) = 2.5
        result = self._compute(60.0, 0.0, confirmation_level="official", trust_label="official")
        self.assertAlmostEqual(result, 57.5, places=2)

    def test_backward_compatible(self):
        # Calling without keyword args should still work
        result = self._compute(60.0, 80.0)
        self.assertIsInstance(result, float)


if __name__ == "__main__":
    unittest.main()
