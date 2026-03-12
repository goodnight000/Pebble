import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath("ai_news"))

from app import config as config_module


class SupabaseIntegrationTests(unittest.TestCase):
    def setUp(self):
        config_module.get_settings.cache_clear()

    def tearDown(self):
        config_module.get_settings.cache_clear()

    def test_service_client_uses_service_role_credentials(self):
        with mock.patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres",
                "SUPABASE_URL": "https://project.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
            },
            clear=True,
        ):
            from app.integrations import supabase as supabase_integration

            settings = config_module.Settings(_env_file=None)
            fake_supabase_module = types.SimpleNamespace(create_client=mock.Mock(return_value=object()))
            fake_client_options_module = types.SimpleNamespace()
            with mock.patch.object(
                supabase_integration,
                "import_module",
                side_effect=lambda name: (
                    fake_supabase_module
                    if name == "supabase"
                    else types.SimpleNamespace(
                        ClientOptions=mock.Mock(side_effect=lambda **kwargs: ("options", kwargs))
                    )
                ),
            ) as import_module_mock:
                client = supabase_integration.get_supabase_service_client(settings)

        self.assertIsNotNone(client)
        self.assertEqual(import_module_mock.call_count, 2)
        fake_supabase_module.create_client.assert_called_once_with(
            "https://project.supabase.co",
            "service-role-key",
            options=("options", {"auto_refresh_token": False, "persist_session": False}),
        )

    def test_service_client_rejects_missing_service_role_key(self):
        with mock.patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres",
                "SUPABASE_URL": "https://project.supabase.co",
            },
            clear=True,
        ):
            from app.integrations import supabase as supabase_integration

            settings = config_module.Settings(_env_file=None)
            with self.assertRaises(RuntimeError):
                supabase_integration.get_supabase_service_client(settings)

    def test_bucket_and_channel_names_resolve_from_settings(self):
        with mock.patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres",
                "SUPABASE_STORAGE_BUCKET_DIGESTS": "digest-artifacts",
                "SUPABASE_REALTIME_CHANNEL_URGENT": "alerts",
                "SUPABASE_REALTIME_CHANNEL_CLUSTERS": "clusters-live",
                "SUPABASE_REALTIME_CHANNEL_DIGESTS": "daily-digests",
            },
            clear=True,
        ):
            from app.integrations import supabase as supabase_integration

            settings = config_module.Settings(_env_file=None)
            self.assertEqual(supabase_integration.get_storage_bucket_name(settings), "digest-artifacts")
            self.assertEqual(
                supabase_integration.get_realtime_channel_map(settings),
                {
                    "urgent": "alerts",
                    "clusters": "clusters-live",
                    "digests": "daily-digests",
                },
            )


if __name__ == "__main__":
    unittest.main()
