import os
import sys
import unittest
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite:///./test-source-labels.db")

sys.path.insert(0, os.path.abspath("ai_news"))

from app.api.source_labels import build_grounding_source


class SourceLabelTests(unittest.TestCase):
    def test_hacker_news_link_uses_destination_publisher_and_keeps_discovery_source(self):
        source = SimpleNamespace(name="Hacker News", kind="hn")

        payload = build_grounding_source(
            source=source,
            url="https://github.com/kodustech/agent-readiness",
        )

        self.assertEqual(payload["title"], "GitHub")
        self.assertEqual(payload["source"], "GitHub")
        self.assertEqual(payload["discoverySource"], "Hacker News")
        self.assertEqual(payload["viaSource"], "Hacker News")

    def test_non_community_source_preserves_source_name(self):
        source = SimpleNamespace(name="Reuters AI (via Google News)", kind="rss")

        payload = build_grounding_source(
            source=source,
            url="https://news.google.com/rss/articles/example",
        )

        self.assertEqual(payload["title"], "Reuters AI (via Google News)")
        self.assertEqual(payload["source"], "Reuters AI (via Google News)")
        self.assertEqual(payload["discoverySource"], "Reuters AI (via Google News)")
        self.assertNotIn("viaSource", payload)


if __name__ == "__main__":
    unittest.main()
