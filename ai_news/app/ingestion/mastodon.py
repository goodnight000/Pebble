"""Mastodon connector for public hashtag timelines."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List

import httpx

from app.common.text import normalize_whitespace, strip_html
from app.common.time import utcnow
from app.config import get_settings
from app.ingestion.base import CandidateItem

logger = logging.getLogger(__name__)

DEFAULT_INSTANCES = ["sigmoid.social", "mastodon.social"]
DEFAULT_HASHTAGS = ["MachineLearning", "AI", "LLM", "NLP", "DeepLearning"]


class MastodonConnector:
    def __init__(
        self,
        source_id: str,
        instances: list[str] | None = None,
        hashtags: list[str] | None = None,
    ):
        self.source_id = source_id
        self.instances = instances or DEFAULT_INSTANCES
        self.hashtags = hashtags or DEFAULT_HASHTAGS

    def fetch_candidates(
        self,
        now: datetime | None = None,
        window_hours: int = 24,
        limit_per_tag: int = 20,
    ) -> List[CandidateItem]:
        now = now or utcnow()
        cutoff = now - timedelta(hours=window_hours)
        settings = get_settings()
        headers = {"User-Agent": settings.user_agent, "Accept": "application/json"}

        items: list[CandidateItem] = []
        seen_ids: set[str] = set()

        with httpx.Client(timeout=25, follow_redirects=True) as client:
            for instance in self.instances:
                for tag in self.hashtags:
                    url = f"https://{instance}/api/v1/timelines/tag/{tag}"
                    try:
                        resp = client.get(url, params={"limit": limit_per_tag}, headers=headers)
                        resp.raise_for_status()
                        posts = resp.json()
                    except Exception as exc:
                        logger.warning("Mastodon connector: %s #%s failed: %s", instance, tag, exc)
                        continue

                    for post in posts:
                        post_id = str(post.get("id") or "")
                        if not post_id or post_id in seen_ids:
                            continue
                        seen_ids.add(post_id)

                        created_raw = post.get("created_at")
                        created_at = None
                        if created_raw:
                            try:
                                created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                            except ValueError:
                                created_at = None
                        if created_at and created_at < cutoff:
                            continue

                        account = post.get("account") or {}
                        author = account.get("acct") or account.get("username")
                        text = normalize_whitespace(strip_html(post.get("content") or ""))
                        if not text:
                            continue

                        link = post.get("url") or post.get("uri")
                        if not link:
                            continue

                        items.append(
                            CandidateItem(
                                source_id=self.source_id,
                                external_id=post_id,
                                url=link,
                                title=text[:140],
                                snippet=text,
                                author=author,
                                published_at=created_at if isinstance(created_at, datetime) else now,
                                fetched_at=now,
                                social_reddit_upvotes=int(post.get("favourites_count") or 0),
                            )
                        )

        return items

