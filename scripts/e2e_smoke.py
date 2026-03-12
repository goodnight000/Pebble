from __future__ import annotations

import json
import sys
import time

from playwright.sync_api import TimeoutError, sync_playwright


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5173"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(base_url, wait_until="domcontentloaded")
        # Avoid waiting for `networkidle` since the app keeps an SSE connection open.
        page.wait_for_selector("text=Daily Digest", timeout=30_000)

        # The page triggers a refresh on mount. Give it time to seed + ingest.
        deadline = time.time() + 60
        last_error = None
        while time.time() < deadline:
            try:
                page.wait_for_selector('div[role="link"]', timeout=5000)
                break
            except TimeoutError as exc:
                last_error = exc
                page.wait_for_timeout(1000)

        cards = page.locator('div[role="link"]')
        count = cards.count()
        page.screenshot(path="/tmp/aipulse_smoke.png", full_page=True)
        browser.close()

        if count <= 0:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "reason": "no_news_cards_rendered",
                        "base_url": base_url,
                        "screenshot": "/tmp/aipulse_smoke.png",
                        "last_error": str(last_error) if last_error else None,
                    }
                )
            )
            return 1

        print(json.dumps({"ok": True, "news_cards": count, "base_url": base_url, "screenshot": "/tmp/aipulse_smoke.png"}))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
