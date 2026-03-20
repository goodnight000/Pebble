from __future__ import annotations

from app.config import load_source_config
from app.db import session_scope
from app.models import Source


def dedupe_sources_by_name(sources: list[dict]) -> list[dict]:
    deduped: dict[str, dict] = {}
    for src in sources:
        name = src.get("name")
        if not name:
            continue
        deduped[name] = src
    return list(deduped.values())


def seed_sources():
    config = load_source_config()
    sources = dedupe_sources_by_name(config.get("sources", []))
    with session_scope() as session:
        # Load all existing sources in one query instead of N individual lookups.
        existing_map = {s.name: s for s in session.query(Source).all()}
        for src in sources:
            existing = existing_map.get(src["name"])
            if not existing:
                existing = Source(name=src["name"])
                session.add(existing)
                existing_map[src["name"]] = existing
            feed_url = src.get("feed_url")
            base_url = src.get("base_url")
            if src.get("kind") == "sitemap":
                # Keep schema simple: persist sitemap_url in feed_url and path_filter in base_url.
                feed_url = feed_url or src.get("sitemap_url")
                base_url = base_url or src.get("path_filter")
            existing.kind = src.get("kind")
            existing.base_url = base_url
            existing.feed_url = feed_url
            existing.authority = src.get("authority", 0.5)
            existing.always_scrape = src.get("always_scrape", False)
            existing.priority_poll = src.get("priority_poll", False)
            existing.enabled = src.get("enabled", True)
            existing.rate_limit_rps = src.get("rate_limit_rps", 0.5)


if __name__ == "__main__":
    seed_sources()
