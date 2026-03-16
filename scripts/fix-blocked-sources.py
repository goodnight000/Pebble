#!/usr/bin/env python3
"""
Test disabled sources in config_sources.yml with curl_cffi browser TLS
impersonation. Sources that respond 200 with valid feed/sitemap content
via curl_cffi but fail with plain httpx are recoverable by adding
`browser_ua: true`.

Updates config_sources.yml in place for recovered sources:
  - Sets enabled: true
  - Adds browser_ua: true (if not already present)
Preserves YAML comments via line-by-line string replacement.
"""
from __future__ import annotations

import asyncio
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx

try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    print("ERROR: curl_cffi not installed. Run:")
    print("  source ai_news/.venv/bin/activate && pip install curl_cffi")
    sys.exit(1)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "ai_news" / "app" / "config_sources.yml"
TIMEOUT = 25
SEMAPHORE_LIMIT = 10

# Minimum bytes to treat as valid content (avoid empty 200 responses)
MIN_CONTENT_LENGTH = 200

# Markers that indicate valid RSS/Atom/Sitemap XML
FEED_MARKERS = (
    b"<rss",
    b"<feed",
    b"<atom",
    b"<urlset",
    b"<sitemapindex",
    b"<?xml",
    b"<channel>",
)


@dataclass
class DisabledSource:
    name: str
    kind: str  # "rss" or "sitemap"
    url: str  # feed_url or sitemap_url
    line_start: int  # first line index (0-based) of "- name:" in config
    url_line: int  # line index of feed_url/sitemap_url
    enabled_line: int  # line index of "enabled: false"
    has_browser_ua: bool = False
    browser_ua_line: int | None = None
    comment: str = ""  # inline or preceding comment about why disabled


@dataclass
class TestResult:
    source: DisabledSource
    httpx_status: int | str = "N/A"
    curl_status: int | str = "N/A"
    curl_has_content: bool = False
    recovered: bool = False
    error: str = ""


def parse_disabled_sources(lines: list[str]) -> list[DisabledSource]:
    """Parse config_sources.yml lines to find all disabled sources with feed/sitemap URLs."""
    sources: list[DisabledSource] = []
    i = 0
    in_sources_section = False

    while i < len(lines):
        stripped = lines[i].strip()

        # Detect the top-level "sources:" key
        if stripped == "sources:":
            in_sources_section = True
            i += 1
            continue

        if not in_sources_section:
            i += 1
            continue

        # Each source starts with "- name:"
        match = re.match(r'^(\s+)-\s+name:\s*"(.+)"', lines[i])
        if not match:
            i += 1
            continue

        name = match.group(2)
        block_start = i
        i += 1

        # Read the rest of this source block
        kind = ""
        url = ""
        url_line = -1
        enabled = None
        enabled_line = -1
        has_browser_ua = False
        browser_ua_line = None
        comment = ""

        while i < len(lines):
            s = lines[i].strip()
            # Next source block or section
            if s.startswith("- name:") or (s and not s.startswith("#") and not s.startswith("-") and ":" in s and not s.startswith("kind") and not s.startswith("feed") and not s.startswith("sitemap") and not s.startswith("path") and not s.startswith("authority") and not s.startswith("always") and not s.startswith("priority") and not s.startswith("enabled") and not s.startswith("browser") and not s.startswith("lastmod") and not s.startswith("query") and not s.startswith("subreddits") and re.match(r'^[a-z_]+:', s) and not any(s.startswith(k) for k in ["kind:", "feed_url:", "sitemap_url:", "path_filter:", "authority:", "always_scrape:", "priority_poll:", "enabled:", "browser_ua:", "lastmod_optional:", "query:", "subreddits:"])):
                break
            if s == "" or s.startswith("- name:"):
                break

            if s.startswith("kind:"):
                kind = s.split(":", 1)[1].strip().strip('"')
            elif s.startswith("feed_url:"):
                url = s.split(":", 1)[1].strip().strip('"')
                # feed_url value includes the ":" from https:
                url = "feed_url:".join(lines[i].split("feed_url:")[1:]).strip().strip('"')
                url_line = i
            elif s.startswith("sitemap_url:"):
                url = "sitemap_url:".join(lines[i].split("sitemap_url:")[1:]).strip().strip('"')
                url_line = i
            elif s.startswith("enabled:"):
                val = s.split(":", 1)[1].strip()
                # Handle inline comments: "enabled: false  # 403 bot-blocked"
                if "#" in val:
                    parts = val.split("#", 1)
                    enabled = parts[0].strip().lower() == "true"
                    comment = parts[1].strip()
                else:
                    enabled = val.lower() == "true"
                enabled_line = i
            elif s.startswith("browser_ua:"):
                has_browser_ua = True
                browser_ua_line = i
            elif s.startswith("#"):
                # Comment line within block — may describe why disabled
                if not comment:
                    comment = s.lstrip("# ").strip()

            i += 1

        if enabled is False and url and url_line >= 0 and kind in ("rss", "sitemap"):
            sources.append(DisabledSource(
                name=name,
                kind=kind,
                url=url,
                line_start=block_start,
                url_line=url_line,
                enabled_line=enabled_line,
                has_browser_ua=has_browser_ua,
                browser_ua_line=browser_ua_line,
                comment=comment,
            ))

    return sources


async def test_source(sem: asyncio.Semaphore, source: DisabledSource) -> TestResult:
    """Test a source URL with httpx then curl_cffi."""
    result = TestResult(source=source)

    async with sem:
        # 1. Test with regular httpx
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0 (compatible; AIPulseBot/1.0)"},
            ) as client:
                resp = await client.get(source.url)
                result.httpx_status = resp.status_code
        except Exception as e:
            result.httpx_status = f"ERR:{type(e).__name__}"

        # 2. Test with curl_cffi (sync, via executor)
        loop = asyncio.get_running_loop()
        try:
            def _curl_fetch():
                r = cffi_requests.get(
                    source.url,
                    impersonate="chrome",
                    timeout=TIMEOUT,
                    allow_redirects=True,
                    headers={
                        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
                    },
                )
                return r.status_code, r.content

            status, content = await loop.run_in_executor(None, _curl_fetch)
            result.curl_status = status

            if status == 200 and content and len(content) >= MIN_CONTENT_LENGTH:
                content_lower = content[:2000].lower()
                if any(marker in content_lower for marker in FEED_MARKERS):
                    result.curl_has_content = True
                    result.recovered = True
                else:
                    result.error = "200 but no valid XML/feed markers"
            elif status == 200:
                result.error = f"200 but content too small ({len(content or b'')} bytes)"
            else:
                result.error = f"HTTP {status}"
        except Exception as e:
            result.curl_status = f"ERR:{type(e).__name__}"
            result.error = str(e)[:100]

    return result


def apply_recoveries(lines: list[str], results: list[TestResult]) -> list[str]:
    """Update config lines for recovered sources. Process in reverse line order
    so insertions don't shift later line indices."""
    recovered = [r for r in results if r.recovered]
    # Sort by enabled_line descending so we can insert without index shifts
    recovered.sort(key=lambda r: r.source.enabled_line, reverse=True)

    for r in recovered:
        src = r.source
        # 1. Set enabled: true (preserve any inline comment)
        old_enabled = lines[src.enabled_line]
        # Replace "enabled: false" with "enabled: true", keep rest of line
        new_enabled = re.sub(
            r'enabled:\s*false',
            'enabled: true',
            old_enabled,
            flags=re.IGNORECASE,
        )
        # Update/remove comment about being blocked
        # Remove comments about 403/blocked/dead since it's now recovered
        new_enabled = re.sub(
            r'\s*#\s*(403[^;]*|bot[-\s]?blocked[^;]*|Cloudflare[^;]*)',
            '',
            new_enabled,
        ).rstrip() + "\n"
        lines[src.enabled_line] = new_enabled

        # 2. Add browser_ua: true if not already present
        if not src.has_browser_ua:
            # Determine indentation from the url line
            url_line_text = lines[src.url_line]
            indent = re.match(r'^(\s+)', url_line_text)
            indent_str = indent.group(1) if indent else "    "
            browser_ua_line = f"{indent_str}browser_ua: true\n"
            # Insert after the url line
            lines.insert(src.url_line + 1, browser_ua_line)

            # Shift enabled_line index if it comes after insertion point
            # (already handled by reverse processing order — enabled_line
            #  is always after url_line for the same source)

    return lines


async def main():
    if not CONFIG_PATH.exists():
        print(f"ERROR: Config not found at {CONFIG_PATH}")
        sys.exit(1)

    print(f"Reading {CONFIG_PATH}")
    lines = CONFIG_PATH.read_text().splitlines(keepends=True)

    sources = parse_disabled_sources(lines)
    # Filter out sources that don't have HTTP(S) URLs (e.g. twitter, mastodon, bluesky)
    sources = [s for s in sources if s.url.startswith("http")]

    print(f"Found {len(sources)} disabled sources with feed/sitemap URLs to test\n")

    if not sources:
        print("Nothing to test.")
        return

    # Test all sources concurrently
    sem = asyncio.Semaphore(SEMAPHORE_LIMIT)
    tasks = [test_source(sem, s) for s in sources]
    results = await asyncio.gather(*tasks)

    # Categorize results
    recovered = [r for r in results if r.recovered]
    blocked_both = [r for r in results if not r.recovered and "ERR" not in str(r.curl_status)]
    errored = [r for r in results if "ERR" in str(r.curl_status)]

    # Print detailed results
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)

    for r in results:
        icon = "RECOVERABLE" if r.recovered else "STILL BLOCKED"
        print(f"\n  [{icon}] {r.source.name}")
        print(f"    URL: {r.source.url}")
        print(f"    httpx: {r.httpx_status}  |  curl_cffi: {r.curl_status}  |  valid content: {r.curl_has_content}")
        if r.error:
            print(f"    note: {r.error}")
        if r.source.comment:
            print(f"    original comment: {r.source.comment}")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"  Total disabled sources tested:  {len(results)}")
    print(f"  Recoverable with browser_ua:    {len(recovered)}")
    print(f"  Still blocked / not a feed:     {len(blocked_both)}")
    print(f"  Errors (timeout/DNS/etc):       {len(errored)}")

    if recovered:
        print(f"\n  Recoverable sources:")
        for r in recovered:
            print(f"    - {r.source.name}")

        # Apply changes
        print(f"\nApplying changes to {CONFIG_PATH} ...")
        # Re-read to be safe
        lines = CONFIG_PATH.read_text().splitlines(keepends=True)
        # Re-parse to get fresh line numbers (file hasn't changed since first read)
        lines = apply_recoveries(lines, recovered)
        CONFIG_PATH.write_text("".join(lines))
        print(f"Updated {len(recovered)} sources: set enabled=true, added browser_ua=true")
    else:
        print("\nNo sources recoverable via browser_ua. Config unchanged.")


if __name__ == "__main__":
    asyncio.run(main())
