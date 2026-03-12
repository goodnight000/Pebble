from __future__ import annotations

from importlib import import_module

from app.config import Settings, get_settings


def _resolve_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def get_storage_bucket_name(settings: Settings | None = None) -> str:
    resolved = _resolve_settings(settings)
    return resolved.supabase_storage_bucket_digests or "digests"


def get_realtime_channel_map(settings: Settings | None = None) -> dict[str, str]:
    resolved = _resolve_settings(settings)
    return {
        "urgent": resolved.supabase_realtime_channel_urgent,
        "clusters": resolved.supabase_realtime_channel_clusters,
        "digests": resolved.supabase_realtime_channel_digests,
    }


def get_supabase_public_client_config(settings: Settings | None = None) -> dict[str, str]:
    resolved = _resolve_settings(settings)
    if not resolved.supabase_url:
        raise RuntimeError("SUPABASE_URL is required")
    if not resolved.supabase_anon_key:
        raise RuntimeError("SUPABASE_ANON_KEY is required")
    return {
        "url": resolved.supabase_url,
        "anon_key": resolved.supabase_anon_key,
    }


def _load_supabase_symbols():
    try:
        supabase_module = import_module("supabase")
        client_options_module = import_module("supabase.lib.client_options")
    except ModuleNotFoundError as exc:
        raise RuntimeError("The Python 'supabase' package is required for backend Supabase operations") from exc
    return supabase_module.create_client, client_options_module.ClientOptions


def build_service_client_options(client_options_cls=None):
    if client_options_cls is None:
        _, client_options_cls = _load_supabase_symbols()
    return client_options_cls(auto_refresh_token=False, persist_session=False)


def get_supabase_service_client(settings: Settings | None = None):
    resolved = _resolve_settings(settings)
    if not resolved.supabase_url:
        raise RuntimeError("SUPABASE_URL is required for backend Supabase operations")
    if not resolved.supabase_service_role_key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is required for backend Supabase operations")

    create_client, client_options_cls = _load_supabase_symbols()
    return create_client(
        resolved.supabase_url,
        resolved.supabase_service_role_key,
        options=build_service_client_options(client_options_cls),
    )
