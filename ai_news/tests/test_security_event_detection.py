import os
import sys
import unittest
from unittest.mock import MagicMock

# Stub out app.db before any app module can import it, so that tests work
# without a real DATABASE_URL or psycopg2 driver.
sys.modules.setdefault("app.db", MagicMock(Base=MagicMock()))

from app.features.event_type_rules import classify_event_type
from app.models import EventType


class TestSecurityEventDetection(unittest.TestCase):
    """Tests for expanded SECURITY_INCIDENT regex detection."""

    # Existing patterns should still match
    def test_existing_vulnerability(self):
        self.assertEqual(classify_event_type("Critical vulnerability found in OpenSSL"), EventType.SECURITY_INCIDENT)

    def test_existing_leak(self):
        self.assertEqual(classify_event_type("Data leak exposes millions of records"), EventType.SECURITY_INCIDENT)

    def test_existing_breach(self):
        self.assertEqual(classify_event_type("Major breach at Fortune 500 company"), EventType.SECURITY_INCIDENT)

    def test_existing_security_incident(self):
        self.assertEqual(classify_event_type("Security incident at cloud provider"), EventType.SECURITY_INCIDENT)

    # New patterns
    def test_cve_pattern(self):
        self.assertEqual(classify_event_type("CVE-2026-1234 affects Linux kernel"), EventType.SECURITY_INCIDENT)

    def test_zero_day_hyphen(self):
        self.assertEqual(classify_event_type("Zero-day exploit discovered in Chrome"), EventType.SECURITY_INCIDENT)

    def test_zero_day_space(self):
        self.assertEqual(classify_event_type("Zero day vulnerability in Windows"), EventType.SECURITY_INCIDENT)

    def test_ransomware(self):
        self.assertEqual(classify_event_type("Ransomware attack hits hospital network"), EventType.SECURITY_INCIDENT)

    def test_data_breach(self):
        self.assertEqual(classify_event_type("Data breach exposes customer data"), EventType.SECURITY_INCIDENT)

    def test_rce(self):
        self.assertEqual(classify_event_type("Remote code execution flaw in Apache"), EventType.SECURITY_INCIDENT)

    def test_rce_abbreviation(self):
        self.assertEqual(classify_event_type("Critical RCE in popular library"), EventType.SECURITY_INCIDENT)

    def test_supply_chain_attack(self):
        self.assertEqual(classify_event_type("Supply chain attack targets npm packages"), EventType.SECURITY_INCIDENT)

    def test_malware(self):
        self.assertEqual(classify_event_type("New malware strain targets AI systems"), EventType.SECURITY_INCIDENT)

    def test_exploit(self):
        self.assertEqual(classify_event_type("Exploit released for critical bug"), EventType.SECURITY_INCIDENT)

    def test_apt(self):
        self.assertEqual(classify_event_type("APT group targets defense contractors"), EventType.SECURITY_INCIDENT)

    def test_backdoor(self):
        self.assertEqual(classify_event_type("Backdoor found in popular Python package"), EventType.SECURITY_INCIDENT)

    def test_phishing(self):
        self.assertEqual(classify_event_type("Phishing campaign targets tech workers"), EventType.SECURITY_INCIDENT)

    def test_privilege_escalation(self):
        self.assertEqual(classify_event_type("Privilege escalation bug in Kubernetes"), EventType.SECURITY_INCIDENT)

    def test_sql_injection(self):
        self.assertEqual(classify_event_type("SQL injection vulnerability in WordPress plugin"), EventType.SECURITY_INCIDENT)

    def test_xss(self):
        self.assertEqual(classify_event_type("XSS flaw discovered in popular framework"), EventType.SECURITY_INCIDENT)

    def test_security_advisory(self):
        self.assertEqual(classify_event_type("Security advisory issued for critical flaw"), EventType.SECURITY_INCIDENT)

    def test_critical_patch(self):
        self.assertEqual(classify_event_type("Critical patch released for zero-day"), EventType.SECURITY_INCIDENT)

    # Non-security titles should NOT match
    def test_non_security_title(self):
        self.assertEqual(classify_event_type("OpenAI releases new GPT model"), EventType.MODEL_RELEASE)

    def test_generic_non_security(self):
        self.assertEqual(classify_event_type("AI startup raises Series A"), EventType.STARTUP_FUNDING)

    def test_plain_other(self):
        self.assertEqual(classify_event_type("Interesting developments in the AI space"), EventType.OTHER)

    # NVD source_kind shortcut
    def test_nvd_source_kind(self):
        self.assertEqual(classify_event_type("Some random title", source_kind="nvd"), EventType.SECURITY_INCIDENT)

    def test_nvd_overrides_other(self):
        self.assertEqual(classify_event_type("AI startup announcement", source_kind="nvd"), EventType.SECURITY_INCIDENT)

    # arxiv still works
    def test_arxiv_still_works(self):
        self.assertEqual(classify_event_type("Some paper title", source_kind="arxiv"), EventType.RESEARCH_PAPER)


if __name__ == "__main__":
    unittest.main()
