import os
import sys
import unittest
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres")

sys.path.insert(0, os.path.abspath("ai_news"))

from app.clustering import cluster as cluster_mod
from app.db import Base
from app.models import Article, Cluster, ClusterMember, RawItem, Source


class ClusterMemberTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        cluster_mod.INDEX.rebuild(np.zeros((0, 384), dtype=np.float32), [])
        cluster_mod.LAST_BUILT_AT = datetime.now(timezone.utc)

    def _make_article(self, session, source: Source, external_id: str, title: str) -> Article:
        raw = RawItem(
            source_id=source.id,
            external_id=external_id,
            url=f"https://example.com/{external_id}",
            title=title,
            snippet=f"{title} snippet",
            fetched_at=datetime.now(timezone.utc),
            canonical_hash=f"hash-{external_id}",
            language="en",
        )
        session.add(raw)
        session.flush()
        article = Article(
            raw_item_id=raw.id,
            final_url=raw.url,
            html=None,
            text=raw.snippet or title,
            extraction_quality=0.8,
            embedding=np.ones(384, dtype=np.float32).tobytes(),
            event_type="OTHER",
            content_type="news",
            topics={"llms": 1.0},
            entities={},
            funding_amount_usd=None,
            global_score=10.0,
            urgent=False,
            summary=None,
        )
        session.add(article)
        session.flush()
        return article

    def test_cluster_can_hold_multiple_articles(self):
        with self.Session() as session:
            source = Source(
                name="Test Source",
                kind="rss",
                base_url="https://example.com",
                authority=0.8,
                always_scrape=False,
                priority_poll=False,
                enabled=True,
                rate_limit_rps=0.5,
            )
            session.add(source)
            session.flush()

            article_one = self._make_article(session, source, "one", "Story One")
            article_two = self._make_article(session, source, "two", "Story Two")

            cluster = Cluster(
                centroid_embedding=np.ones(384, dtype=np.float32).tobytes(),
                headline="Story One",
                top_article_id=article_one.id,
                coverage_count=2,
                sources_count=1,
                max_global_score=10.0,
            )
            session.add(cluster)
            session.flush()

            session.add(ClusterMember(cluster_id=cluster.id, article_id=article_one.id, similarity=1.0))
            session.add(ClusterMember(cluster_id=cluster.id, article_id=article_two.id, similarity=0.95))
            session.commit()

            members = session.query(ClusterMember).filter(ClusterMember.cluster_id == cluster.id).all()
            self.assertEqual(len(members), 2)

    def test_attach_or_create_cluster_is_idempotent_for_existing_membership(self):
        embedding = np.ones(384, dtype=np.float32)
        with self.Session() as session:
            source = Source(
                name="Attach Source",
                kind="rss",
                base_url="https://example.com",
                authority=0.8,
                always_scrape=False,
                priority_poll=False,
                enabled=True,
                rate_limit_rps=0.5,
            )
            session.add(source)
            session.flush()

            article_one = self._make_article(session, source, "attach-one", "Attach One")
            article_two = self._make_article(session, source, "attach-two", "Attach Two")

            cluster = Cluster(
                centroid_embedding=embedding.tobytes(),
                headline="Attach One",
                top_article_id=article_one.id,
                coverage_count=1,
                sources_count=1,
                max_global_score=10.0,
            )
            session.add(cluster)
            session.flush()
            session.add(ClusterMember(cluster_id=cluster.id, article_id=article_one.id, similarity=1.0))
            session.flush()

            cluster_mod.INDEX.rebuild(np.vstack([embedding]), [cluster.id])
            cluster_mod.LAST_BUILT_AT = datetime.now(timezone.utc)

            first_cluster_id, _ = cluster_mod.attach_or_create_cluster(session, article_two, embedding)
            second_cluster_id, _ = cluster_mod.attach_or_create_cluster(session, article_two, embedding)
            session.commit()

            members = session.query(ClusterMember).filter(ClusterMember.cluster_id == cluster.id).all()
            self.assertEqual(first_cluster_id, cluster.id)
            self.assertEqual(second_cluster_id, cluster.id)
            self.assertEqual(len(members), 2)


if __name__ == "__main__":
    unittest.main()
