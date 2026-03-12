"""Wayback Machine helper for opportunistic paywall fallback."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


async def check_wayback(url: str) -> str | None:
    """Return closest archived URL if available, otherwise None."""
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(
                "https://archive.org/wayback/available",
                params={"url": url},
            )
            resp.raise_for_status()
            snapshot = (resp.json() or {}).get("archived_snapshots", {}).get("closest", {})
    except Exception as exc:
        logger.debug("Wayback lookup failed for %s: %s", url, exc)
        return None

    if snapshot.get("available") and snapshot.get("status") == "200":
        return snapshot.get("url")
    return None

