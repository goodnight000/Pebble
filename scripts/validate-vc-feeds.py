"""Validate all VC firm feed and sitemap URLs are reachable and return valid content."""
from __future__ import annotations

import sys
import yaml
import httpx
import feedparser
from lxml import etree
from pathlib import Path

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}

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


def _fetch_bytes(url: str, *, accept: str = "*/*") -> bytes:
    """Fetch URL bytes, falling back to curl_cffi if httpx fails."""
    headers = {**BROWSER_HEADERS, "Accept": accept}
    try:
        resp = httpx.get(url, headers=headers, timeout=25, follow_redirects=True)
        resp.raise_for_status()
        return resp.content
    except (httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout):
        # Fallback: use curl_cffi for browser TLS fingerprinting
        from curl_cffi import requests as cffi_requests
        resp = cffi_requests.get(
            url, impersonate="chrome", timeout=25, allow_redirects=True,
            headers={"Accept": accept},
        )
        resp.raise_for_status()
        return resp.content


def validate_rss(name: str, url: str) -> tuple[bool, str]:
    try:
        content = _fetch_bytes(url, accept="application/rss+xml, application/atom+xml, application/xml, text/xml, */*")
        parsed = feedparser.parse(content)
        n_entries = len(parsed.entries)
        if n_entries == 0 and not parsed.feed.get("title"):
            return False, "No entries and no feed title — likely not a valid feed"
        return True, f"OK — {n_entries} entries, feed title: {parsed.feed.get('title', 'N/A')}"
    except Exception as e:
        return False, f"Error: {e}"


def validate_sitemap(name: str, url: str, path_filter: str | None) -> tuple[bool, str]:
    try:
        content = _fetch_bytes(url, accept="application/xml, text/xml, */*")
        # Check if we got HTML instead of XML
        if content.strip()[:15].lower().startswith(b'<!doctype html') or content.strip()[:6].lower() == b'<html>':
            return False, "Returns HTML, not XML"
        root = etree.fromstring(content)
        tag = etree.QName(root).localname.lower()
        if tag == "sitemapindex":
            child_locs = root.xpath(".//*[local-name()='sitemap']/*[local-name()='loc']/text()")
            return True, f"OK — sitemap index with {len(child_locs)} child sitemaps"
        url_elems = root.xpath(".//*[local-name()='url']")
        if path_filter:
            matching = [u for u in url_elems
                        if any(path_filter in (loc.text or "")
                               for loc in u.xpath("./*[local-name()='loc']"))]
            return True, f"OK — {len(url_elems)} total URLs, {len(matching)} match path_filter '{path_filter}'"
        return True, f"OK — {len(url_elems)} URLs"
    except etree.XMLSyntaxError as e:
        return False, f"XML parse error: {e}"
    except Exception as e:
        return False, f"Error: {e}"


def main():
    config_path = Path(__file__).resolve().parent.parent / "ai_news" / "app" / "config_sources.yml"
    cfg = yaml.safe_load(config_path.open())
    sources = cfg.get("sources", [])

    vc_sources = [s for s in sources if is_vc_source(s["name"])]
    print(f"\nValidating {len(vc_sources)} VC sources...\n")

    failures = []
    for src in vc_sources:
        name = src["name"]
        kind = src["kind"]
        url = src.get("feed_url") or src.get("sitemap_url", "")

        if not src.get("enabled", True):
            print(f"  [SKIP] {name} (disabled)")
            print()
            continue

        if kind == "rss":
            ok, msg = validate_rss(name, url)
        elif kind == "sitemap":
            path_filter = src.get("path_filter")
            ok, msg = validate_sitemap(name, url, path_filter)
        else:
            ok, msg = False, f"Unknown kind: {kind}"

        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name} ({kind})")
        print(f"         {url}")
        print(f"         {msg}")
        print()
        if not ok:
            failures.append((name, msg))

    print(f"\n{'='*60}")
    print(f"Results: {len(vc_sources) - len(failures)}/{len(vc_sources)} passed")
    if failures:
        print(f"\nFailed sources:")
        for name, msg in failures:
            print(f"  - {name}: {msg}")
        sys.exit(1)
    else:
        print("All VC sources validated successfully!")
        sys.exit(0)


if __name__ == "__main__":
    main()
