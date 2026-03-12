from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

try:
    import praw
except Exception:  # pragma: no cover - optional dependency
    praw = None

from app.common.text import normalize_whitespace
from app.common.time import utcnow
from app.config import get_settings
from app.ingestion.base import CandidateItem


SUBREDDITS = [
    "MachineLearning",
    "LocalLLaMA",
    "OpenAI",
    "singularity",
    "artificial",
    "StableDiffusion",
    "ChatGPT",
    "ClaudeAI",
    "netsec",
    "cybersecurity",
]


class RedditConnector:
    def __init__(self, source_id: str):
        self.source_id = source_id

    def _client(self):
        settings = get_settings()
        if praw is None:
            return None
        if not settings.reddit_client_id or not settings.reddit_client_secret:
            return None
        return praw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
        )

    def fetch_candidates(self, now: datetime | None = None, window_hours: int = 24) -> List[CandidateItem]:
        now = now or utcnow()
        cutoff = now - timedelta(hours=window_hours)
        items: List[CandidateItem] = []
        client = self._client()
        if client is None:
            return items
        for subreddit_name in SUBREDDITS:
            subreddit = client.subreddit(subreddit_name)
            for submission in subreddit.new(limit=50):
                created = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
                if created < cutoff:
                    continue
                items.append(
                    CandidateItem(
                        source_id=self.source_id,
                        external_id=submission.id,
                        url=submission.url,
                        title=normalize_whitespace(submission.title),
                        snippet=normalize_whitespace(submission.selftext or ""),
                        author=str(submission.author) if submission.author else None,
                        published_at=created,
                        fetched_at=now,
                        social_reddit_upvotes=submission.score,
                    )
                )
        return items
