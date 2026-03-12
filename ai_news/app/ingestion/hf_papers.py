"""Hugging Face Daily Papers connector for community-curated trending research."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List

import httpx

from app.common.text import normalize_whitespace
from app.common.time import utcnow
from app.config import get_settings
from app.ingestion.base import CandidateItem

logger = logging.getLogger(__name__)

API_URL = "https://huggingface.co/api/daily_papers"


class HFPapersConnector:
    def __init__(self, source_id: str):
        self.source_id = source_id

    def fetch_candidates(
        self,
        now: datetime | None = None,
        window_hours: int = 48,
    ) -> List[CandidateItem]:
        now = now or utcnow()
        cutoff = now - timedelta(hours=window_hours)
        settings = get_settings()
        headers = {"User-Agent": settings.user_agent, "Accept": "application/json"}

        items: List[CandidateItem] = []

        try:
            with httpx.Client(timeout=25, follow_redirects=True) as client:
                resp = client.get(API_URL, headers=headers)
                resp.raise_for_status()
                entries = resp.json()
        except Exception as exc:
            logger.warning("HF Papers connector failed: %s", exc)
            return items

        if not isinstance(entries, list):
            logger.warning("HF Papers: unexpected response type %s", type(entries).__name__)
            return items

        seen_ids: set[str] = set()

        for entry in entries:
            paper = entry.get("paper") or {}
            paper_id = paper.get("id")
            if not paper_id or paper_id in seen_ids:
                continue
            seen_ids.add(paper_id)

            title = normalize_whitespace(paper.get("title") or "")
            if not title:
                continue

            # Use ai_summary if available, fall back to regular summary.
            snippet = normalize_whitespace(
                paper.get("ai_summary") or paper.get("summary") or ""
            )

            # Parse publication date.
            pub_date = None
            pub_raw = paper.get("publishedAt")
            if pub_raw:
                try:
                    pub_date = datetime.fromisoformat(pub_raw.replace("Z", "+00:00"))
                except ValueError:
                    pass

            if pub_date and pub_date < cutoff:
                continue

            # Build canonical arxiv URL.
            url = f"https://arxiv.org/abs/{paper_id}"

            authors_list = paper.get("authors") or []
            author_names = ", ".join(
                a.get("name", "") for a in authors_list[:5]
            )

            upvotes = int(paper.get("upvotes") or 0)
            github_stars = None
            github_repo = paper.get("githubRepo")
            if github_repo:
                github_stars = int(paper.get("githubStars") or 0)

            items.append(
                CandidateItem(
                    source_id=self.source_id,
                    external_id=f"hf:{paper_id}",
                    url=url,
                    title=title,
                    snippet=snippet,
                    author=author_names or None,
                    published_at=pub_date,
                    fetched_at=now,
                    social_hn_points=upvotes,
                    social_github_stars=github_stars,
                )
            )

        return items
