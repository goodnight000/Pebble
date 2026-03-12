from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List

import feedparser
import httpx

from app.common.text import normalize_whitespace, strip_html
from app.common.time import utcnow
from app.config import get_settings
from app.ingestion.base import CandidateItem

logger = logging.getLogger(__name__)

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _fetch_with_browser_tls(url: str) -> bytes:
    """Fetch URL using curl_cffi which impersonates a real browser TLS fingerprint.

    Many sites (Pantheon, WordPress, Cloudflare) block httpx/requests because
    their TLS ClientHello doesn't match any known browser. curl_cffi uses
    libcurl with browser-impersonation patches to produce an authentic
    Chrome/Firefox TLS fingerprint at zero cost.
    """
    from curl_cffi import requests as cffi_requests

    resp = cffi_requests.get(
        url,
        impersonate="chrome",
        timeout=20,
        allow_redirects=True,
        headers={
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    resp.raise_for_status()
    return resp.content


class RSSConnector:
    def __init__(self, source_id: str, feed_url: str, *, browser_ua: bool = False):
        self.source_id = source_id
        self.feed_url = feed_url
        self.browser_ua = browser_ua

    def fetch_candidates(self, now: datetime | None = None) -> List[CandidateItem]:
        now = now or utcnow()
        settings = get_settings()
        cutoff = now - timedelta(hours=settings.ingest_lookback_hours)

        if self.browser_ua:
            # Use curl_cffi for authentic browser TLS fingerprinting.
            content = _fetch_with_browser_tls(self.feed_url)
        else:
            headers = {
                "User-Agent": settings.user_agent,
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
            }
            with httpx.Client(timeout=20, follow_redirects=True) as client:
                response = client.get(self.feed_url, headers=headers)
                response.raise_for_status()
                content = response.content

        parsed = feedparser.parse(content)

        items: List[CandidateItem] = []
        for entry in parsed.entries:
            external_id = entry.get("id") or entry.get("link")
            if not external_id:
                continue
            published_at = None
            parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
            if parsed_time:
                published_at = datetime(*parsed_time[:6], tzinfo=timezone.utc)
            if published_at and published_at < cutoff:
                continue
            summary = entry.get("summary")
            snippet = normalize_whitespace(strip_html(summary)) if summary else None
            title = normalize_whitespace(entry.get("title", ""))
            link = entry.get("link")
            if not title or not link:
                continue
            items.append(
                CandidateItem(
                    source_id=self.source_id,
                    external_id=str(external_id),
                    url=link,
                    title=title,
                    snippet=snippet,
                    author=entry.get("author"),
                    published_at=published_at,
                    fetched_at=now,
                )
            )
        return items
