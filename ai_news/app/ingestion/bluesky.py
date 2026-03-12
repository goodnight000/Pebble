"""Bluesky connector using public AT Protocol search endpoint."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List

import httpx

from app.common.text import normalize_whitespace
from app.common.time import utcnow
from app.config import get_settings
from app.ingestion.base import CandidateItem

logger = logging.getLogger(__name__)

DEFAULT_QUERIES = [
    "machine learning",
    "artificial intelligence",
    "LLM",
    "OpenAI",
    "Anthropic",
    "transformer model",
]


class BlueskyConnector:
    def __init__(self, source_id: str, queries: list[str] | None = None):
        self.source_id = source_id
        self.queries = queries or DEFAULT_QUERIES
        self.base_url = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"

    def fetch_candidates(
        self,
        now: datetime | None = None,
        window_hours: int = 24,
        limit_per_query: int = 25,
    ) -> List[CandidateItem]:
        now = now or utcnow()
        cutoff = now - timedelta(hours=window_hours)
        settings = get_settings()
        headers = {"User-Agent": settings.user_agent, "Accept": "application/json"}

        items: list[CandidateItem] = []
        seen_ids: set[str] = set()

        with httpx.Client(timeout=25, follow_redirects=True) as client:
            for query in self.queries:
                try:
                    resp = client.get(
                        self.base_url,
                        params={"q": query, "limit": limit_per_query},
                        headers=headers,
                    )
                    resp.raise_for_status()
                    posts = (resp.json() or {}).get("posts", [])
                except Exception as exc:
                    logger.warning("Bluesky connector: query '%s' failed: %s", query, exc)
                    continue

                for item in posts:
                    post = item.get("record") or {}
                    uri = item.get("uri") or ""
                    if not uri or uri in seen_ids:
                        continue
                    seen_ids.add(uri)

                    created_raw = post.get("createdAt")
                    created_at = None
                    if created_raw:
                        try:
                            created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                        except ValueError:
                            created_at = None
                    if created_at and created_at < cutoff:
                        continue

                    text = normalize_whitespace(post.get("text") or "")
                    if not text:
                        continue

                    author = (item.get("author") or {}).get("handle")
                    external_id = uri
                    # Keep canonical link when possible.
                    link = f"https://bsky.app/profile/{author}/post/{uri.split('/')[-1]}" if author else uri

                    items.append(
                        CandidateItem(
                            source_id=self.source_id,
                            external_id=external_id,
                            url=link,
                            title=text[:140],
                            snippet=text,
                            author=author,
                            published_at=created_at if isinstance(created_at, datetime) else now,
                            fetched_at=now,
                            social_reddit_upvotes=int((item.get("likeCount") or 0)),
                        )
                    )

        return items

