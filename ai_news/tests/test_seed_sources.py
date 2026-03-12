import os
import sys
import unittest

os.environ.setdefault('DATABASE_URL', 'sqlite:///./test-seed-sources.db')

sys.path.insert(0, os.path.abspath('ai_news'))

from app.scripts.seed_sources import dedupe_sources_by_name


class SeedSourcesTests(unittest.TestCase):
    def test_dedupes_duplicate_source_names_and_keeps_last_definition(self):
        items = [
            {"name": "Google Project Zero", "kind": "rss", "feed_url": "https://first.example/feed"},
            {"name": "Trail of Bits", "kind": "rss", "feed_url": "https://one.example/feed"},
            {"name": "Google Project Zero", "kind": "sitemap", "sitemap_url": "https://second.example/sitemap.xml"},
        ]

        deduped = dedupe_sources_by_name(items)

        self.assertEqual([item["name"] for item in deduped], ["Google Project Zero", "Trail of Bits"])
        self.assertEqual(deduped[0]["kind"], "sitemap")
        self.assertEqual(deduped[0]["sitemap_url"], "https://second.example/sitemap.xml")


if __name__ == '__main__':
    unittest.main()
