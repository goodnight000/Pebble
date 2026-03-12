from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

import httpx

from app.common.text import normalize_whitespace
from app.common.time import utcnow
from app.config import get_settings
from app.ingestion.base import CandidateItem


class GitHubConnector:
    def __init__(self, source_id: str, query_terms: str | None = None):
        self.source_id = source_id
        # GitHub Search does not reliably support complex boolean expressions in the query
        # string, and overly-specific queries can return 0 results. Use a small set of
        # simple keyword queries and merge.
        self.query_terms = query_terms or "llm,agent,diffusion,transformer,machine learning"

    def fetch_candidates(self, now: datetime | None = None, since_days: int = 7) -> List[CandidateItem]:
        now = now or utcnow()
        since_date = (now - timedelta(days=since_days)).date().isoformat()
        url = "https://api.github.com/search/repositories"
        settings = get_settings()
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": settings.user_agent,
        }
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"

        # Keep requests small to avoid hitting unauthenticated search rate limits.
        terms = [t.strip() for t in (self.query_terms or "").split(",") if t.strip()]
        if not terms:
            terms = ["llm"]

        items: List[CandidateItem] = []
        seen_repo_ids: set[str] = set()
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            for term in terms:
                # Quote phrases; leave single tokens unquoted.
                q_term = f"\"{term}\"" if " " in term else term
                query = f"{q_term} pushed:>={since_date}"
                params = {"q": query, "sort": "stars", "order": "desc", "per_page": 20}
                response = client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
                for repo in data.get("items", []):
                    external_id = repo.get("id")
                    if not external_id:
                        continue
                    repo_id = str(external_id)
                    if repo_id in seen_repo_ids:
                        continue
                    seen_repo_ids.add(repo_id)

                    title = normalize_whitespace(repo.get("full_name", ""))
                    if not title:
                        continue
                    items.append(
                        CandidateItem(
                            source_id=self.source_id,
                            external_id=repo_id,
                            url=repo.get("html_url"),
                            title=title,
                            snippet=normalize_whitespace(repo.get("description") or ""),
                            author=repo.get("owner", {}).get("login"),
                            published_at=None,
                            fetched_at=now,
                            social_github_stars=repo.get("stargazers_count"),
                        )
                    )
                if len(items) >= 60:
                    break
        return items
