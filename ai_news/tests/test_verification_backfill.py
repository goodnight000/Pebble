import os
import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres")

sys.path.insert(0, os.path.abspath("ai_news"))

from app.db import Base
from app.models import Article, RawItem, Source


def _embedding() -> bytes:
    return b"\x00" * (384 * 4)


class VerificationBackfillTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def _seed_row(
        self,
        session,
        *,
        source_id: str,
        raw_id: str,
        article_id: str,
        fetched_at: datetime,
        verification_state: str | None,
    ) -> Article:
        source = Source(
            id=source_id,
            name=f"Source {source_id}",
            kind="rss",
            authority=0.8,
            always_scrape=False,
            priority_poll=False,
            enabled=True,
            rate_limit_rps=0.5,
        )
        raw = RawItem(
            id=raw_id,
            source_id=source_id,
            external_id=raw_id,
            url=f"https://example.com/{raw_id}",
            title=f"Title {raw_id}",
            snippet="Snippet",
            published_at=fetched_at,
            fetched_at=fetched_at,
            language="en",
            canonical_hash=f"canon-{raw_id}",
        )
        article = Article(
            id=article_id,
            raw_item_id=raw_id,
            final_url=raw.url,
            text="Today we are launching something notable.",
            extraction_quality=1.0,
            embedding=_embedding(),
            content_type="news",
            event_type="OTHER",
            topics={},
            entities={},
            global_score=50.0,
            verification_state=verification_state,
        )
        session.add(source)
        session.add(raw)
        session.add(article)
        return article

    def test_dry_run_counts_recent_unbackfilled_rows_only(self):
        from app.scripts.backfill_verification import backfill_verification_session

        now = datetime.now(timezone.utc)
        with self.Session() as session:
            self._seed_row(
                session,
                source_id=str(uuid.uuid4()),
                raw_id=str(uuid.uuid4()),
                article_id=str(uuid.uuid4()),
                fetched_at=now - timedelta(hours=6),
                verification_state=None,
            )
            self._seed_row(
                session,
                source_id=str(uuid.uuid4()),
                raw_id=str(uuid.uuid4()),
                article_id=str(uuid.uuid4()),
                fetched_at=now - timedelta(hours=6),
                verification_state="official_statement",
            )
            self._seed_row(
                session,
                source_id=str(uuid.uuid4()),
                raw_id=str(uuid.uuid4()),
                article_id=str(uuid.uuid4()),
                fetched_at=now - timedelta(days=10),
                verification_state=None,
            )
            session.commit()

            with mock.patch("app.scripts.backfill_verification.refresh_article_verification_fields") as refresh:
                result = backfill_verification_session(session, window_hours=72, batch_size=20, dry_run=True)

        self.assertEqual(result["candidates"], 1)
        self.assertEqual(result["updated"], 0)
        refresh.assert_not_called()

    def test_backfill_updates_only_missing_verification_rows(self):
        from app.scripts.backfill_verification import backfill_verification_session

        now = datetime.now(timezone.utc)
        with self.Session() as session:
            target = self._seed_row(
                session,
                source_id=str(uuid.uuid4()),
                raw_id=str(uuid.uuid4()),
                article_id=str(uuid.uuid4()),
                fetched_at=now - timedelta(hours=2),
                verification_state=None,
            )
            existing = self._seed_row(
                session,
                source_id=str(uuid.uuid4()),
                raw_id=str(uuid.uuid4()),
                article_id=str(uuid.uuid4()),
                fetched_at=now - timedelta(hours=2),
                verification_state="community_signal",
            )
            session.commit()

            def fake_refresh(db_session, article, raw, source):
                article.verification_state = "official_statement"
                article.verification_confidence = 91.0
                return article

            with mock.patch(
                "app.scripts.backfill_verification.refresh_article_verification_fields",
                side_effect=fake_refresh,
            ) as refresh:
                result = backfill_verification_session(session, window_hours=72, batch_size=20, dry_run=False)
                session.flush()

        self.assertEqual(result["candidates"], 1)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(target.verification_state, "official_statement")
        self.assertEqual(target.verification_confidence, 91.0)
        self.assertEqual(existing.verification_state, "community_signal")
        refresh.assert_called_once()


if __name__ == "__main__":
    unittest.main()
