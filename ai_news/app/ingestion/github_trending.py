"""GitHub Trending connector — scrape trending repos for AI/ML."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List

import httpx
from bs4 import BeautifulSoup

from app.common.text import normalize_whitespace
from app.common.time import utcnow
from app.config import get_settings
from app.ingestion.base import CandidateItem

logger = logging.getLogger(__name__)

AI_KEYWORDS = {
    "llm", "transformer", "gpt", "diffusion", "neural", "machine-learning",
    "deep-learning", "ai", "nlp", "computer-vision", "reinforcement-learning",
    "langchain", "rag", "embedding", "fine-tune", "lora", "gguf", "onnx",
}


class GitHubTrendingConnector:
    def __init__(self, source_id: str):
        self.source_id = source_id
        self.url = "https://github.com/trending"

    def fetch_candidates(self, now: datetime | None = None) -> List[CandidateItem]:
        """Scrape GitHub Trending and filter for AI/ML repos."""
        now = now or utcnow()
        settings = get_settings()
        headers = {
            "User-Agent": settings.user_agent,
            "Accept": "text/html",
        }

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(self.url, headers=headers)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        items: List[CandidateItem] = []

        for article in soup.select("article.Box-row"):
            repo_link = article.select_one("h2 a")
            if not repo_link:
                continue
            repo_path = repo_link.get("href", "").strip("/")
            if not repo_path:
                continue

            desc_el = article.select_one("p")
            description = normalize_whitespace(desc_el.get_text(strip=True)) if desc_el else ""

            # Filter for AI/ML relevance
            combined = f"{repo_path} {description}".lower()
            if not any(kw in combined for kw in AI_KEYWORDS):
                continue

            stars_el = article.select_one("[class*='stargazers'], .float-sm-right")
            stars_text = stars_el.get_text(strip=True) if stars_el else "0"
            stars = 0
            if stars_text:
                try:
                    stars = int(stars_text.replace(",", "").split()[0])
                except (ValueError, IndexError):
                    stars = 0

            title = repo_path
            if description:
                title = f"{repo_path}: {description[:100]}"

            items.append(
                CandidateItem(
                    source_id=self.source_id,
                    external_id=repo_path,
                    url=f"https://github.com/{repo_path}",
                    title=title,
                    snippet=description,
                    published_at=None,
                    fetched_at=now,
                    social_github_stars=stars,
                )
            )

        logger.info("GitHub Trending: found %d AI/ML repos", len(items))
        return items
