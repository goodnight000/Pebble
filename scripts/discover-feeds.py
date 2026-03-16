#!/usr/bin/env python3
"""
discover-feeds.py — Auto-discover correct feed URLs for disabled RSS/sitemap sources.

Loads config_sources.yml, finds disabled RSS/sitemap sources, probes for valid
feed URLs via HTML link discovery and common-path probing, then updates the
config file in-place (preserving YAML comments) with recovered feed URLs.
"""

import asyncio
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
import yaml
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_PATH = Path(__file__).resolve().parent.parent / "ai_news" / "app" / "config_sources.yml"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

FEED_ACCEPT = (
    "application/rss+xml, application/atom+xml, "
    "application/xml, text/xml, */*"
)

COMMON_FEED_PATHS = [
    "/feed", "/feed/", "/rss", "/rss/", "/rss.xml", "/feed.xml",
    "/atom.xml", "/index.xml",
    "/blog/feed", "/blog/feed/", "/blog/rss", "/blog/rss.xml",
    "/blog/feed.xml",
    "/feeds/posts/default",  # Blogger
    "/feed/rss", "/feed/atom",
]

# XML markers that confirm a response is a valid feed / sitemap
FEED_MARKERS = (b"<rss", b"<feed", b"<atom", b"<?xml", b"<channel",
                b"<urlset", b"<sitemapindex")

# Sources that are truly defunct — skip them
DEFUNCT_NAMES = {"Neptune AI", "Greentech Media", "Data Science Central",
                 "Determined AI", "Gradient AI"}

# Social-media source kinds — skip them
SOCIAL_KINDS = {"mastodon", "bluesky", "twitter"}

TIMEOUT = 20
SEMAPHORE_LIMIT = 30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_base_url(url: str) -> str:
    """Return scheme + netloc (+ optional path prefix for blog subdomains)."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def is_feed_content(body: bytes) -> bool:
    """Return True if *body* looks like XML feed / sitemap content."""
    # Check first 5000 bytes to avoid scanning huge payloads
    head = body[:5000].lower()
    return any(marker in head for marker in FEED_MARKERS)


def should_skip(source: dict) -> bool:
    """Return True if this source should be skipped."""
    name = source.get("name", "")
    kind = source.get("kind", "")
    if kind in SOCIAL_KINDS:
        return True
    for defunct in DEFUNCT_NAMES:
        if defunct in name:
            return True
    return False


def get_url_key(source: dict) -> str:
    """Return the YAML key used for the URL field."""
    if source.get("kind") == "sitemap":
        return "sitemap_url"
    return "feed_url"


def get_source_url(source: dict) -> str | None:
    key = get_url_key(source)
    return source.get(key)


# ---------------------------------------------------------------------------
# Feed discovery logic
# ---------------------------------------------------------------------------

async def validate_feed_url(client: httpx.AsyncClient, url: str) -> bool:
    """Check that *url* returns 200 and contains feed XML markers."""
    try:
        resp = await client.get(
            url,
            headers={"Accept": FEED_ACCEPT},
            follow_redirects=True,
            timeout=TIMEOUT,
        )
        if resp.status_code == 200 and is_feed_content(resp.content):
            return True
    except Exception:
        pass
    return False


async def discover_via_html_links(
    client: httpx.AsyncClient, base_url: str
) -> list[str]:
    """Fetch homepage HTML and extract <link rel="alternate"> feed URLs."""
    candidates = []
    try:
        resp = await client.get(
            base_url,
            headers={"Accept": "text/html"},
            follow_redirects=True,
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return candidates
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("link", rel="alternate"):
            link_type = (link.get("type") or "").lower()
            if link_type in (
                "application/rss+xml",
                "application/atom+xml",
                "application/xml",
                "text/xml",
            ):
                href = link.get("href")
                if href:
                    # Resolve relative URLs
                    full = urljoin(base_url, href)
                    candidates.append(full)
    except Exception:
        pass
    return candidates


async def discover_via_path_probing(
    client: httpx.AsyncClient, base_url: str
) -> list[str]:
    """Try common feed paths and return those that validate."""
    valid = []

    async def _probe(path: str):
        url = base_url.rstrip("/") + path
        if await validate_feed_url(client, url):
            valid.append(url)

    # Probe all paths concurrently (they share the client semaphore)
    await asyncio.gather(*[_probe(p) for p in COMMON_FEED_PATHS])
    return valid


async def discover_feed(
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
    source: dict,
) -> tuple[dict, str | None, str]:
    """
    Try to find a working feed URL for *source*.
    Returns (source, new_url_or_None, method_used).
    """
    async with sem:
        url = get_source_url(source)
        if not url:
            return source, None, "no_url"

        base_url = extract_base_url(url)

        # 0. Quick check: maybe the existing URL already works
        if await validate_feed_url(client, url):
            return source, url, "existing_works"

        # 1. HTML link discovery (preferred)
        html_candidates = await discover_via_html_links(client, base_url)
        for c in html_candidates:
            if await validate_feed_url(client, c):
                return source, c, "html_link"

        # 2. Path probing
        path_hits = await discover_via_path_probing(client, base_url)
        if path_hits:
            return source, path_hits[0], "path_probe"

        # 3. If base URL differs from feed_url domain (e.g. feeds.megaphone.fm),
        #    also try the feed_url domain as-is
        feed_parsed = urlparse(url)
        if feed_parsed.netloc != urlparse(base_url).netloc:
            alt_base = f"{feed_parsed.scheme}://{feed_parsed.netloc}"
            html2 = await discover_via_html_links(client, alt_base)
            for c in html2:
                if await validate_feed_url(client, c):
                    return source, c, "html_link_alt"
            path2 = await discover_via_path_probing(client, alt_base)
            if path2:
                return source, path2[0], "path_probe_alt"

        return source, None, "not_found"


# ---------------------------------------------------------------------------
# Config file update (line-by-line, preserving comments)
# ---------------------------------------------------------------------------

def update_config_file(recoveries: list[tuple[dict, str]]):
    """
    For each (source, new_url), find the source block by name in the YAML
    and update its feed_url/sitemap_url and enabled lines.
    """
    lines = CONFIG_PATH.read_text(encoding="utf-8").splitlines(keepends=True)

    for source, new_url in recoveries:
        name = source["name"]
        url_key = get_url_key(source)
        old_url = get_source_url(source)

        # Find the line with this source's name
        name_pattern = re.compile(r'^\s*-?\s*name:\s*["\']?' + re.escape(name) + r'["\']?\s*$')
        name_idx = None
        for i, line in enumerate(lines):
            if name_pattern.match(line):
                name_idx = i
                break

        if name_idx is None:
            print(f"  WARNING: could not find source '{name}' in config file")
            continue

        # Search forward from name_idx for the url_key line and enabled line
        # (within the same source block — stop at next "- name:" or end)
        url_line_idx = None
        enabled_line_idx = None

        for j in range(name_idx + 1, min(name_idx + 20, len(lines))):
            stripped = lines[j].lstrip()
            # Stop if we hit the next source entry
            if stripped.startswith("- name:"):
                break
            if stripped.startswith(f"{url_key}:") and url_line_idx is None:
                url_line_idx = j
            if stripped.startswith("enabled:") and enabled_line_idx is None:
                enabled_line_idx = j

        # Update feed_url / sitemap_url line
        if url_line_idx is not None and new_url != old_url:
            indent = lines[url_line_idx][: len(lines[url_line_idx]) - len(lines[url_line_idx].lstrip())]
            lines[url_line_idx] = f'{indent}{url_key}: "{new_url}"\n'

        # Update enabled line
        if enabled_line_idx is not None:
            old_line = lines[enabled_line_idx]
            indent = old_line[: len(old_line) - len(old_line.lstrip())]
            # Drop any inline comment about 404/disabled
            lines[enabled_line_idx] = f"{indent}enabled: true\n"

    CONFIG_PATH.write_text("".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    # Load config
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    sources = config.get("sources", [])

    # Filter to disabled RSS/sitemap sources
    disabled = [
        s for s in sources
        if s.get("enabled") is False
        and s.get("kind") in ("rss", "sitemap")
        and not should_skip(s)
    ]

    print(f"Found {len(disabled)} disabled RSS/sitemap sources to probe")
    print(f"(skipping {sum(1 for s in sources if s.get('enabled') is False and should_skip(s))} defunct/social sources)")
    print()

    sem = asyncio.Semaphore(SEMAPHORE_LIMIT)
    t0 = time.time()

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=TIMEOUT,
    ) as client:
        tasks = [discover_feed(sem, client, s) for s in disabled]
        results = await asyncio.gather(*tasks)

    elapsed = time.time() - t0

    # Categorize results
    already_working = []
    recovered = []
    failed = []

    for source, new_url, method in results:
        if method == "existing_works":
            already_working.append((source, new_url, method))
        elif new_url is not None and method != "existing_works":
            recovered.append((source, new_url, method))
        else:
            failed.append((source, new_url, method))

    # Print report
    print("=" * 72)
    print(f"FEED DISCOVERY REPORT  ({elapsed:.1f}s elapsed)")
    print("=" * 72)

    if already_working:
        print(f"\n--- EXISTING URL ALREADY WORKS ({len(already_working)}) ---")
        for source, url, _ in already_working:
            print(f"  [OK] {source['name']}")
            print(f"       {url}")

    if recovered:
        print(f"\n--- RECOVERED ({len(recovered)}) ---")
        for source, new_url, method in recovered:
            old_url = get_source_url(source)
            print(f"  [RECOVERED] {source['name']}  ({method})")
            print(f"       old: {old_url}")
            print(f"       new: {new_url}")

    if failed:
        print(f"\n--- STILL BROKEN ({len(failed)}) ---")
        for source, _, method in failed:
            url = get_source_url(source)
            print(f"  [FAIL] {source['name']}")
            print(f"       {url}  ({method})")

    print()
    print(f"Summary: {len(already_working)} already working, "
          f"{len(recovered)} recovered, {len(failed)} still broken")
    print(f"Total probed: {len(disabled)}")

    # Apply recoveries to config file
    to_update = [(s, u) for s, u, _ in already_working] + \
                [(s, u) for s, u, _ in recovered]

    if to_update:
        print(f"\nUpdating config file with {len(to_update)} sources...")
        update_config_file(to_update)
        print("Done. Config file updated.")
    else:
        print("\nNo sources to update.")


if __name__ == "__main__":
    asyncio.run(main())
