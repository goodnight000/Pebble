from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

import httpx

from app.common.text import normalize_whitespace
from app.common.time import utcnow
from app.ingestion.base import CandidateItem
from app.config import get_settings


HN_QUERIES = [
    "AI", "LLM", "GPT", "machine learning", "OpenAI", "Anthropic", "Claude",
    "cybersecurity", "vulnerability", "CVE", "zero-day", "ransomware",
]


class HackerNewsConnector:
    def __init__(self, source_id: str):
        self.source_id = source_id

    def fetch_candidates(self, now: datetime | None = None) -> List[CandidateItem]:
        now = now or utcnow()
        # Use search_by_date for recency.
        base_url = "https://hn.algolia.com/api/v1/search_by_date"
        # Algolia search treats multiple terms as AND. We make multiple queries
        # with different keywords and merge results to get better coverage.
        queries = HN_QUERIES
        cutoff = now - timedelta(hours=get_settings().ingest_lookback_hours)

        seen_ids: set[str] = set()
        items: List[CandidateItem] = []

        with httpx.Client(timeout=20) as client:
            for query in queries:
                try:
                    params = {"query": query, "tags": "story", "hitsPerPage": 30}
                    response = client.get(base_url, params=params)
                    response.raise_for_status()
                    data = response.json()
                except Exception:
                    continue

                for hit in data.get("hits", []):
                    object_id = hit.get("objectID")
                    if not object_id or object_id in seen_ids:
                        continue
                    seen_ids.add(object_id)

                    title = normalize_whitespace(hit.get("title") or "")
                    hit_url = hit.get("url") or hit.get("story_url")
                    if not title or not hit_url:
                        continue
                    published_at = None
                    created_at = hit.get("created_at")
                    if created_at:
                        try:
                            published_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        except ValueError:
                            published_at = None
                    if published_at and published_at < cutoff:
                        continue
                    items.append(
                        CandidateItem(
                            source_id=self.source_id,
                            external_id=str(object_id),
                            url=hit_url,
                            title=title,
                            snippet=normalize_whitespace(hit.get("story_text") or ""),
                            author=hit.get("author"),
                            published_at=published_at,
                            fetched_at=now,
                            social_hn_points=hit.get("points"),
                            social_hn_comments=hit.get("num_comments"),
                        )
                    )
        return items
