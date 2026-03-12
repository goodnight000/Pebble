from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from app.config import Settings, get_settings
from app.integrations.supabase import get_realtime_channel_map


def _resolve_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def _realtime_url(supabase_url: str) -> str:
    parsed = urlparse(supabase_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}/realtime/v1"


def _compact_payload(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if value is not None}


def build_urgent_update_event(*, article_id: str, title: str, source: str, url: str, final_score: float) -> dict:
    return _compact_payload({
        "article_id": article_id,
        "title": title,
        "source": source,
        "url": url,
        "final_score": final_score,
    })


def build_new_cluster_event(
    *, cluster_id: str, headline: str, top_article_id: str | None, coverage_count: int
) -> dict:
    return _compact_payload({
        "cluster_id": cluster_id,
        "headline": headline,
        "top_article_id": top_article_id,
        "coverage_count": coverage_count,
    })


def build_digest_refresh_event(
    *, user_id: str, digest_date: str, content_type: str, headline: str | None, storage_path: str | None
) -> dict:
    return _compact_payload({
        "user_id": user_id,
        "date": digest_date,
        "content_type": content_type,
        "headline": headline,
        "storage_path": storage_path,
    })


async def _broadcast_event_async(*, channel: str, event: str, payload: dict, settings: Settings) -> None:
    from realtime import AsyncRealtimeClient

    client = AsyncRealtimeClient(_realtime_url(settings.supabase_url), settings.supabase_service_role_key)
    realtime_channel = client.channel(
        channel,
        {"config": {"broadcast": {"ack": True, "self": False}}},
    )
    await realtime_channel.subscribe()
    await realtime_channel.send_broadcast(event, payload)
    await client.remove_channel(realtime_channel)


def _broadcast_event(*, channel: str, event: str, payload: dict, settings: Settings):
    return asyncio.run(_broadcast_event_async(channel=channel, event=event, payload=payload, settings=settings))


def publish_realtime_event(
    channel_key: str,
    event: str,
    payload: dict,
    *,
    settings: Settings | None = None,
    publisher=None,
):
    resolved = _resolve_settings(settings)
    if not resolved.supabase_realtime_enabled:
        return None

    channel = get_realtime_channel_map(resolved)[channel_key]
    send = publisher or _broadcast_event
    return send(channel=channel, event=event, payload=payload, settings=resolved)
