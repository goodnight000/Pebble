from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Tuple

from bs4 import BeautifulSoup
from htmldate import find_date
from readability import Document
import trafilatura

from app.common.text import normalize_whitespace
from app.scraping import playwright_fetch

logger = logging.getLogger(__name__)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _quality_score(text: str, html: str) -> float:
    text_len = len(text)
    soup = BeautifulSoup(html, "html.parser")
    num_links = len(soup.find_all("a"))
    num_words = max(1, len(text.split()))
    link_density = num_links / num_words
    return _clamp01(0.70 * _clamp01(text_len / 5000) + 0.30 * (1 - _clamp01(link_density / 0.20)))


def _extract_trafilatura(html: str) -> str | None:
    return trafilatura.extract(html, include_comments=False, include_tables=False)


def _extract_readability(html: str) -> str | None:
    doc = Document(html)
    summary_html = doc.summary()
    soup = BeautifulSoup(summary_html, "html.parser")
    return soup.get_text(" ", strip=True)


async def extract_text(html: str, url: str) -> Tuple[str, float]:
    text = _extract_trafilatura(html) or _extract_readability(html) or ""
    text = normalize_whitespace(text)
    quality = _quality_score(text, html)

    if len(text) < 1500 or quality < 0.55:
        try:
            rendered_html = await playwright_fetch.fetch_rendered_html(url)
        except Exception:
            return text, quality
        text = _extract_trafilatura(rendered_html) or _extract_readability(rendered_html) or text
        text = normalize_whitespace(text)
        quality = _quality_score(text, rendered_html)

    return text, quality


def extract_pub_date(html: str, url: str) -> datetime | None:
    """Extract the original publication date from HTML using htmldate.

    Returns a timezone-aware UTC datetime, or None if no date could be found.
    This is used to correct sitemap ``lastmod`` timestamps which reflect
    *modification* time rather than *publication* time.
    """
    try:
        date_str = find_date(
            html,
            url=url,
            original_date=True,
            outputformat="%Y-%m-%d",
        )
        if date_str:
            dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return dt
    except Exception:
        logger.debug("htmldate extraction failed for %s", url, exc_info=True)
    return None
