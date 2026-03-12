"""Integration tests for cybersecurity scoring signals."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("ai_news"))

from app.scoring.signals import entity_prominence_score, event_impact_score, ENTITY_TIERS


class CybersecurityScoringTests(unittest.TestCase):
    """Verify that cybersecurity entities and events score correctly."""

    def test_security_incident_event_impact(self):
        score = event_impact_score("SECURITY_INCIDENT")
        self.assertAlmostEqual(score, 0.90, places=2)

    def test_crowdstrike_entity_prominence(self):
        score = entity_prominence_score({"CrowdStrike": 1.0})
        self.assertGreaterEqual(score, 0.75, f"CrowdStrike prominence {score} < 0.75")

    def test_cisa_entity_prominence(self):
        score = entity_prominence_score({"CISA": 1.0})
        self.assertGreaterEqual(score, 0.70, f"CISA prominence {score} < 0.70")

    def test_mitre_entity_prominence(self):
        score = entity_prominence_score({"MITRE": 1.0})
        self.assertGreaterEqual(score, 0.70, f"MITRE prominence {score} < 0.70")


if __name__ == "__main__":
    unittest.main()
