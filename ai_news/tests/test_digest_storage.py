import os
import sys
import unittest
from datetime import datetime, timezone
from unittest import mock

import orjson

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

sys.path.insert(0, os.path.abspath("ai_news"))

from app import config as config_module


class DigestStorageTests(unittest.TestCase):
    def setUp(self):
        config_module.get_settings.cache_clear()

    def tearDown(self):
        config_module.get_settings.cache_clear()

    def test_build_digest_artifact_serializes_payload(self):
        from app.services.digest_storage import build_digest_artifact

        artifact = build_digest_artifact(
            user_id="user-123",
            date=datetime(2026, 3, 11, 6, 0, tzinfo=timezone.utc),
            content_type="all",
            article_ids=["article-1", "article-2"],
            headline="Daily AI Pulse",
            executive_summary="Two major updates.",
            llm_authored=True,
        )

        self.assertEqual(artifact.bucket, "digests")
        self.assertEqual(artifact.path, "daily-digests/user-123/2026-03-11/all.json")
        payload = orjson.loads(artifact.body)
        self.assertEqual(payload["headline"], "Daily AI Pulse")
        self.assertEqual(payload["article_ids"], ["article-1", "article-2"])
        self.assertTrue(payload["llm_authored"])

    def test_store_digest_artifact_returns_stable_metadata(self):
        from app.services.digest_storage import build_digest_artifact, store_digest_artifact

        artifact = build_digest_artifact(
            user_id="user-123",
            date=datetime(2026, 3, 11, 6, 0, tzinfo=timezone.utc),
            content_type="research",
            article_ids=["article-9"],
            headline="Research Daily",
            executive_summary="One research item.",
            llm_authored=False,
        )
        bucket_client = mock.Mock()
        client = mock.Mock()
        client.storage.from_.return_value = bucket_client

        metadata = store_digest_artifact(artifact, client=client)

        client.storage.from_.assert_called_once_with("digests")
        bucket_client.upload.assert_called_once()
        self.assertEqual(
            metadata,
            {
                "bucket": "digests",
                "path": "daily-digests/user-123/2026-03-11/research.json",
            },
        )

    def test_build_longform_digest_artifact_serializes_html_payload(self):
        from app.services.digest_storage import build_longform_digest_artifact

        artifact = build_longform_digest_artifact(
            user_id="user-123",
            date=datetime(2026, 3, 11, 6, 0, tzinfo=timezone.utc),
            headline="Digest Title",
            subtitle="Digest Subtitle",
            longform_html="<h1>Hello</h1>",
            llm_authored=True,
        )

        self.assertEqual(artifact.bucket, "digests")
        self.assertEqual(artifact.path, "daily-digests/user-123/2026-03-11/longform.json")
        payload = orjson.loads(artifact.body)
        self.assertEqual(payload["headline"], "Digest Title")
        self.assertEqual(payload["subtitle"], "Digest Subtitle")
        self.assertEqual(payload["longform_html"], "<h1>Hello</h1>")
        self.assertTrue(payload["llm_authored"])

    def test_load_longform_digest_artifact_parses_storage_payload(self):
        from app.services.digest_storage import load_longform_digest_artifact

        artifact_payload = orjson.dumps(
            {
                "headline": "Digest Title",
                "subtitle": "Digest Subtitle",
                "longform_html": "<p>Body</p>",
                "llm_authored": True,
            }
        )
        bucket_client = mock.Mock()
        bucket_client.download.return_value = artifact_payload
        client = mock.Mock()
        client.storage.from_.return_value = bucket_client

        payload = load_longform_digest_artifact("digests", "daily-digests/user-123/2026-03-11/longform.json", client=client)

        client.storage.from_.assert_called_once_with("digests")
        bucket_client.download.assert_called_once_with("daily-digests/user-123/2026-03-11/longform.json")
        self.assertEqual(payload["headline"], "Digest Title")
        self.assertEqual(payload["subtitle"], "Digest Subtitle")
        self.assertEqual(payload["longform_html"], "<p>Body</p>")

if __name__ == "__main__":
    unittest.main()
