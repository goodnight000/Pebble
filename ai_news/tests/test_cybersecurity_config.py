"""Tests that cybersecurity sources, entities, and keywords are properly configured."""
import os
import sys
import unittest

import yaml
from pathlib import Path

sys.path.insert(0, os.path.abspath("ai_news"))

CONFIG_DIR = Path(__file__).resolve().parent.parent / "app"


def _load_sources():
    with open(CONFIG_DIR / "config_sources.yml") as f:
        return yaml.safe_load(f)


def _load_entities():
    with open(CONFIG_DIR / "config_entities.yml") as f:
        return yaml.safe_load(f)


class CybersecuritySourcesTests(unittest.TestCase):
    """Verify cybersecurity RSS sources exist in config_sources.yml."""

    def setUp(self):
        self.cfg = _load_sources()
        self.source_names = [s["name"] for s in self.cfg["sources"]]

    def test_has_at_least_15_cybersecurity_rss_sources(self):
        cyber_names = [
            "Krebs on Security",
            "BleepingComputer",
            "The Hacker News (THN)",
            "Dark Reading",
            "SecurityWeek",
            "CyberScoop",
            "The Record (Recorded Future)",
            "SC Media",
            "CISA Cybersecurity Advisories",
            "NCSC UK",
            "SANS ISC Diary",
            "ENISA",
            "Google Project Zero",
            "Google TAG",
            "Microsoft Security Blog",
        ]
        found = [n for n in cyber_names if n in self.source_names]
        self.assertGreaterEqual(len(found), 15, f"Only found {len(found)} of the expected cybersecurity sources")

    def test_has_nvd_source(self):
        nvd_sources = [s for s in self.cfg["sources"] if s.get("kind") == "nvd"]
        self.assertGreaterEqual(len(nvd_sources), 1, "No NVD source with kind: nvd found")

    def test_keywords_include_cybersecurity_terms(self):
        kw = self.cfg.get("keywords", {})
        required = ["CVE", "zero-day", "ransomware", "malware", "exploit", "data breach"]
        for term in required:
            self.assertIn(term, kw, f"Keyword '{term}' missing from keywords section")

    def test_official_domains_include_security_domains(self):
        domains = self.cfg.get("official_domains", [])
        required = ["crowdstrike.com", "paloaltonetworks.com", "nist.gov", "cisa.gov"]
        for d in required:
            self.assertIn(d, domains, f"Official domain '{d}' missing")


class CybersecurityEntitiesTests(unittest.TestCase):
    """Verify cybersecurity entities in config_entities.yml."""

    def setUp(self):
        self.cfg = _load_entities()

    def test_entity_aliases_include_security_companies(self):
        aliases = self.cfg.get("aliases", {})
        required = ["CrowdStrike", "Palo Alto Networks", "Mandiant", "SentinelOne"]
        for name in required:
            self.assertIn(name, aliases, f"Entity alias '{name}' missing from aliases")

    def test_crowdstrike_and_palo_alto_in_tier2(self):
        tier2 = self.cfg.get("ENTITY_TIERS", {}).get("tier2", [])
        self.assertIn("CrowdStrike", tier2)
        self.assertIn("Palo Alto Networks", tier2)

    def test_security_entities_in_tier3(self):
        tier3 = self.cfg.get("ENTITY_TIERS", {}).get("tier3", [])
        required_tier3 = ["Mandiant", "Recorded Future", "SentinelOne", "Fortinet", "Cisco Talos", "MITRE", "CISA"]
        for name in required_tier3:
            self.assertIn(name, tier3, f"Entity '{name}' missing from tier3")


class SignalsPyConfigTests(unittest.TestCase):
    """Verify ENTITY_TIERS and OFFICIAL_DOMAINS in signals.py include security entries."""

    def test_entity_tiers_include_security_entities(self):
        from app.scoring.signals import ENTITY_TIERS

        required = ["CrowdStrike", "CISA", "Palo Alto Networks", "Cloudflare", "Mandiant", "MITRE"]
        for name in required:
            self.assertIn(name, ENTITY_TIERS, f"ENTITY_TIERS missing '{name}'")

    def test_official_domains_include_security_domains(self):
        from app.scoring.signals import OFFICIAL_DOMAINS

        required = ["nist.gov", "cisa.gov", "crowdstrike.com", "paloaltonetworks.com"]
        for d in required:
            self.assertIn(d, OFFICIAL_DOMAINS, f"OFFICIAL_DOMAINS missing '{d}'")


if __name__ == "__main__":
    unittest.main()
