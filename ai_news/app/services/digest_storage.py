from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

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
