"""Test actual connector ingestion for all VC firm sources."""
from __future__ import annotations

import sys
import os
import traceback
from pathlib import Path

# Add the ai_news directory to Python path so we can import app modules
ai_news_dir = Path(__file__).resolve().parent.parent / "ai_news"
sys.path.insert(0, str(ai_news_dir))
os.chdir(ai_news_dir)

import yaml
from datetime import datetime, timezone

from app.ingestion.rss import RSSConnector
from app.ingestion.sitemap import SitemapConnector

# Match source names from config_sources.yml under the VC sections.
# We look for the section headers "VC FIRMS" to identify them, but since YAML
# doesn't have structured section metadata, we match by name keywords.
VC_KEYWORDS = [
    "Air Street", "Radical Ventures", "Madrona", "Insight Partners",
    "Sequoia Capital", "Battery Ventures", "Menlo Ventures", "a16z",
    "Tunguz", "Elad Gil", "Nathan Benaich", "Y Combinator Blog",
    "Balderton", "M12", "Obvious", "Greylock", "Coatue", "GV (",
    "Bessemer", "Sapphire", "NFX", "Lightspeed", "AI Fund", "Norwest",
    "Kleiner", "General Catalyst", "Antler", "Lux Capital", "Accel",
    "Felicis", "Scale Venture", "Amplify", "Emergence", "Khosla",
]


def is_vc_source(name: str) -> bool:
    return any(kw in name for kw in VC_KEYWORDS)


def main():
    config_path = ai_news_dir / "app" / "config_sources.yml"
    cfg = yaml.safe_load(config_path.open())
    sources = cfg.get("sources", [])
    vc_sources = [s for s in sources if is_vc_source(s["name"]) and s.get("enabled", True)]

    print(f"\nTesting actual connector ingestion for {len(vc_sources)} VC sources...\n")

    now = datetime.now(timezone.utc)
    failures = []
    total_candidates = 0

    for src in vc_sources:
        name = src["name"]
        kind = src["kind"]
        browser_ua = src.get("browser_ua", False)

        try:
            if kind == "rss":
                feed_url = src.get("feed_url", "")
                connector = RSSConnector("test-source-id", feed_url, browser_ua=browser_ua)
                candidates = connector.fetch_candidates(now)
                print(f"  [PASS] {name} (rss)")
                print(f"         {len(candidates)} candidates returned")
                if candidates:
                    print(f"         Sample: {candidates[0].title[:80]}")
                total_candidates += len(candidates)

            elif kind == "sitemap":
                # Mirror the seed_sources.py mapping:
                # YAML sitemap_url -> connector sitemap_url
                # YAML path_filter -> connector path_filter
                sitemap_url = src.get("feed_url") or src.get("sitemap_url", "")
                path_filter = src.get("base_url") or src.get("path_filter")
                lastmod_optional = src.get("lastmod_optional", False)
                connector = SitemapConnector(
                    "test-source-id",
                    sitemap_url,
                    path_filter=path_filter,
                    browser_ua=browser_ua,
                    lastmod_optional=lastmod_optional,
                )
                candidates = connector.fetch_candidates(now)
                print(f"  [PASS] {name} (sitemap, lastmod_optional={lastmod_optional})")
                print(f"         {len(candidates)} candidates returned")
                if candidates:
                    print(f"         Sample: {candidates[0].title[:80]}")
                total_candidates += len(candidates)

            else:
                print(f"  [SKIP] {name} — unknown kind: {kind}")

        except Exception as e:
            print(f"  [FAIL] {name} ({kind})")
            print(f"         Error: {e}")
            traceback.print_exc()
            failures.append((name, str(e)))

        print()

    print(f"{'='*60}")
    print(f"Results: {len(vc_sources) - len(failures)}/{len(vc_sources)} passed")
    print(f"Total candidates returned: {total_candidates}")
    if failures:
        print(f"\nFailed sources:")
        for name, msg in failures:
            print(f"  - {name}: {msg}")
        sys.exit(1)
    else:
        print("\nAll VC sources ingested successfully through actual connectors!")
        sys.exit(0)


if __name__ == "__main__":
    main()
