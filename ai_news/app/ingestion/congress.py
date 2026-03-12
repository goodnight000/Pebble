"""Congress.gov connector — AI-related bills and legislation."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List

import httpx

from app.common.text import normalize_whitespace
from app.common.time import utcnow
from app.config import get_settings
from app.ingestion.base import CandidateItem

logger = logging.getLogger(__name__)

CONGRESS_API_BASE = "https://api.congress.gov/v3"
AI_SEARCH_TERMS = ["artificial intelligence", "machine learning", "AI regulation", "algorithmic"]


class CongressConnector:
    def __init__(self, source_id: str, api_key: str | None = None):
        self.source_id = source_id
        self.api_key = api_key or ""

    def fetch_candidates(self, now: datetime | None = None) -> List[CandidateItem]:
        """Fetch recent AI-related bills from Congress.gov API."""
        now = now or utcnow()
        if not self.api_key:
            logger.warning("Congress connector: no API key configured, skipping")
            return []

        settings = get_settings()
        cutoff = now - timedelta(hours=settings.ingest_lookback_hours)
        items: List[CandidateItem] = []
        seen_urls: set[str] = set()

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            for term in AI_SEARCH_TERMS:
                params = {
                    "query": term,
                    "api_key": self.api_key,
                    "format": "json",
                    "limit": 20,
                    "sort": "updateDate+desc",
                }
                try:
                    resp = client.get(f"{CONGRESS_API_BASE}/bill", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception:
                    logger.exception("Congress API request failed for term: %s", term)
                    continue

                for bill in data.get("bills", []):
                    bill_url = bill.get("url", "")
                    if not bill_url or bill_url in seen_urls:
                        continue
                    seen_urls.add(bill_url)

                    title = normalize_whitespace(bill.get("title", ""))
                    if not title:
                        continue

                    update_date = bill.get("updateDate", "")
                    pub_dt = now
                    if update_date:
                        try:
                            pub_dt = datetime.fromisoformat(update_date.replace("Z", "+00:00"))
                            if pub_dt.tzinfo is None:
                                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                        except ValueError:
                            pass

                    if pub_dt < cutoff:
                        continue

                    items.append(
                        CandidateItem(
                            source_id=self.source_id,
                            external_id=bill_url,
                            url=bill_url,
                            title=title,
                            snippet=None,
                            published_at=pub_dt,
                            fetched_at=now,
                        )
                    )

        logger.info("Congress: found %d AI-related bills", len(items))
        return items
