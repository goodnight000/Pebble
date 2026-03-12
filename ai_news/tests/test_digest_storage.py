import os
import sys
import unittest
from datetime import datetime, timezone
from unittest import mock

import orjson
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres")

sys.path.insert(0, os.path.abspath("ai_news"))

from app import config as config_module
from app.db import Base
from app.models import DailyDigest, User


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

    def test_daily_digest_model_accepts_storage_reference_fields(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        user = User()
        session.add(user)
        session.flush()

        digest = DailyDigest(
            user_id=user.id,
            date=datetime(2026, 3, 11, 6, 0, tzinfo=timezone.utc),
            article_ids=["article-1"],
            content_type="all",
            storage_bucket="digests",
            storage_path="daily-digests/user-123/2026-03-11/all.json",
        )
        session.add(digest)
        session.commit()

        row = session.query(DailyDigest).first()
        self.assertEqual(row.storage_bucket, "digests")
        self.assertEqual(row.storage_path, "daily-digests/user-123/2026-03-11/all.json")


if __name__ == "__main__":
    unittest.main()
