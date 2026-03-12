import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath("ai_news"))

from app import config as config_module


class RealtimeEventsTests(unittest.TestCase):
    def setUp(self):
        config_module.get_settings.cache_clear()

    def tearDown(self):
        config_module.get_settings.cache_clear()

    def test_build_urgent_update_event_is_compact_and_normalized(self):
        from app.services.realtime_events import build_urgent_update_event

        payload = build_urgent_update_event(
            article_id="article-1",
            title="Big AI release",
            source="OpenAI",
            url="https://example.com/story",
            final_score=96.5,
        )

        self.assertEqual(
            payload,
            {
                "article_id": "article-1",
                "title": "Big AI release",
                "source": "OpenAI",
                "url": "https://example.com/story",
                "final_score": 96.5,
            },
        )

    def test_build_new_cluster_event_omits_none_top_article_id(self):
        from app.services.realtime_events import build_new_cluster_event

        payload = build_new_cluster_event(
            cluster_id="cluster-1",
            headline="New cluster formed",
            top_article_id=None,
            coverage_count=1,
        )

        self.assertEqual(
            payload,
            {
                "cluster_id": "cluster-1",
                "headline": "New cluster formed",
                "coverage_count": 1,
            },
        )

    def test_build_digest_refresh_event_omits_none_optional_fields(self):
        from app.services.realtime_events import build_digest_refresh_event

        payload = build_digest_refresh_event(
            user_id="user-1",
            digest_date="2026-03-11",
            content_type="all",
            headline=None,
            storage_path=None,
        )

        self.assertEqual(
            payload,
            {
                "user_id": "user-1",
                "date": "2026-03-11",
                "content_type": "all",
            },
        )

    def test_publish_realtime_event_is_noop_when_disabled(self):
        from app.services.realtime_events import publish_realtime_event

        settings = config_module.Settings(_env_file=None)
        publisher = mock.Mock()

        result = publish_realtime_event(
            "urgent",
            "urgent_update",
            {"article_id": "article-1"},
            settings=settings,
            publisher=publisher,
        )

        self.assertIsNone(result)
        publisher.assert_not_called()

    def test_publish_realtime_event_uses_backend_publisher_when_enabled(self):
        from app.services.realtime_events import publish_realtime_event

        with mock.patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres",
                "SUPABASE_URL": "https://project.supabase.co",
                "SUPABASE_ANON_KEY": "anon-key",
                "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
                "SUPABASE_REALTIME_ENABLED": "true",
                "SUPABASE_REALTIME_CHANNEL_URGENT": "alerts",
            },
            clear=True,
        ):
            settings = config_module.Settings(_env_file=None)
            publisher = mock.Mock(return_value="ok")

            result = publish_realtime_event(
                "urgent",
                "urgent_update",
                {"article_id": "article-1"},
                settings=settings,
                publisher=publisher,
            )

        self.assertEqual(result, "ok")
        publisher.assert_called_once_with(
            channel="alerts",
            event="urgent_update",
            payload={"article_id": "article-1"},
            settings=settings,
        )

    def test_publish_realtime_event_uses_digest_channel_mapping_when_enabled(self):
        from app.services.realtime_events import publish_realtime_event

        with mock.patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres",
                "SUPABASE_URL": "https://project.supabase.co",
                "SUPABASE_ANON_KEY": "anon-key",
                "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
                "SUPABASE_REALTIME_ENABLED": "true",
                "SUPABASE_REALTIME_CHANNEL_DIGESTS": "daily-digests",
            },
            clear=True,
        ):
            settings = config_module.Settings(_env_file=None)
            publisher = mock.Mock(return_value="ok")

            result = publish_realtime_event(
                "digests",
                "digest_refresh",
                {"user_id": "user-1"},
                settings=settings,
                publisher=publisher,
            )

        self.assertEqual(result, "ok")
        publisher.assert_called_once_with(
            channel="daily-digests",
            event="digest_refresh",
            payload={"user_id": "user-1"},
            settings=settings,
        )


if __name__ == "__main__":
    unittest.main()
