from __future__ import annotations

from urllib.parse import urlparse

from app.models import Source


COMMUNITY_PLATFORM_HOSTS: dict[str, set[str]] = {
    "hn": {"news.ycombinator.com", "ycombinator.com"},
    "reddit": {"reddit.com", "www.reddit.com", "old.reddit.com"},
    "twitter": {"twitter.com", "www.twitter.com", "x.com", "www.x.com"},
    "bluesky": {"bsky.app", "www.bsky.app"},
}

HOST_BRAND_MAP: dict[str, str] = {
    "github.com": "GitHub",
    "huggingface.co": "Hugging Face",
    "arxiv.org": "arXiv",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "stepsecurity.io": "StepSecurity",
    "openai.com": "OpenAI",
    "anthropic.com": "Anthropic",
    "blog.google": "Google",
    "google.com": "Google",
    "deepmind.google": "Google DeepMind",
    "meta.com": "Meta",
    "ai.meta.com": "Meta AI",
    "microsoft.com": "Microsoft",
    "nvidia.com": "NVIDIA",
}


def _normalized_host(url: str | None) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _display_name_for_host(host: str) -> str:
    if not host:
        return ""
    if host in HOST_BRAND_MAP:
        return HOST_BRAND_MAP[host]

    parts = host.split(".")
    if len(parts) >= 2:
        label = parts[-2]
    else:
        label = parts[0]
    return label.replace("-", " ").title()


def build_grounding_source(*, source: Source, url: str | None) -> dict[str, str]:
    host = _normalized_host(url)
    discovery_source = source.name

    if source.kind in COMMUNITY_PLATFORM_HOSTS and host and host not in COMMUNITY_PLATFORM_HOSTS[source.kind]:
        publisher = _display_name_for_host(host)
        payload = {
            "title": publisher,
            "uri": url or "",
            "source": publisher,
            "discoverySource": discovery_source,
        }
        if publisher != discovery_source:
            payload["viaSource"] = discovery_source
        return payload

    return {
        "title": discovery_source,
        "uri": url or "",
        "source": discovery_source,
        "discoverySource": discovery_source,
    }
