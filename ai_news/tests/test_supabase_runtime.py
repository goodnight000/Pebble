import os
import sys
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from pydantic import ValidationError
from sqlalchemy import Uuid

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres")

sys.path.insert(0, os.path.abspath("ai_news"))
if "supabase" not in sys.modules:
    supabase_stub = types.ModuleType("supabase")
    supabase_stub.create_client = lambda *args, **kwargs: None
    supabase_stub.__path__ = []
    supabase_lib_stub = types.ModuleType("supabase.lib")
    supabase_lib_stub.__path__ = []
    supabase_client_options_stub = types.ModuleType("supabase.lib.client_options")

    class ClientOptions:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    supabase_client_options_stub.ClientOptions = ClientOptions
    sys.modules["supabase"] = supabase_stub
    sys.modules["supabase.lib"] = supabase_lib_stub
    sys.modules["supabase.lib.client_options"] = supabase_client_options_stub

from app import config as config_module
from app.api import main as main_module
from app import db as db_module
from app import models as models_module


class SupabaseRuntimeTests(unittest.TestCase):
    def setUp(self):
        config_module.get_settings.cache_clear()

    def tearDown(self):
        config_module.get_settings.cache_clear()

    def test_settings_parse_supabase_fields(self):
        with mock.patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres",
                "SUPABASE_URL": "https://project.supabase.co",
                "SUPABASE_ANON_KEY": "anon-key",
                "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
                "SUPABASE_STORAGE_BUCKET_DIGESTS": "digests",
                "SUPABASE_REALTIME_ENABLED": "true",
            },
            clear=True,
        ):
            settings = config_module.Settings()

        self.assertEqual(getattr(settings, "supabase_url", None), "https://project.supabase.co")
        self.assertEqual(getattr(settings, "supabase_anon_key", None), "anon-key")
        self.assertEqual(getattr(settings, "supabase_service_role_key", None), "service-role-key")
        self.assertEqual(getattr(settings, "supabase_storage_bucket_digests", None), "digests")
        self.assertTrue(getattr(settings, "supabase_realtime_enabled", False))

    def test_settings_require_database_url(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValidationError):
                config_module.Settings(_env_file=None)

    def test_settings_require_supabase_url_when_realtime_enabled(self):
        with mock.patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres",
                "SUPABASE_REALTIME_ENABLED": "true",
            },
            clear=True,
        ):
            with self.assertRaises(ValidationError):
                config_module.Settings()

    def test_settings_require_service_role_key_when_realtime_enabled(self):
        with mock.patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres",
                "SUPABASE_URL": "https://project.supabase.co",
                "SUPABASE_REALTIME_ENABLED": "true",
            },
            clear=True,
        ):
            with self.assertRaises(ValidationError):
                config_module.Settings()

    def test_settings_require_anon_key_when_realtime_enabled(self):
        with mock.patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres",
                "SUPABASE_URL": "https://project.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
                "SUPABASE_REALTIME_ENABLED": "true",
            },
            clear=True,
        ):
            with self.assertRaises(ValidationError):
                config_module.Settings()

    def test_on_startup_does_not_call_create_all(self):
        session = mock.MagicMock()
        missing_user_query = mock.MagicMock()
        missing_user_query.filter.return_value.first.return_value = None
        missing_prefs_query = mock.MagicMock()
        missing_prefs_query.filter.return_value.first.return_value = None
        session.query.side_effect = [missing_user_query, missing_prefs_query]

        @contextmanager
        def fake_session_scope():
            yield session

        with mock.patch.object(
            db_module.Base.metadata,
            "create_all",
            side_effect=AssertionError("create_all should not be called during startup"),
        ), mock.patch.object(main_module, "session_scope", fake_session_scope), mock.patch.object(
            main_module, "seed_sources"
        ), mock.patch.object(main_module, "maybe_start_inline_scheduler"):
            main_module.on_startup()

        self.assertEqual(session.add.call_count, 2)
        self.assertEqual(session.flush.call_count, 1)

    def test_dev_scripts_require_database_url_without_sqlite_repair(self):
        root = Path(__file__).resolve().parents[2]
        for relative_path in ("scripts/dev.ts", "scripts/dev-ai.ts"):
            contents = (root / relative_path).read_text(encoding="utf-8")
            self.assertIn("alembic", contents)
            self.assertIn("loadDotenv", contents)
            self.assertIn(".env.local", contents)
            self.assertIn("startsWith('sqlite')", contents)
            self.assertIn("Use your Supabase Postgres database", contents)
            self.assertNotIn("repair_cluster_members_schema", contents)
            self.assertNotIn("sqlite:///", contents)
            self.assertNotIn("127.0.0.1:5432/ai_news", contents)

    def test_alembic_env_escapes_percent_encoded_database_urls(self):
        root = Path(__file__).resolve().parents[1]
        contents = (root / "alembic" / "env.py").read_text(encoding="utf-8")
        self.assertIn('replace("%", "%%")', contents)

    def test_compat_router_exposes_realtime_config_alias(self):
        root = Path(__file__).resolve().parents[1]
        contents = (root / "app" / "api" / "routes_api.py").read_text(encoding="utf-8")
        self.assertIn('@router.get("/news/realtime/config")', contents)

    def test_models_use_uuid_columns_for_postgres_compatibility(self):
        self.assertIsInstance(models_module.Source.__table__.c.id.type, Uuid)
        self.assertIsInstance(models_module.RawItem.__table__.c.source_id.type, Uuid)
        self.assertIsInstance(models_module.Article.__table__.c.id.type, Uuid)
        self.assertIsInstance(models_module.User.__table__.c.id.type, Uuid)
        self.assertIsInstance(models_module.DailyDigest.__table__.c.user_id.type, Uuid)


if __name__ == "__main__":
    unittest.main()
