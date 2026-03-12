from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Protocol


@dataclass
class CandidateItem:
    source_id: str
    external_id: str
    url: str
    title: str
    snippet: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime | None = None
    language: str = "en"
    social_hn_points: int | None = None
    social_hn_comments: int | None = None
    social_reddit_upvotes: int | None = None
    social_github_stars: int | None = None


class Connector(Protocol):
    def fetch_candidates(self, now: datetime) -> List[CandidateItem]:
        ...
