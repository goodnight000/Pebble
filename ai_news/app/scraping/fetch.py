from __future__ import annotations

import asyncio
import logging
import random
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.common.rate_limit import rate_limiter
from app.config import get_settings

logger = logging.getLogger(__name__)

_robots_cache: dict[str, RobotFileParser] = {}

# Cache for conditional GET headers (ETag / Last-Modified) keyed by URL.
_etag_cache: dict[str, dict[str, str]] = {}


async def _allowed_by_robots(url: str, user_agent: str) -> bool:
    parsed = urlparse(url)
    domain = parsed.netloc
    rp = _robots_cache.get(domain)
    if not rp:
        robots_url = f"{parsed.scheme}://{domain}/robots.txt"
        rp = RobotFileParser()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(robots_url)
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    rp = None
        except Exception:
            rp = None
        if rp:
            _robots_cache[domain] = rp
    if not rp:
        return True
    return rp.can_fetch(user_agent, url)


def jittered_interval(base_seconds: float, jitter_fraction: float = 0.20) -> float:
    """Return *base_seconds* with +-jitter_fraction random jitter applied."""
    low = base_seconds * (1.0 - jitter_fraction)
    high = base_seconds * (1.0 + jitter_fraction)
    return random.uniform(low, high)


def _fetch_with_browser_tls(url: str) -> tuple[str, str]:
    """Fallback fetch using curl_cffi for browser TLS fingerprint impersonation.

    Many sites (Cloudflare, Pantheon, WordPress) return 403 to httpx because
    its TLS ClientHello doesn't match any known browser. curl_cffi uses
    libcurl with browser-impersonation patches for an authentic fingerprint.
    """
    from curl_cffi import requests as cffi_requests

    resp = cffi_requests.get(
        url,
        impersonate="chrome",
        timeout=25,
        allow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text, str(resp.url)


async def fetch_html(
    url: str,
    rate_limit_rps: float = 0.5,
    max_retries: int = 3,
    base_delay: float = 2.0,
) -> tuple[str, str]:
    """Fetch HTML with conditional GET, exponential backoff on 429/503, and jitter.

    On 403, falls back to curl_cffi with browser TLS fingerprinting to bypass
    bot-protection (Cloudflare, etc.).

    Returns (html_text, final_url).
    """
    settings = get_settings()
    parsed = urlparse(url)
    domain = parsed.netloc
    await rate_limiter.acquire(domain, rate_limit_rps)
    headers: dict[str, str] = {"User-Agent": settings.user_agent}

    if not await _allowed_by_robots(url, settings.user_agent):
        raise RuntimeError("Blocked by robots.txt")

    # Conditional GET: reuse ETag / Last-Modified from previous fetch.
    cached = _etag_cache.get(url)
    if cached:
        if "etag" in cached:
            headers["If-None-Match"] = cached["etag"]
        if "last-modified" in cached:
            headers["If-Modified-Since"] = cached["last-modified"]

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            response = await client.get(url, headers=headers)

            if response.status_code == 304:
                raise NotModifiedError(url)

            if response.status_code == 403:
                # Bot-blocked — try curl_cffi with browser TLS fingerprint.
                logger.info("fetch_html %s returned 403, retrying with browser TLS", url)
                try:
                    text, final_url = await asyncio.to_thread(_fetch_with_browser_tls, url)
                    return text, final_url
                except Exception as cffi_exc:
                    logger.warning("fetch_html browser TLS fallback also failed for %s: %s", url, cffi_exc)
                    response.raise_for_status()  # raise the original 403

            if response.status_code in (429, 503) and attempt < max_retries:
                delay = jittered_interval(base_delay * (2 ** attempt))
                logger.warning(
                    "fetch_html %s returned %d, retrying in %.1fs (attempt %d/%d)",
                    url, response.status_code, delay, attempt + 1, max_retries,
                )
                await asyncio.sleep(delay)
                last_exc = httpx.HTTPStatusError(
                    f"{response.status_code}", request=response.request, response=response,
                )
                continue

            response.raise_for_status()

            # Store conditional GET headers for next time.
            new_cache: dict[str, str] = {}
            if response.headers.get("etag"):
                new_cache["etag"] = response.headers["etag"]
            if response.headers.get("last-modified"):
                new_cache["last-modified"] = response.headers["last-modified"]
            if new_cache:
                _etag_cache[url] = new_cache

            return response.text, str(response.url)

    # All retries exhausted
    if last_exc:
        raise last_exc
    raise RuntimeError(f"fetch_html failed for {url} after {max_retries} retries")


class NotModifiedError(Exception):
    """Raised when the server returns 304 Not Modified."""

    def __init__(self, url: str):
        self.url = url
        super().__init__(f"Not modified: {url}")
