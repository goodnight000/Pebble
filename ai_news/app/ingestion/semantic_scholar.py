"""Semantic Scholar connector for trending/high-citation recent CS papers."""
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

# Bulk endpoint always returns up to 1000 per call; we truncate in code.
BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"

FIELDS = ",".join([
    "title",
    "abstract",
    "authors",
    "citationCount",
    "influentialCitationCount",
    "url",
    "openAccessPdf",
    "publicationDate",
    "year",
])


class SemanticScholarConnector:
    def __init__(self, source_id: str):
        self.source_id = source_id

    def fetch_candidates(
        self,
        now: datetime | None = None,
        max_results: int = 100,
    ) -> List[CandidateItem]:
        now = now or utcnow()
        settings = get_settings()
        api_key = getattr(settings, "semantic_scholar_api_key", None) or ""

        headers = {"User-Agent": settings.user_agent, "Accept": "application/json"}
        if api_key:
            headers["x-api-key"] = api_key

        # Fetch papers from the current year, sorted by citation count.
        # The bulk endpoint ignores `limit` and returns up to 1000 per call.
        current_year = now.year
        params = {
            "query": "artificial intelligence machine learning",
            "fieldsOfStudy": "Computer Science",
            "year": f"{current_year}",
            "sort": "citationCount:desc",
            "fields": FIELDS,
        }

        items: List[CandidateItem] = []

        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.get(BASE_URL, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Semantic Scholar connector failed: %s", exc)
            return items

        for paper in data.get("data", [])[:max_results]:
            paper_id = paper.get("paperId")
            title = normalize_whitespace(paper.get("title") or "")
            if not paper_id or not title:
                continue

            abstract = normalize_whitespace(paper.get("abstract") or "")
            url = paper.get("url") or f"https://www.semanticscholar.org/paper/{paper_id}"

            # Prefer open-access PDF link when available.
            oa_pdf = paper.get("openAccessPdf")
            if isinstance(oa_pdf, dict) and oa_pdf.get("url"):
                url = oa_pdf["url"]

            pub_date = None
            pub_date_raw = paper.get("publicationDate")
            if pub_date_raw:
                try:
                    pub_date = datetime.fromisoformat(pub_date_raw)
                except ValueError:
                    pass

            authors_list = paper.get("authors") or []
            author_names = ", ".join(
                a.get("name", "") for a in authors_list[:5]
            )

            citation_count = int(paper.get("citationCount") or 0)

            items.append(
                CandidateItem(
                    source_id=self.source_id,
                    external_id=f"s2:{paper_id}",
                    url=url,
                    title=title,
                    snippet=abstract,
                    author=author_names or None,
                    published_at=pub_date,
                    fetched_at=now,
                    social_hn_points=citation_count,
                )
            )

        return items
