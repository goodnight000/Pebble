from __future__ import annotations

from app.config import get_settings


async def fetch_rendered_html(url: str) -> str:
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Playwright not available") from exc

    settings = get_settings()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(user_agent=settings.user_agent)
        await page.goto(url, wait_until="networkidle", timeout=30000)
        content = await page.content()
        await browser.close()
        return content
