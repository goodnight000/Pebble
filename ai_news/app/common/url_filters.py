from __future__ import annotations

from urllib.parse import urlparse

EVERGREEN_SEGMENTS = {
    "about",
    "careers",
    "company",
    "contact",
    "events",
    "help",
    "legal",
    "privacy",
    "supported-countries",
    "support",
    "terms",
    "unsubscribe",
}

SECTION_INDEX_SLUGS = {
    "announcements",
    "blog",
    "blogs",
    "changelog",
    "company",
    "docs",
    "documentation",
    "events",
    "news",
    "press",
    "research",
    "updates",
}

LOCALE_PREFIXES = {"de", "en", "es", "fr", "ja", "ko", "pt", "zh", "zh-cn", "zh-tw"}


def _segments(url: str) -> list[str]:
    path = (urlparse(url).path or "").strip("/").lower()
    return [part for part in path.split("/") if part]


def is_evergreen_or_directory_url(url: str | None) -> bool:
    if not url:
        return True
    parsed = urlparse(url)
    if not parsed.netloc:
        return True

    parts = _segments(url)
    if not parts:
        return True
    if any(part in EVERGREEN_SEGMENTS for part in parts):
        return True

    # Locale roots and locale section roots are usually evergreen.
    if len(parts) == 1 and parts[0] in LOCALE_PREFIXES:
        return True
    if len(parts) == 2 and parts[0] in LOCALE_PREFIXES and parts[1] in SECTION_INDEX_SLUGS:
        return True

    # Section landing pages like /blog, /news, /press should not rank as news.
    if parts[-1] in SECTION_INDEX_SLUGS and len(parts) <= 2:
        return True
    return False


def is_news_candidate_url(url: str | None, *, path_filter: str | None = None) -> bool:
    if not url:
        return False
    if path_filter and path_filter not in url:
        return False
    return not is_evergreen_or_directory_url(url)
