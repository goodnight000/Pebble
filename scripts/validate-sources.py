#!/usr/bin/env python3
"""Validate all sources in config_sources.yml.

Checks that RSS feed_urls return 200 and contain valid XML/feed data,
and that sitemap_urls return 200 and contain valid sitemap XML.
Reports failures, blocks (403/captcha), and redirects.
"""
from __future__ import annotations

import sys
import time
import yaml
import asyncio
import logging
from pathlib import Path
from dataclasses import dataclass, field

import httpx

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "ai_news" / "app" / "config_sources.yml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, application/atom+xml, text/xml, */*",
}

# Concurrency limit to avoid hammering servers
SEMAPHORE_LIMIT = 30
TIMEOUT = 25  # seconds


@dataclass
class ValidationResult:
    name: str
    kind: str
    url: str
    status_code: int | None = None
    error: str | None = None
    content_type: str | None = None
    redirect_url: str | None = None
    is_feed: bool = False
    is_blocked: bool = False
    response_size: int = 0


async def check_source(
    client: httpx.AsyncClient,
    source: dict,
    semaphore: asyncio.Semaphore,
) -> ValidationResult | None:
    name = source.get("name", "unknown")
    kind = source.get("kind", "")
    enabled = source.get("enabled", True)

    if not enabled:
        return ValidationResult(name=name, kind=kind, url="", error="DISABLED (skipped)")

    # Determine URL to check
    url = ""
    if kind == "rss":
        url = source.get("feed_url", "")
    elif kind == "sitemap":
        url = source.get("sitemap_url", "")
    elif kind in ("hn", "reddit", "twitter", "mastodon", "bluesky", "github",
                  "github_trending", "arxiv", "nvd", "congress",
                  "semantic_scholar", "hf_papers"):
        # API-based sources — check base_url or known endpoint
        url = source.get("base_url", "")
        if kind == "hf_papers":
            url = "https://huggingface.co/api/daily_papers"
        elif kind == "semantic_scholar":
            url = "https://api.semanticscholar.org/graph/v1/paper/search"
        elif not url:
            return ValidationResult(name=name, kind=kind, url="N/A", error="API source (no URL to check)")
    else:
        return ValidationResult(name=name, kind=kind, url="N/A", error=f"Unknown kind: {kind}")

    if not url:
        return ValidationResult(name=name, kind=kind, url="", error="No URL configured")

    async with semaphore:
        try:
            resp = await client.get(url, headers=HEADERS, follow_redirects=True, timeout=TIMEOUT)
            ct = resp.headers.get("content-type", "")
            body_preview = resp.text[:2000] if resp.status_code == 200 else ""

            result = ValidationResult(
                name=name,
                kind=kind,
                url=url,
                status_code=resp.status_code,
                content_type=ct,
                response_size=len(resp.content),
            )

            # Check for redirects
            if resp.history:
                result.redirect_url = str(resp.url)

            # Check for blocks
            if resp.status_code == 403:
                result.is_blocked = True
                result.error = "403 Forbidden (likely bot-blocked)"
            elif resp.status_code == 429:
                result.is_blocked = True
                result.error = "429 Too Many Requests (rate limited)"
            elif resp.status_code == 404:
                result.error = "404 Not Found"
            elif resp.status_code == 410:
                result.error = "410 Gone (feed removed)"
            elif resp.status_code >= 500:
                result.error = f"{resp.status_code} Server Error"
            elif resp.status_code == 200:
                # Check for Cloudflare challenge pages
                if "cf-browser-verification" in body_preview or "challenge-platform" in body_preview:
                    result.is_blocked = True
                    result.error = "Cloudflare challenge page (blocked)"
                # Check if response looks like a feed/sitemap
                elif kind == "rss":
                    if any(marker in body_preview for marker in ["<rss", "<feed", "<atom", "<?xml", "<channel"]):
                        result.is_feed = True
                    elif "<html" in body_preview.lower():
                        result.error = "200 but returns HTML (not a feed)"
                elif kind == "sitemap":
                    if any(marker in body_preview for marker in ["<urlset", "<sitemapindex", "<?xml"]):
                        result.is_feed = True
                    elif "<html" in body_preview.lower():
                        result.error = "200 but returns HTML (not a sitemap)"
            else:
                result.error = f"Unexpected status: {resp.status_code}"

            return result

        except httpx.TimeoutException:
            return ValidationResult(name=name, kind=kind, url=url, error="Timeout (>25s)")
        except httpx.ConnectError as e:
            return ValidationResult(name=name, kind=kind, url=url, error=f"Connection error: {e}")
        except Exception as e:
            return ValidationResult(name=name, kind=kind, url=url, error=f"Error: {e}")


async def main():
    # Load config
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    sources = config.get("sources", [])
    logger.info(f"Loaded {len(sources)} sources from {CONFIG_PATH}")

    semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)

    async with httpx.AsyncClient() as client:
        tasks = [check_source(client, src, semaphore) for src in sources]
        results = await asyncio.gather(*tasks)

    results = [r for r in results if r is not None]

    # Categorize results
    ok = [r for r in results if r.status_code == 200 and not r.error]
    disabled = [r for r in results if r.error and "DISABLED" in r.error]
    blocked = [r for r in results if r.is_blocked]
    not_found = [r for r in results if r.error and "404" in (r.error or "")]
    gone = [r for r in results if r.error and "410" in (r.error or "")]
    server_err = [r for r in results if r.status_code and r.status_code >= 500]
    timeout = [r for r in results if r.error and "Timeout" in (r.error or "")]
    conn_err = [r for r in results if r.error and "Connection error" in (r.error or "")]
    html_not_feed = [r for r in results if r.error and "returns HTML" in (r.error or "")]
    api_sources = [r for r in results if r.error and "API source" in (r.error or "")]
    other_err = [r for r in results if r.error and r not in disabled + blocked + not_found +
                 gone + server_err + timeout + conn_err + html_not_feed + api_sources]

    # Print report
    print("\n" + "=" * 80)
    print(f"SOURCE VALIDATION REPORT — {len(sources)} total sources")
    print("=" * 80)

    print(f"\n{'Status':<30} {'Count':>5}")
    print("-" * 35)
    print(f"{'OK (200 + valid feed/API)' :<30} {len(ok):>5}")
    print(f"{'Disabled (skipped)' :<30} {len(disabled):>5}")
    print(f"{'Blocked (403/captcha)' :<30} {len(blocked):>5}")
    print(f"{'Not Found (404)' :<30} {len(not_found):>5}")
    print(f"{'Gone (410)' :<30} {len(gone):>5}")
    print(f"{'Server Error (5xx)' :<30} {len(server_err):>5}")
    print(f"{'Timeout' :<30} {len(timeout):>5}")
    print(f"{'Connection Error' :<30} {len(conn_err):>5}")
    print(f"{'HTML instead of feed' :<30} {len(html_not_feed):>5}")
    print(f"{'API sources (no URL check)' :<30} {len(api_sources):>5}")
    print(f"{'Other errors' :<30} {len(other_err):>5}")

    def print_section(title, items):
        if not items:
            return
        print(f"\n--- {title} ({len(items)}) ---")
        for r in sorted(items, key=lambda x: x.name):
            msg = f"  {r.name}"
            if r.url:
                msg += f"\n    URL: {r.url}"
            if r.error:
                msg += f"\n    Error: {r.error}"
            if r.redirect_url:
                msg += f"\n    Redirected to: {r.redirect_url}"
            print(msg)

    print_section("BLOCKED (403 / Captcha)", blocked)
    print_section("NOT FOUND (404)", not_found)
    print_section("GONE (410)", gone)
    print_section("SERVER ERRORS (5xx)", server_err)
    print_section("TIMEOUTS", timeout)
    print_section("CONNECTION ERRORS", conn_err)
    print_section("HTML INSTEAD OF FEED", html_not_feed)
    print_section("OTHER ERRORS", other_err)

    # Summary
    working = len(ok) + len(api_sources)
    broken = len(blocked) + len(not_found) + len(gone) + len(server_err) + len(timeout) + len(conn_err) + len(html_not_feed) + len(other_err)
    print(f"\n{'=' * 80}")
    print(f"SUMMARY: {working} working | {len(disabled)} disabled | {broken} broken/problematic")
    print(f"{'=' * 80}")

    if broken > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
