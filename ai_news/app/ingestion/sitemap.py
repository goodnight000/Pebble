"""Sitemap connector — parse XML sitemaps for new content."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List
from urllib.parse import urlparse

import httpx
from lxml import etree

from app.common.text import normalize_whitespace
from app.common.time import utcnow
from app.common.url_filters import is_news_candidate_url
from app.config import get_settings
from app.ingestion.base import CandidateItem

logger = logging.getLogger(__name__)

MAX_SITEMAP_DEPTH = 3
MAX_SITEMAPS_PER_SOURCE = 24

# Cap how many URLs we accept from no-lastmod sitemaps to avoid flooding.
MAX_NO_LASTMOD_URLS = 200


def _fetch_url_bytes(url: str, *, browser_ua: bool, headers: dict[str, str]) -> bytes:
    """Fetch URL bytes, optionally using curl_cffi for browser TLS impersonation."""
    if browser_ua:
        from curl_cffi import requests as cffi_requests

        resp = cffi_requests.get(
            url,
            impersonate="chrome",
            timeout=30,
            allow_redirects=True,
            headers={"Accept": headers.get("Accept", "*/*")},
        )
        resp.raise_for_status()
        return resp.content
    else:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.content


class SitemapConnector:
    def __init__(
        self,
        source_id: str,
        sitemap_url: str,
        path_filter: str | None = None,
        *,
        browser_ua: bool = False,
        lastmod_optional: bool = False,
    ):
        self.source_id = source_id
        self.sitemap_url = sitemap_url
        self.path_filter = path_filter
        self.browser_ua = browser_ua
        self.lastmod_optional = lastmod_optional

    def fetch_candidates(self, now: datetime | None = None) -> List[CandidateItem]:
        """Parse sitemap XML and return new URLs since last check."""
        now = now or utcnow()
        settings = get_settings()
        cutoff = now - timedelta(hours=settings.ingest_lookback_hours)
        ua = settings.user_agent
        headers = {
            "User-Agent": ua,
            "Accept": "application/xml, text/xml, */*",
        }

        items: List[CandidateItem] = []
        no_lastmod_count = 0
        rows = self._iter_sitemap_urls(
            self.sitemap_url, headers=headers, browser_ua=self.browser_ua,
        )
        for loc, lastmod_text in rows:
            if not is_news_candidate_url(loc, path_filter=self.path_filter):
                continue

            lastmod = None
            if lastmod_text:
                try:
                    lastmod = datetime.fromisoformat(lastmod_text.replace("Z", "+00:00"))
                    if lastmod.tzinfo is None:
                        lastmod = lastmod.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

            if not lastmod:
                if not self.lastmod_optional:
                    continue
                # Accept URL without lastmod but cap the total to avoid flooding.
                no_lastmod_count += 1
                if no_lastmod_count > MAX_NO_LASTMOD_URLS:
                    continue
            else:
                if lastmod < cutoff:
                    continue

            # Derive a readable title from the URL path
            path = urlparse(loc).path.rstrip("/")
            slug = path.split("/")[-1] if path else loc
            title = normalize_whitespace(slug.replace("-", " ").replace("_", " ").title())

            items.append(
                CandidateItem(
                    source_id=self.source_id,
                    external_id=loc,
                    url=loc,
                    title=title,
                    snippet=None,
                    published_at=lastmod,
                    fetched_at=now,
                )
            )

        logger.info("Sitemap %s: found %d candidates", self.sitemap_url, len(items))
        return items

    def _iter_sitemap_urls(
        self,
        sitemap_url: str,
        *,
        headers: dict[str, str],
        browser_ua: bool = False,
        depth: int = 0,
        visited: set[str] | None = None,
    ) -> list[tuple[str, str | None]]:
        visited = visited or set()
        if depth > MAX_SITEMAP_DEPTH:
            return []
        if sitemap_url in visited:
            return []
        if len(visited) >= MAX_SITEMAPS_PER_SOURCE:
            return []
        visited.add(sitemap_url)

        content = _fetch_url_bytes(sitemap_url, browser_ua=browser_ua, headers=headers)
        root = etree.fromstring(content)
        tag = etree.QName(root).localname.lower()

        if tag == "sitemapindex":
            rows: list[tuple[str, str | None]] = []
            for loc in root.xpath(".//*[local-name()='sitemap']/*[local-name()='loc']/text()"):
                child = (loc or "").strip()
                if not child:
                    continue
                rows.extend(
                    self._iter_sitemap_urls(
                        child,
                        headers=headers,
                        browser_ua=browser_ua,
                        depth=depth + 1,
                        visited=visited,
                    )
                )
            return rows

        rows: list[tuple[str, str | None]] = []
        for url_elem in root.xpath(".//*[local-name()='url']"):
            loc = url_elem.xpath("./*[local-name()='loc']/text()")
            if not loc:
                continue
            url = (loc[0] or "").strip()
            if not url:
                continue
            lastmod = url_elem.xpath("./*[local-name()='lastmod']/text()")
            rows.append((url, (lastmod[0] or "").strip() if lastmod else None))
        return rows
