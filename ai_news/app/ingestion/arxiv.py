from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List
from urllib.parse import urlencode

import feedparser
import httpx

from app.common.text import normalize_whitespace
from app.common.time import utcnow
from app.config import get_settings
from app.ingestion.base import CandidateItem


ARXIV_CATS = ["cs.LG", "cs.CL", "cs.AI", "cs.CR", "cs.RO", "stat.ML", "cs.CV", "cs.SE", "eess.AS"]


class ArxivConnector:
    def __init__(self, source_id: str, base_url: str):
        self.source_id = source_id
        self.base_url = base_url.rstrip("/")

    def _build_query(self) -> str:
        cat_query = " OR ".join([f"cat:{cat}" for cat in ARXIV_CATS])
        return cat_query

    def fetch_candidates(
        self,
        now: datetime | None = None,
        window_hours: int = 24,
        max_results: int = 200,
        page_size: int = 100,
    ) -> List[CandidateItem]:
        now = now or utcnow()
        query = self._build_query()
        settings = get_settings()
        headers = {"User-Agent": settings.user_agent, "Accept": "application/atom+xml, application/xml, text/xml, */*"}
        cutoff = now - timedelta(hours=window_hours)

        items: List[CandidateItem] = []
        start = 0
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            while start < max_results:
                batch = min(page_size, max_results - start)
                params = urlencode(
                    {
                        "search_query": query,
                        "sortBy": "lastUpdatedDate",
                        "sortOrder": "descending",
                        "start": start,
                        "max_results": batch,
                    }
                )
                url = f"{self.base_url}?{params}"
                response = client.get(url, headers=headers)
                response.raise_for_status()
                parsed = feedparser.parse(response.content)
                if not parsed.entries:
                    break

                past_cutoff = False
                for entry in parsed.entries:
                    updated_at = None
                    if entry.get("updated_parsed"):
                        updated_at = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
                    if updated_at and updated_at < cutoff:
                        past_cutoff = True
                        continue
                    external_id = entry.get("id")
                    if not external_id:
                        continue
                    title = normalize_whitespace(entry.get("title", ""))
                    if not title:
                        continue
                    summary = normalize_whitespace(entry.get("summary", ""))
                    items.append(
                        CandidateItem(
                            source_id=self.source_id,
                            external_id=str(external_id),
                            url=entry.get("id"),
                            title=title,
                            snippet=summary,
                            author=entry.get("author"),
                            published_at=updated_at,
                            fetched_at=now,
                        )
                    )

                # Stop if all entries in this page were past the cutoff
                if past_cutoff and len(parsed.entries) == sum(
                    1 for e in parsed.entries
                    if e.get("updated_parsed") and datetime(*e.updated_parsed[:6], tzinfo=timezone.utc) < cutoff
                ):
                    break
                start += batch
        return items
