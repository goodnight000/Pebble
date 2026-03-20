from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import Any

import orjson

from app.config import Settings
from app.integrations.supabase import get_storage_bucket_name, get_supabase_service_client


@dataclass(frozen=True)
class DigestArtifact:
    bucket: str
    path: str
    body: bytes


def build_digest_artifact(
    *,
    user_id: str,
    date: datetime,
    content_type: str,
    article_ids: list[str],
    headline: str | None,
    executive_summary: str | None,
    llm_authored: bool,
    settings: Settings | None = None,
) -> DigestArtifact:
    bucket = get_storage_bucket_name(settings)
    digest_date = date.date().isoformat()
    path = f"daily-digests/{user_id}/{digest_date}/{content_type}.json"
    body = orjson.dumps(
        {
            "user_id": user_id,
            "date": digest_date,
            "content_type": content_type,
            "article_ids": article_ids,
            "headline": headline,
            "executive_summary": executive_summary,
            "llm_authored": llm_authored,
        }
    )
    return DigestArtifact(bucket=bucket, path=path, body=body)


def store_digest_artifact(
    artifact: DigestArtifact,
    *,
    settings: Settings | None = None,
    client=None,
) -> dict[str, str]:
    storage_client = client or get_supabase_service_client(settings)
    storage_bucket = storage_client.storage.from_(artifact.bucket)
    storage_bucket.upload(
        artifact.path,
        BytesIO(artifact.body),
        {"content-type": "application/json", "upsert": "true"},
    )
    return {"bucket": artifact.bucket, "path": artifact.path}


def build_longform_digest_artifact(
    *,
    user_id: str,
    date: datetime,
    headline: str | None,
    subtitle: str | None,
    longform_html: str,
    llm_authored: bool,
    settings: Settings | None = None,
) -> DigestArtifact:
    bucket = get_storage_bucket_name(settings)
    digest_date = date.date().isoformat()
    path = f"daily-digests/{user_id}/{digest_date}/longform.json"
    body = orjson.dumps(
        {
            "user_id": user_id,
            "date": digest_date,
            "content_type": "longform",
            "headline": headline,
            "subtitle": subtitle,
            "longform_html": longform_html,
            "llm_authored": llm_authored,
        }
    )
    return DigestArtifact(bucket=bucket, path=path, body=body)


def _coerce_download_body(download_result: Any) -> bytes | None:
    if download_result is None:
        return None
    if isinstance(download_result, bytes):
        return download_result
    if hasattr(download_result, "read"):
        return download_result.read()
    if hasattr(download_result, "data"):
        data = download_result.data
        return data if isinstance(data, bytes) else None
    if isinstance(download_result, tuple) and download_result:
        first = download_result[0]
        return first if isinstance(first, bytes) else None
    return None


def build_weekly_artifact(
    *,
    user_id: str,
    date: datetime,
    items: list[dict],
    settings: Settings | None = None,
) -> DigestArtifact | None:
    """Build a weekly top articles artifact for storage."""
    if settings and not settings.supabase_storage_enabled:
        return None
    bucket = get_storage_bucket_name(settings)
    path = f"weekly-top/{user_id}/{date.strftime('%Y-%m-%d')}/weekly.json"
    body = orjson.dumps({"items": items, "generated_at": date.isoformat()})
    return DigestArtifact(bucket=bucket, path=path, body=body)


def load_weekly_artifact(
    *,
    user_id: str,
    date: datetime,
    settings: Settings | None = None,
    client=None,
) -> dict[str, Any] | None:
    """Download a stored weekly-top artifact from Supabase Storage."""
    if settings and not settings.supabase_storage_enabled:
        return None
    bucket = get_storage_bucket_name(settings)
    path = f"weekly-top/{user_id}/{date.strftime('%Y-%m-%d')}/weekly.json"
    storage_client = client or get_supabase_service_client(settings)
    storage_bucket = storage_client.storage.from_(bucket)
    try:
        raw = _coerce_download_body(storage_bucket.download(path))
    except Exception:
        return None
    if not raw:
        return None
    from app.observability.egress import note_dependency_egress

    note_dependency_egress(service="supabase_storage", bytes_count=len(raw), target=f"{bucket}/{path}")
    payload = orjson.loads(raw)
    return payload if isinstance(payload, dict) else None


def load_longform_digest_artifact(
    bucket: str,
    path: str,
    *,
    settings: Settings | None = None,
    client=None,
) -> dict[str, Any] | None:
    storage_client = client or get_supabase_service_client(settings)
    storage_bucket = storage_client.storage.from_(bucket)
    raw = _coerce_download_body(storage_bucket.download(path))
    if not raw:
        return None
    from app.observability.egress import note_dependency_egress

    note_dependency_egress(service="supabase_storage", bytes_count=len(raw), target=f"{bucket}/{path}")
    payload = orjson.loads(raw)
    return payload if isinstance(payload, dict) else None


def build_today_response_artifact(
    *,
    user_id: str,
    date: datetime,
    response_data: dict[str, Any],
    settings: Settings | None = None,
) -> DigestArtifact | None:
    """Build a Supabase Storage artifact for the full /api/digest/today response.

    The artifact stores the English-locale version of the complete response so
    the endpoint can serve it with near-zero DB egress.  Returns ``None`` when
    Supabase Storage is disabled.
    """
    _settings = settings or Settings()
    if not _settings.supabase_storage_enabled:
        return None
    bucket = get_storage_bucket_name(_settings)
    digest_date = date.date().isoformat()
    path = f"daily-digests/{user_id}/{digest_date}/today_response.json"
    body = orjson.dumps(response_data)
    return DigestArtifact(bucket=bucket, path=path, body=body)


def load_today_response_artifact(
    *,
    user_id: str,
    date: datetime,
    settings: Settings | None = None,
    client=None,
) -> dict[str, Any] | None:
    """Load the pre-built /api/digest/today response from Supabase Storage.

    Returns the parsed JSON dict or ``None`` if the artifact does not exist or
    storage is disabled.
    """
    _settings = settings or Settings()
    if not _settings.supabase_storage_enabled:
        return None
    bucket = get_storage_bucket_name(_settings)
    digest_date = date.date().isoformat()
    path = f"daily-digests/{user_id}/{digest_date}/today_response.json"
    storage_client = client or get_supabase_service_client(_settings)
    storage_bucket = storage_client.storage.from_(bucket)
    try:
        raw = _coerce_download_body(storage_bucket.download(path))
    except Exception:
        return None
    if not raw:
        return None
    from app.observability.egress import note_dependency_egress

    note_dependency_egress(service="supabase_storage", bytes_count=len(raw), target=f"{bucket}/{path}")
    payload = orjson.loads(raw)
    return payload if isinstance(payload, dict) else None
