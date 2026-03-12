"""Twitter/X connector using twscrape with graceful fallback behavior."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List

from app.common.text import normalize_whitespace
from app.common.time import utcnow
from app.config import get_settings
from app.ingestion.base import CandidateItem

logger = logging.getLogger(__name__)

DEFAULT_AI_ACCOUNTS = [
    "OpenAI",
    "AnthropicAI",
    "GoogleDeepMind",
    "MetaAI",
    "huggingface",
    "MistralAI",
    "karpathy",
    "ylecun",
    "emollick",
]


class TwitterConnector:
    """Monitor AI accounts on X/Twitter.

    Expected setup:
    - twscrape installed
    - sessions pre-configured via twscrape CLI/accounts db
    - optional TWITTER_ACCOUNTS_CSV env to override tracked accounts
    """

    def __init__(self, source_id: str, accounts: list[str] | None = None):
        self.source_id = source_id
        self.accounts = accounts or DEFAULT_AI_ACCOUNTS

    def _resolve_accounts(self) -> list[str]:
        settings = get_settings()
        raw = getattr(settings, "twitter_accounts_csv", "") or ""
        if raw.strip():
            parsed = [x.strip() for x in raw.split(",") if x.strip()]
            if parsed:
                return parsed
        return self.accounts

    async def _fetch_async(self, now: datetime, window_hours: int, per_account: int) -> list[CandidateItem]:
        try:
            from twscrape import API
        except Exception:
            logger.warning("Twitter connector: twscrape not installed, skipping")
            return []

        cutoff = now - timedelta(hours=window_hours)
        accounts = self._resolve_accounts()
        api = API()
        items: list[CandidateItem] = []
        seen_ids: set[str] = set()

        for handle in accounts:
            query = f"from:{handle} lang:en"
            try:
                async for tweet in api.search(query, limit=per_account):
                    tweet_id = str(getattr(tweet, "id", "") or "")
                    if not tweet_id or tweet_id in seen_ids:
                        continue
                    seen_ids.add(tweet_id)

                    created_at = getattr(tweet, "date", None)
                    if isinstance(created_at, datetime):
                        if created_at.tzinfo is None:
                            created_at = created_at.replace(tzinfo=timezone.utc)
                        if created_at < cutoff:
                            continue

                    text = normalize_whitespace(getattr(tweet, "rawContent", "") or "")
                    if not text:
                        continue

                    user_obj = getattr(tweet, "user", None)
                    username = getattr(user_obj, "username", None) if user_obj else None
                    url = getattr(tweet, "url", None) or (
                        f"https://x.com/{username}/status/{tweet_id}" if username else f"https://x.com/i/status/{tweet_id}"
                    )

                    title = text[:140]
                    items.append(
                        CandidateItem(
                            source_id=self.source_id,
                            external_id=tweet_id,
                            url=url,
                            title=title,
                            snippet=text,
                            author=username,
                            published_at=created_at if isinstance(created_at, datetime) else now,
                            fetched_at=now,
                            # Reuse an existing social signal field as a generic engagement proxy.
                            social_reddit_upvotes=int(getattr(tweet, "likeCount", 0) or 0),
                        )
                    )
            except Exception as exc:
                logger.warning("Twitter connector: failed for @%s: %s", handle, exc)
                continue

        return items

    def fetch_candidates(
        self,
        now: datetime | None = None,
        window_hours: int = 24,
        per_account: int = 20,
    ) -> List[CandidateItem]:
        now = now or utcnow()
        try:
            return asyncio.run(self._fetch_async(now, window_hours, per_account))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self._fetch_async(now, window_hours, per_account))
            finally:
                loop.close()

