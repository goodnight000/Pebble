from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict
import uuid

import yaml
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent


def _default_public_user_id() -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "ai_news_public_user"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = Field(default="dev", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    database_url: str = Field(..., alias="DATABASE_URL")
    redis_url: str = Field(default="", alias="REDIS_URL")
    celery_broker_url: str = Field(default="memory://", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="cache+memory://", alias="CELERY_RESULT_BACKEND")
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_anon_key: str | None = Field(default=None, alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str | None = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_storage_bucket_digests: str | None = Field(default="digests", alias="SUPABASE_STORAGE_BUCKET_DIGESTS")
    supabase_storage_enabled: bool = Field(default=False, alias="SUPABASE_STORAGE_ENABLED")
    supabase_realtime_enabled: bool = Field(default=False, alias="SUPABASE_REALTIME_ENABLED")
    supabase_realtime_channel_urgent: str = Field(default="urgent_update", alias="SUPABASE_REALTIME_CHANNEL_URGENT")
    supabase_realtime_channel_clusters: str = Field(default="new_cluster", alias="SUPABASE_REALTIME_CHANNEL_CLUSTERS")
    supabase_realtime_channel_digests: str = Field(default="digest_refresh", alias="SUPABASE_REALTIME_CHANNEL_DIGESTS")

    user_agent: str = Field(default="ai-news-bot/0.1", alias="USER_AGENT")

    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(default="google/gemini-3-flash-preview", alias="OPENROUTER_MODEL")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL")
    openrouter_app_url: str = Field(default="http://localhost:3000", alias="OPENROUTER_APP_URL")
    openrouter_app_title: str = Field(default="AIPulse", alias="OPENROUTER_APP_TITLE")
    llm_request_timeout_seconds: int = Field(default=60, alias="LLM_REQUEST_TIMEOUT_SECONDS")
    llm_max_retries: int = Field(default=2, alias="LLM_MAX_RETRIES")
    llm_retry_backoff_seconds: float = Field(default=1.5, alias="LLM_RETRY_BACKOFF_SECONDS")

    webhook_urgent_url: str | None = Field(default=None, alias="WEBHOOK_URGENT_URL")

    github_token: str | None = Field(default=None, alias="GITHUB_TOKEN")
    reddit_client_id: str | None = Field(default=None, alias="REDDIT_CLIENT_ID")
    reddit_client_secret: str | None = Field(default=None, alias="REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = Field(default="ai-news-bot/0.1", alias="REDDIT_USER_AGENT")
    congress_api_key: str | None = Field(default=None, alias="CONGRESS_API_KEY")
    semantic_scholar_api_key: str | None = Field(default=None, alias="SEMANTIC_SCHOLAR_API_KEY")

    public_user_id: str = Field(default_factory=_default_public_user_id, alias="PUBLIC_USER_ID")

    max_scrape_per_run: int = Field(default=50, alias="MAX_SCRAPE_PER_RUN")
    max_watch_per_run: int = Field(default=15, alias="MAX_WATCH_PER_RUN")
    ingest_lookback_hours: int = Field(default=168, alias="INGEST_LOOKBACK_HOURS")

    @model_validator(mode="after")
    def validate_supabase_runtime(self) -> "Settings":
        if self.supabase_realtime_enabled:
            if not self.supabase_url:
                raise ValueError("SUPABASE_URL is required when SUPABASE_REALTIME_ENABLED is true")
            if not self.supabase_anon_key:
                raise ValueError("SUPABASE_ANON_KEY is required when SUPABASE_REALTIME_ENABLED is true")
            if not self.supabase_service_role_key:
                raise ValueError("SUPABASE_SERVICE_ROLE_KEY is required when SUPABASE_REALTIME_ENABLED is true")
        if self.supabase_storage_enabled:
            if not self.supabase_url:
                raise ValueError("SUPABASE_URL is required when SUPABASE_STORAGE_ENABLED is true")
            if not self.supabase_service_role_key:
                raise ValueError("SUPABASE_SERVICE_ROLE_KEY is required when SUPABASE_STORAGE_ENABLED is true")
            if not self.supabase_storage_bucket_digests:
                raise ValueError("SUPABASE_STORAGE_BUCKET_DIGESTS is required when SUPABASE_STORAGE_ENABLED is true")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_source_config() -> Dict[str, Any]:
    return _load_yaml(BASE_DIR / "config_sources.yml")


def load_entity_aliases() -> Dict[str, Any]:
    return _load_yaml(BASE_DIR / "config_entities.yml")
