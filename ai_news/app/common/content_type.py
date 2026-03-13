"""Derive article content_type from source kind and event type."""
from __future__ import annotations


def content_type_for(source_kind: str, event_type: str) -> str:
    if source_kind in ("github", "github_trending"):
        return "github"
    if source_kind == "arxiv" or event_type == "RESEARCH_PAPER":
        return "research"
    return "news"
