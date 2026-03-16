from __future__ import annotations

import asyncio
import threading
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import numpy as np
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from app.clustering.cluster import attach_or_create_cluster, bytes_to_vector, update_cluster_stats
from app.common.embeddings import embed_text, embed_texts
from app.common.hashing import canonical_hash
from app.common.time import utcnow
from app.common.url_filters import is_news_candidate_url
from app.config import get_settings, load_source_config
from app.db import session_scope
from app.features.compute import build_features
from app.features.topic_anchors import TOPIC_ANCHORS
from app.ingestion.arxiv import ArxivConnector
from app.ingestion.bluesky import BlueskyConnector
from app.ingestion.congress import CongressConnector
from app.ingestion.github import GitHubConnector
from app.ingestion.github_trending import GitHubTrendingConnector
from app.ingestion.hackernews import HackerNewsConnector
from app.ingestion.nvd import NVDConnector
from app.ingestion.hf_papers import HFPapersConnector
from app.ingestion.mastodon import MastodonConnector
from app.ingestion.reddit import RedditConnector
from app.ingestion.rss import RSSConnector
from app.ingestion.semantic_scholar import SemanticScholarConnector
from app.ingestion.sitemap import SitemapConnector
from app.ingestion.twitter import TwitterConnector
from app.ingestion.wayback import check_wayback
from app.llm.client import LLMClient
from app.models import Article, Cluster, ClusterMember, EntityCanonMap, RawItem, Source
from app.scraping.extract import extract_pub_date, extract_text, extract_text_lightweight
from app.scraping.fetch import fetch_html
from app.scoring.importance import GlobalScoreInputs, compute_global_score_v2
from app.scoring.llm_judge import compute_final_score
from app.scoring.signals import is_official_source, log_norm, research_rigor_score
from app.scoring.time_decay import compute_urgent, rank_score
from app.scoring.trust import estimate_independent_sources
from app.scoring.verification import (
    VerificationInputs,
    compute_verification,
    legacy_trust_components,
    legacy_trust_label_for_state,
)
from app.services.realtime_events import build_new_cluster_event, build_urgent_update_event, publish_realtime_event
from app.tasks.celery_app import celery_app


INGEST_RUN_LOCK = threading.Lock()


def _content_type_for(source_kind: str, event_type: str) -> str:
    from app.common.content_type import content_type_for
    return content_type_for(source_kind, event_type)


SAMPLE_ITEMS = [
    {
        "external_id": "sample-1",
        "title": "Open-source agent framework adds tool-use routing for enterprise workflows",
        "url": "https://example.com/sample/open-source-agent-framework",
        "snippet": "A lightweight agent framework released on GitHub introduces tool routing, safety guards, and eval templates for internal copilots.",
        "hours_ago": 3,
    },
    {
        "external_id": "sample-2",
        "title": "New multimodal benchmark compares frontier models on long-context reasoning",
        "url": "https://example.com/sample/multimodal-benchmark",
        "snippet": "Researchers publish a benchmark covering vision-language tasks with long prompts and multi-turn evaluation.",
        "hours_ago": 5,
    },
    {
        "external_id": "sample-3",
        "title": "Startup raises $25M Series A to scale efficient inference chips",
        "url": "https://example.com/sample/inference-chips",
        "snippet": "The round targets deployment of low-power inference accelerators for edge devices and data centers.",
        "hours_ago": 7,
    },
    {
        "external_id": "sample-4",
        "title": "Policy update: draft safety guidance for foundation model evaluations",
        "url": "https://example.com/sample/policy-guidance",
        "snippet": "Regulators publish an early framework outlining red-team requirements and model risk reporting.",
        "hours_ago": 10,
    },
    {
        "external_id": "sample-5",
        "title": "Research team releases dataset for robust speech recognition in noisy environments",
        "url": "https://example.com/sample/speech-dataset",
        "snippet": "A new open dataset of 500 hours of noisy speech aims to improve audio robustness and evaluation.",
        "hours_ago": 12,
    },
]

PAYWALLED_DOMAINS = (
    "bloomberg.com",
    "ft.com",
    "economist.com",
    "theinformation.com",
)

COMMUNITY_SOURCE_KINDS = {"hn", "reddit", "twitter", "mastodon", "bluesky"}
SOCIAL_SIGNAL_FIELDS = (
    "social_hn_points",
    "social_hn_comments",
    "social_reddit_upvotes",
    "social_github_stars",
)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "igshid", "ref", "source", "mc_cid", "mc_eid"}
RAW_ITEM_COLUMNS = {
    "source_id",
    "external_id",
    "url",
    "title",
    "snippet",
    "author",
    "published_at",
    "fetched_at",
    "language",
    "social_hn_points",
    "social_hn_comments",
    "social_reddit_upvotes",
    "social_github_stars",
    "canonical_hash",
}


def _normalize_article_url(url: str | None) -> str:
    """Normalize URLs for cross-source matching."""
    if not url:
        return ""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    kept_query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        key_l = key.lower()
        if key_l.startswith("utm_") or key_l in TRACKING_QUERY_KEYS:
            continue
        kept_query.append((key, value))
    query = urlencode(sorted(kept_query))
    return urlunparse(("", host, path, "", query, ""))


def _merge_social_signals(raw: RawItem, candidate: dict) -> bool:
    """Merge social counters using max() to avoid double counting over repeated polls."""
    changed = False
    for field in SOCIAL_SIGNAL_FIELDS:
        incoming = candidate.get(field)
        if incoming is None:
            continue
        try:
            incoming_int = int(incoming)
        except (TypeError, ValueError):
            continue
        current = int(getattr(raw, field) or 0)
        if incoming_int > current:
            setattr(raw, field, incoming_int)
            changed = True
    return changed


def _find_existing_raw_by_url(session, url: str) -> RawItem | None:
    exact = session.query(RawItem).filter(RawItem.url == url).first()
    if exact:
        return exact
    normalized = _normalize_article_url(url)
    if not normalized:
        return None
    domain = urlparse(url).hostname or ""
    if domain.startswith("www."):
        domain = domain[4:]
    if not domain:
        return None
    rows = (
        session.query(RawItem)
        .filter(RawItem.url.contains(domain))
        .order_by(func.coalesce(RawItem.published_at, RawItem.fetched_at).desc())
        .limit(200)
        .all()
    )
    for raw in rows:
        if _normalize_article_url(raw.url) == normalized:
            return raw
    return None


def _find_existing_article_by_url(session, url: str) -> Article | None:
    exact = session.query(Article).filter(Article.final_url == url).first()
    if exact:
        return exact
    normalized = _normalize_article_url(url)
    if not normalized:
        return None
    domain = urlparse(url).hostname or ""
    if domain.startswith("www."):
        domain = domain[4:]
    if not domain:
        return None
    rows = (
        session.query(Article, RawItem)
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .filter(or_(Article.final_url.contains(domain), RawItem.url.contains(domain)))
        .order_by(func.coalesce(RawItem.published_at, RawItem.fetched_at).desc())
        .limit(200)
        .all()
    )
    for article, raw in rows:
        if _normalize_article_url(article.final_url) == normalized:
            return article
        if _normalize_article_url(raw.url) == normalized:
            return article
    return None


def _seed_sample_if_empty() -> None:
    settings = get_settings()
    if settings.app_env.lower() == "prod":
        return
    with session_scope() as session:
        existing_articles = session.query(Article.id).count()
        if existing_articles > 0:
            non_sample = (
                session.query(Article.id)
                .join(RawItem, Article.raw_item_id == RawItem.id)
                .join(Source, RawItem.source_id == Source.id)
                .filter(Source.name != "Local Sample Feed")
                .count()
            )
            if non_sample == 0:
                rows = (
                    session.query(Article)
                    .join(RawItem, Article.raw_item_id == RawItem.id)
                    .join(Source, RawItem.source_id == Source.id)
                    .filter(Source.name == "Local Sample Feed")
                    .all()
                )
                for article in rows:
                    if article.global_score < 65:
                        article.global_score = 72.0
            return
        source = session.query(Source).filter(Source.name == "Local Sample Feed").first()
        if not source:
            source = Source(
                name="Local Sample Feed",
                kind="custom",
                base_url="https://example.com",
                authority=0.4,
                always_scrape=True,
                priority_poll=False,
                enabled=True,
                rate_limit_rps=0.5,
            )
            session.add(source)
            session.flush()

        now = utcnow()
        for item in SAMPLE_ITEMS:
            published_at = now - timedelta(hours=item["hours_ago"])
            raw = RawItem(
                source_id=source.id,
                external_id=item["external_id"],
                url=item["url"],
                title=item["title"],
                snippet=item["snippet"],
                author=None,
                published_at=published_at,
                fetched_at=now,
                language="en",
                canonical_hash=canonical_hash(item["title"], item["url"]),
                pre_score=55.0,
                scrape_decision="fetch_full",
                scrape_reason="local_sample_seed",
            )
            session.add(raw)
            session.flush()

            text = item["snippet"]
            event_type, topics, entities, funding_amount = build_features(
                raw.title,
                text,
                source_kind=source.kind,
                url=raw.url,
                source_name=source.name,
            )
            embedding = embed_text(f"{raw.title}\n{text}")
            et_str = event_type.value if hasattr(event_type, "value") else str(event_type)
            article = Article(
                raw_item_id=raw.id,
                final_url=raw.url,
                html=None,
                text=text,
                extraction_quality=0.2,
                embedding=embedding.astype("float32").tobytes(),
                event_type=et_str,
                content_type=_content_type_for(source.kind, et_str),
                topics=topics,
                entities=entities,
                funding_amount_usd=funding_amount,
                global_score=0.0,
                urgent=False,
                summary=text,
            )
            session.add(article)
            session.flush()
            _update_article_scores(session, article, raw, source)
            if article.global_score < 65:
                article.global_score = 72.0


ANCHOR_TEXTS = [phrase for phrases in TOPIC_ANCHORS.values() for phrase in phrases]
ANCHOR_EMBS = embed_texts(ANCHOR_TEXTS)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _ai_relevance(title: str) -> float:
    title_emb = embed_text(title)
    sim_max = float((ANCHOR_EMBS @ title_emb).max()) if len(ANCHOR_EMBS) else 0.0
    return _clamp01((sim_max - 0.15) / 0.35)


def _keyword_score(title: str) -> float:
    config = load_source_config()
    keywords = config.get("keywords", {})
    score = 0.0
    lowered = title.lower()
    for phrase, weight in keywords.items():
        if phrase in lowered:
            score += float(weight)
    return _clamp01(score)


def _social_score(raw: RawItem) -> float:
    hn = log_norm(raw.social_hn_points or 0, 500)
    reddit = log_norm(raw.social_reddit_upvotes or 0, 5000)
    gh = log_norm(raw.social_github_stars or 0, 5000)
    return _clamp01(max(hn, reddit, gh))


def _compute_pre_score(raw: RawItem, source: Source) -> float:
    ai_rel = _ai_relevance(raw.title)
    kw = _keyword_score(raw.title)
    social = _social_score(raw)
    return 100 * _clamp01(0.35 * source.authority + 0.30 * ai_rel + 0.20 * kw + 0.15 * social)


def _scrape_decision(raw: RawItem, source: Source) -> tuple[str, str]:
    config = load_source_config()
    thresholds = config.get("scrape_thresholds", {})
    pre_fetch = thresholds.get("pre_fetch_full", 40)
    pre_priority = thresholds.get("pre_fetch_full_priority", 70)

    ai_rel = _ai_relevance(raw.title)
    title_lower = raw.title.lower()

    if source.always_scrape:
        return "fetch_full", "always_scrape"
    if ai_rel >= 0.75 and any(token in title_lower for token in ["release", "launch", "raise", "acquire", "announc"]):
        return "fetch_full", "ai_relevance_force_fetch"
    if raw.pre_score is not None and raw.pre_score >= pre_priority:
        return "fetch_full_priority", "pre_score>=70"
    if raw.pre_score is not None and raw.pre_score >= pre_fetch:
        return "fetch_full", "pre_score>=40"
    pre_watch = thresholds.get("pre_watch", 30)
    if raw.pre_score is not None and raw.pre_score >= pre_watch:
        if source.authority >= 0.70 or ai_rel >= 0.60:
            return "fetch_watch", "watch_band"
    return "skip", "below_threshold_skip"


def _upsert_raw_item(session, candidate: dict, seen_keys: set, seen_hashes: set) -> None:
    if not is_news_candidate_url(candidate.get("url")):
        return

    source_kind = candidate.get("source_kind")
    # Strict recency discipline for sitemap sources: no publication time, no ingest.
    if source_kind == "sitemap" and candidate.get("published_at") is None:
        return

    if source_kind in COMMUNITY_SOURCE_KINDS:
        article_match = _find_existing_article_by_url(session, candidate.get("url", ""))
        existing_raw = None
        if article_match:
            existing_raw = session.query(RawItem).filter(RawItem.id == article_match.raw_item_id).first()
        if existing_raw is None:
            existing_raw = _find_existing_raw_by_url(session, candidate.get("url", ""))
        if existing_raw:
            changed = _merge_social_signals(existing_raw, candidate)
            if changed and existing_raw.article:
                source = session.query(Source).filter(Source.id == existing_raw.source_id).first()
                if source:
                    _refresh_existing_article_scores(session, existing_raw.article, existing_raw, source)
            return

    key = (str(candidate["source_id"]), candidate["external_id"])
    if key in seen_keys:
        return
    seen_keys.add(key)

    canonical = candidate["canonical_hash"]
    if canonical in seen_hashes:
        return
    seen_hashes.add(canonical)

    # Skip if canonical hash already exists in DB (global dedup)
    if session.query(RawItem.id).filter(RawItem.canonical_hash == canonical).first():
        return

    existing = (
        session.query(RawItem)
        .filter(RawItem.source_id == candidate["source_id"], RawItem.external_id == candidate["external_id"])
        .first()
    )
    if existing:
        for key, value in candidate.items():
            if key not in RAW_ITEM_COLUMNS:
                continue
            if key == "id":
                continue
            setattr(existing, key, value)
        return
    payload = {k: v for k, v in candidate.items() if k in RAW_ITEM_COLUMNS}
    session.add(RawItem(**payload))


def _source_yaml_flags() -> dict[str, dict]:
    """Build a lookup from source name to YAML-only flags (browser_ua, lastmod_optional)."""
    config = load_source_config()
    return {
        src["name"]: src
        for src in config.get("sources", [])
        if src.get("name")
    }


_yaml_cache: dict[str, dict] | None = None


def _get_yaml_flags(source_name: str) -> dict:
    global _yaml_cache
    if _yaml_cache is None:
        _yaml_cache = _source_yaml_flags()
    return _yaml_cache.get(source_name, {})


def _connector_for_source(source: Source):
    flags = _get_yaml_flags(source.name)
    browser_ua = flags.get("browser_ua", False)

    if source.kind == "rss":
        return RSSConnector(str(source.id), source.feed_url, browser_ua=browser_ua)
    if source.kind == "arxiv":
        return ArxivConnector(str(source.id), source.base_url)
    if source.kind == "github":
        return GitHubConnector(str(source.id))
    if source.kind == "github_trending":
        return GitHubTrendingConnector(str(source.id))
    if source.kind == "hn":
        return HackerNewsConnector(str(source.id))
    if source.kind == "reddit":
        return RedditConnector(str(source.id))
    if source.kind == "sitemap":
        sitemap_url = source.feed_url
        path_filter = source.base_url
        if not sitemap_url:
            return None
        lastmod_optional = flags.get("lastmod_optional", False)
        return SitemapConnector(
            str(source.id),
            sitemap_url,
            path_filter=path_filter,
            browser_ua=browser_ua,
            lastmod_optional=lastmod_optional,
        )
    if source.kind == "congress":
        settings = get_settings()
        api_key = getattr(settings, "congress_api_key", None) or ""
        return CongressConnector(str(source.id), api_key=api_key)
    if source.kind == "twitter":
        return TwitterConnector(str(source.id))
    if source.kind == "mastodon":
        return MastodonConnector(str(source.id))
    if source.kind == "bluesky":
        return BlueskyConnector(str(source.id))
    if source.kind == "semantic_scholar":
        return SemanticScholarConnector(str(source.id))
    if source.kind == "hf_papers":
        return HFPapersConnector(str(source.id))
    if source.kind == "nvd":
        return NVDConnector(str(source.id))
    return None


def _max_similarity_recent(session, embedding: np.ndarray, lookback_days: int, exclude_cluster_id: str | None) -> float:
    cutoff = utcnow() - timedelta(days=lookback_days)
    query = session.query(Cluster).filter(Cluster.last_seen_at >= cutoff)
    if exclude_cluster_id:
        query = query.filter(Cluster.id != exclude_cluster_id)
    clusters = query.all()
    if not clusters:
        return 0.0
    sims = []
    for cluster in clusters:
        if not cluster.centroid_embedding:
            continue
        vec = bytes_to_vector(cluster.centroid_embedding)
        if vec.size == 0:
            continue
        sims.append(float(vec @ embedding))
    return max(sims) if sims else 0.0


async def _scrape_and_process(raw: RawItem, source: Source) -> Article | None:
    html = None
    final_url = raw.url
    text = None
    quality = 0.0

    # Watch-band items: lightweight extraction only
    is_watch = raw.scrape_decision == "fetch_watch"

    try:
        html, final_url = await fetch_html(raw.url, rate_limit_rps=source.rate_limit_rps)
        if is_watch:
            text, quality = extract_text_lightweight(html, final_url)
        else:
            text, quality = await extract_text(html, final_url)
    except Exception:
        # Some domains (e.g. behind bot challenges) may block full-page scraping.
        # Fall back to the feed/snippet so we still surface the item in the UI.
        html = None
        final_url = raw.url
        text = None
        quality = 0.0

    # Opportunistic Wayback fallback for likely paywalled domains.
    if not text and (raw.pre_score or 0) >= 70:
        url_lower = (raw.url or "").lower()
        if any(domain in url_lower for domain in PAYWALLED_DOMAINS):
            archive_url = await check_wayback(raw.url)
            if archive_url:
                try:
                    html, final_url = await fetch_html(archive_url, rate_limit_rps=source.rate_limit_rps)
                    text, quality = await extract_text(html, final_url)
                except Exception:
                    pass

    if not text:
        if raw.snippet:
            text = raw.snippet
            quality = max(quality, 0.15)
        else:
            return None

    # ── Correct published_at for sitemap sources using real pub date ──
    if html and source.kind == "sitemap":
        real_pub = extract_pub_date(html, final_url or raw.url)
        if real_pub:
            # Strip tzinfo for comparison with naive-UTC DB timestamps
            real_pub_naive = real_pub.replace(tzinfo=None)
            raw_pub_naive = (
                raw.published_at.replace(tzinfo=None)
                if raw.published_at and raw.published_at.tzinfo
                else raw.published_at
            )
            # If real pub date is >24 h older than what the sitemap reported,
            # the sitemap lastmod was just an edit — use the true date.
            if raw_pub_naive and (raw_pub_naive - real_pub_naive).total_seconds() > 86400:
                print(
                    f"[pipeline] sitemap date correction: {raw.url} "
                    f"lastmod={raw_pub_naive} real_pub={real_pub_naive}"
                )
                raw.published_at = real_pub_naive
                # If corrected date is outside the lookback window, skip it.
                settings = get_settings()
                cutoff = utcnow().replace(tzinfo=None) - timedelta(
                    hours=settings.ingest_lookback_hours,
                )
                if real_pub_naive < cutoff:
                    print(
                        f"[pipeline] skipping stale sitemap article: {raw.url} "
                        f"(real pub {real_pub_naive} < cutoff {cutoff})"
                    )
                    return None

    event_type, topics, entities, funding_amount = build_features(
        raw.title,
        text,
        source_kind=source.kind,
        url=final_url or raw.url,
        source_name=source.name,
    )
    embedding_text = f"{raw.title}\n{(text[:800] if text else raw.snippet or '')}"
    embedding = embed_text(embedding_text)

    et_str = event_type.value if hasattr(event_type, "value") else str(event_type)
    article = Article(
        raw_item_id=raw.id,
        final_url=final_url,
        html=html if raw.scrape_decision == "fetch_full_priority" else None,
        text=text,
        extraction_quality=quality,
        embedding=embedding.astype("float32").tobytes(),
        event_type=et_str,
        content_type=_content_type_for(source.kind, et_str),
        topics=topics,
        entities=entities,
        funding_amount_usd=funding_amount,
        global_score=0.0,
        urgent=False,
        summary=None,
    )
    return article


def _score_article(
    session,
    article: Article,
    raw: RawItem,
    source: Source,
    *,
    attach_cluster: bool,
    allow_llm: bool = True,
) -> Article:
    embedding = bytes_to_vector(article.embedding)
    cluster_id = None
    if attach_cluster:
        cluster_id, _sim = attach_or_create_cluster(session, article, embedding)
    else:
        member = session.query(ClusterMember).filter(ClusterMember.article_id == article.id).first()
        if member:
            cluster_id = member.cluster_id
        else:
            cluster_id, _sim = attach_or_create_cluster(session, article, embedding)

    cluster = session.query(Cluster).filter(Cluster.id == cluster_id).first()
    novelty_sim = _max_similarity_recent(session, embedding, lookback_days=90, exclude_cluster_id=cluster_id)

    # Gather cluster articles for trust/independent source analysis
    cluster_articles = []
    source_names = []
    if cluster:
        rows = (
            session.query(Article, Source.name)
            .join(ClusterMember, ClusterMember.article_id == Article.id)
            .join(RawItem, Article.raw_item_id == RawItem.id)
            .join(Source, RawItem.source_id == Source.id)
            .filter(ClusterMember.cluster_id == cluster_id)
            .all()
        )
        cluster_articles = [art for art, _sname in rows]
        source_names = [sname for _art, sname in rows]

    independent_count = estimate_independent_sources(cluster_articles) if cluster_articles else 1
    articles_in_cluster = cluster.coverage_count if cluster else 1
    now = utcnow().replace(tzinfo=None)  # naive UTC to match DB timestamps
    ts = raw.published_at or raw.fetched_at
    if ts and ts.tzinfo is not None:
        ts = ts.replace(tzinfo=None)
    age_hours = max(0.1, (now - ts).total_seconds() / 3600) if ts else 1.0
    cluster_age_hours = 1.0
    if cluster and cluster.first_seen_at:
        fsa = cluster.first_seen_at
        if fsa.tzinfo is not None:
            fsa = fsa.replace(tzinfo=None)
        cluster_age_hours = max(0.1, (now - fsa).total_seconds() / 3600)

    # Primary entity: highest-weighted entity
    primary_entity = None
    if article.entities:
        primary_entity = max(article.entities, key=article.entities.get)

    # ── 1. Compute global score v2 (11 signals) ─────────────────────
    inputs = GlobalScoreInputs(
        source_authority=source.authority,
        event_type=article.event_type,
        entities=article.entities,
        independent_sources=independent_count,
        raw_item=raw,
        age_hours=age_hours,
        articles_in_cluster=articles_in_cluster,
        cluster_age_hours=cluster_age_hours,
        novelty_sim=novelty_sim,
        recent_max_score=cluster.max_global_score if cluster else 0.0,
        primary_entity=primary_entity,
        session=session,
        source_kind=source.kind,
        text=article.text,
        funding_amount_usd=article.funding_amount_usd,
        final_url=article.final_url,
        source_names=source_names,
        content_type=article.content_type,
        extraction_quality=article.extraction_quality if article.extraction_quality is not None else 1.0,
    )
    score, signal_breakdown = compute_global_score_v2(inputs)
    article.global_score = score

    # Store individual signal values
    article.entity_prominence = signal_breakdown.get("entity_prominence")
    article.social_velocity = signal_breakdown.get("social_velocity")
    article.cluster_velocity = signal_breakdown.get("cluster_velocity")
    article.event_rarity = signal_breakdown.get("event_rarity")
    article.independent_sources = independent_count

    # ── 2. Compute verification and compatibility trust fields ──────
    verification_inputs = VerificationInputs(
        cluster_articles=cluster_articles,
        source_authority=source.authority,
        text=article.text,
        url=article.final_url,
        primary_entity=primary_entity,
        independent_sources=independent_count,
        event_type=article.event_type,
        source_kind=source.kind,
        source_name=source.name,
        created_at=article.created_at,
    )
    verification = compute_verification(verification_inputs)
    trust_label = legacy_trust_label_for_state(
        verification.verification_state,
        verification.verification_confidence,
    )
    trust_components = legacy_trust_components(verification, article.text)
    article.verification_mode = verification.verification_mode
    article.verification_state = verification.verification_state
    article.freshness_state = verification.freshness_state
    article.verification_confidence = verification.verification_confidence
    article.verification_signals = verification.verification_signals
    article.update_status = verification.update_status
    article.canonical_evidence_url = verification.canonical_evidence_url
    article.trust_score = verification.verification_confidence
    article.trust_label = trust_label
    article.trust_components = trust_components
    article.hedging_ratio = trust_components.get("hedging_ratio")
    article.attribution_ratio = trust_components.get("attribution_ratio")
    article.specificity_score = trust_components.get("specificity_score")
    article.has_primary_document = bool(trust_components.get("primary_document", 0) > 0)
    article.confirmation_level = trust_components.get("confirmation_level")

    # Update cluster trust fields
    if cluster:
        cluster.cluster_velocity = signal_breakdown.get("cluster_velocity")
        cluster.independent_sources_count = independent_count
        cluster.has_official_confirmation = verification.verification_state == "official_statement"
        cluster.cluster_trust_score = verification.verification_confidence
        cluster.cluster_trust_label = trust_label
        cluster.cluster_verification_state = verification.verification_state
        cluster.cluster_freshness_state = verification.freshness_state
        cluster.cluster_verification_confidence = verification.verification_confidence
        cluster.cluster_verification_signals = verification.verification_signals

    # ── 3. LLM judge (for articles scoring >= 40) ────────────────────
    llm_score_val = None
    if allow_llm and article.global_score >= 40:
        llm = LLMClient()
        result = llm.judge_significance(
            raw.title,
            source.name,
            article.event_type,
            (article.text or "")[:800],
        )
        if result:
            llm_score_val, llm_reasoning = result
            article.llm_score = llm_score_val
            article.llm_reasoning = llm_reasoning

    # ── 4. Compute final score (blend rule + LLM) ────────────────────
    article.final_score = compute_final_score(
        article.global_score, llm_score_val,
        confirmation_level=article.confirmation_level,
        trust_label=article.trust_label,
        verification_state=article.verification_state,
        verification_confidence=article.verification_confidence,
        update_status=article.update_status,
    )

    # ── 5. Determine urgent ──────────────────────────────────────────
    article.urgent = compute_urgent(
        article.final_score,
        age_hours,
        independent_count,
        is_official_source(article.final_url),
        article.trust_label,
        verification_state=article.verification_state,
        verification_confidence=article.verification_confidence,
    )

    if cluster_id:
        update_cluster_stats(session, cluster_id)
    return article


def _update_article_scores(session, article: Article, raw: RawItem, source: Source) -> Article:
    return _score_article(session, article, raw, source, attach_cluster=True)


def _refresh_existing_article_scores(
    session,
    article: Article,
    raw: RawItem,
    source: Source,
    *,
    allow_llm: bool = True,
) -> Article:
    return _score_article(session, article, raw, source, attach_cluster=False, allow_llm=allow_llm)


@celery_app.task(name="app.tasks.pipeline.run_priority_poll")
def run_priority_poll():
    if not INGEST_RUN_LOCK.acquire(blocking=False):
        print("[pipeline] skipping priority poll; another ingest run is active")
        return
    try:
        _run_poll(priority_only=True)
    finally:
        INGEST_RUN_LOCK.release()


@celery_app.task(name="app.tasks.pipeline.run_normal_poll")
def run_normal_poll():
    if not INGEST_RUN_LOCK.acquire(blocking=False):
        print("[pipeline] skipping normal poll; another ingest run is active")
        return
    try:
        _run_poll(priority_only=False)
    finally:
        INGEST_RUN_LOCK.release()


@celery_app.task(name="app.tasks.pipeline.run_arxiv_poll")
def run_arxiv_poll():
    if not INGEST_RUN_LOCK.acquire(blocking=False):
        print("[pipeline] skipping arxiv poll; another ingest run is active")
        return
    try:
        _run_special(kind="arxiv", window_hours=3)
    finally:
        INGEST_RUN_LOCK.release()


@celery_app.task(name="app.tasks.pipeline.run_github_poll")
def run_github_poll():
    if not INGEST_RUN_LOCK.acquire(blocking=False):
        print("[pipeline] skipping github poll; another ingest run is active")
        return
    try:
        _run_special(kind="github", window_hours=24)
    finally:
        INGEST_RUN_LOCK.release()


@celery_app.task(name="app.tasks.pipeline.run_sitemap_poll")
def run_sitemap_poll():
    if not INGEST_RUN_LOCK.acquire(blocking=False):
        print("[pipeline] skipping sitemap poll; another ingest run is active")
        return
    try:
        _run_special(kind="sitemap", window_hours=24)
    finally:
        INGEST_RUN_LOCK.release()


@celery_app.task(name="app.tasks.pipeline.run_gov_api_poll")
def run_gov_api_poll():
    if not INGEST_RUN_LOCK.acquire(blocking=False):
        print("[pipeline] skipping gov poll; another ingest run is active")
        return
    try:
        _run_special(kind="congress", window_hours=24)
    finally:
        INGEST_RUN_LOCK.release()


@celery_app.task(name="app.tasks.pipeline.run_twitter_poll")
def run_twitter_poll():
    if not INGEST_RUN_LOCK.acquire(blocking=False):
        print("[pipeline] skipping twitter poll; another ingest run is active")
        return
    try:
        _run_special(kind="twitter", window_hours=24)
    finally:
        INGEST_RUN_LOCK.release()


@celery_app.task(name="app.tasks.pipeline.run_social_poll")
def run_social_poll():
    if not INGEST_RUN_LOCK.acquire(blocking=False):
        print("[pipeline] skipping social poll; another ingest run is active")
        return
    try:
        _run_special(kind="mastodon", window_hours=24)
        _run_special(kind="bluesky", window_hours=24)
    finally:
        INGEST_RUN_LOCK.release()


@celery_app.task(name="app.tasks.pipeline.rebuild_faiss_index")
def rebuild_faiss_index():
    from app.clustering.cluster import rebuild_index

    with session_scope() as session:
        rebuild_index(session, lookback_days=7)


def rescore_recent_articles(window_hours: int = 72) -> None:
    cutoff = utcnow() - timedelta(hours=window_hours)
    with session_scope() as session:
        rows = (
            session.query(Article, RawItem, Source)
            .join(RawItem, Article.raw_item_id == RawItem.id)
            .join(Source, RawItem.source_id == Source.id)
            .filter(func.coalesce(RawItem.fetched_at, Article.created_at) >= cutoff)
            .all()
        )
        for article, raw, source in rows:
            event_type, topics, entities, funding_amount = build_features(
                raw.title,
                article.text or raw.snippet or "",
                source_kind=source.kind,
                url=article.final_url or raw.url,
                source_name=source.name,
            )
            et_str = event_type.value if hasattr(event_type, "value") else str(event_type)
            article.event_type = et_str
            article.content_type = _content_type_for(source.kind, et_str)
            article.topics = topics
            article.entities = entities
            article.funding_amount_usd = funding_amount
            _refresh_existing_article_scores(session, article, raw, source)


def run_refresh():
    if not INGEST_RUN_LOCK.acquire(blocking=False):
        print("[pipeline] skipping refresh; another ingest run is active")
        return
    try:
        _run_poll(priority_only=True)
        _run_poll(priority_only=False)
        _run_special(kind="arxiv", window_hours=24)
        _run_special(kind="github", window_hours=24)
        _run_special(kind="sitemap", window_hours=24)
        _run_special(kind="congress", window_hours=24)
        _run_special(kind="twitter", window_hours=24)
        _run_special(kind="mastodon", window_hours=24)
        _run_special(kind="bluesky", window_hours=24)
        rescore_recent_articles(window_hours=72)
        _seed_sample_if_empty()
    finally:
        INGEST_RUN_LOCK.release()


def _process_scrape_targets(raw_ids: list[str]) -> None:
    # Scrape OUTSIDE the DB transaction to avoid holding the SQLite write lock
    # during slow network I/O.
    for raw_id in raw_ids:
        try:
            # 3a: Read raw item data and detach from session (short transaction)
            with session_scope() as session:
                raw = session.query(RawItem).filter(RawItem.id == raw_id).first()
                if not raw:
                    continue
                if session.query(Article.id).filter(Article.raw_item_id == raw.id).first():
                    continue
                source = session.query(Source).filter(Source.id == raw.source_id).first()
                if source is None:
                    continue
                # Detach objects so they can be used after session closes
                session.expunge(raw)
                session.expunge(source)

            # 3b: Scrape content — NO DB transaction held during network I/O
            try:
                article = asyncio.run(_scrape_and_process(raw, source))
            except Exception as exc:
                print(f"[pipeline] scrape failed: {raw.url} -> {exc}")
                continue
            if not article:
                continue

            # 3c: Save article + score (short transaction — DB writes only)
            pending_realtime_events: list[tuple[str, str, dict]] = []
            with session_scope() as session:
                # Re-check no duplicate was created while we were scraping
                if session.query(Article.id).filter(Article.raw_item_id == raw.id).first():
                    continue
                # Merge detached raw/source back into this session for scoring
                raw = session.merge(raw)
                source = session.merge(source)
                session.add(article)
                try:
                    session.flush()
                except IntegrityError as exc:
                    session.rollback()
                    if "articles.raw_item_id" in str(exc):
                        continue
                    raise
                _update_article_scores(session, article, raw, source)

                llm = LLMClient()
                reclassified = False
                if article.global_score >= 60 or raw.scrape_decision == "fetch_full_priority":
                    max_topic = max(article.topics.values()) if article.topics else 0.0
                    if article.event_type == "OTHER" or max_topic < 0.35:
                        data = llm.classify_event_and_topics(raw.title, article.text)
                        if data.get("event_type"):
                            article.event_type = data.get("event_type")
                            article.content_type = _content_type_for(source.kind, article.event_type)
                            reclassified = True
                        if data.get("topics"):
                            article.topics = data.get("topics")
                            reclassified = True
                # Rescore if LLM changed event_type or topics, since
                # global_score was computed with the stale values.
                if reclassified:
                    _refresh_existing_article_scores(session, article, raw, source)
                if article.global_score >= 70 and article.summary is None:
                    summary = llm.summarize(raw.title, article.text)
                    if summary:
                        article.summary = summary
                cluster = (
                    session.query(Cluster)
                    .join(ClusterMember, ClusterMember.cluster_id == Cluster.id)
                    .filter(ClusterMember.article_id == article.id)
                    .first()
                )
                if article.urgent:
                    pending_realtime_events.append(
                        (
                            "urgent",
                            "urgent_update",
                            build_urgent_update_event(
                                article_id=str(article.id),
                                title=raw.title,
                                source=source.name,
                                url=article.final_url,
                                final_score=article.final_score or article.global_score,
                            ),
                        )
                    )
                if cluster and cluster.coverage_count == 1:
                    pending_realtime_events.append(
                        (
                            "clusters",
                            "new_cluster",
                            build_new_cluster_event(
                                cluster_id=str(cluster.id),
                                headline=cluster.headline,
                                top_article_id=str(cluster.top_article_id) if cluster.top_article_id else None,
                                coverage_count=cluster.coverage_count,
                            ),
                        )
                    )
            for channel_key, event_name, payload in pending_realtime_events:
                publish_realtime_event(channel_key, event_name, payload)
        except Exception as exc:
            print(f"[pipeline] article processing failed for raw_id={raw_id}: {exc}")


def _run_poll(priority_only: bool):
    # ── Phase 1a: Read sources (short read transaction) ──
    with session_scope() as session:
        sources = session.query(Source).filter(Source.enabled.is_(True)).all()
        if priority_only:
            sources = [s for s in sources if s.priority_poll]
        else:
            sources = [s for s in sources if not s.priority_poll]
        # Detach sources so we can use them outside the session
        for s in sources:
            session.expunge(s)

    # ── Phase 1b: Fetch candidates from all sources (NO DB transaction) ──
    now = utcnow()
    all_candidates = []  # list of dicts
    for source in sources:
        connector = _connector_for_source(source)
        if not connector:
            continue
        try:
            candidates = connector.fetch_candidates(now)
        except Exception as exc:
            print(f"[pipeline] source fetch failed: {source.name} ({source.kind}) -> {exc}")
            continue
        for item in candidates:
            all_candidates.append({
                "source_id": source.id,
                "external_id": item.external_id,
                "url": item.url,
                "title": item.title,
                "snippet": item.snippet,
                "author": item.author,
                "published_at": item.published_at,
                "fetched_at": item.fetched_at or now,
                "language": item.language,
                "social_hn_points": item.social_hn_points,
                "social_hn_comments": item.social_hn_comments,
                "social_reddit_upvotes": item.social_reddit_upvotes,
                "social_github_stars": item.social_github_stars,
                "canonical_hash": canonical_hash(item.title, item.url),
                "source_kind": source.kind,
            })

    # ── Phase 1c: Write candidates + pre-score (short write transaction) ──
    with session_scope() as session:
        seen_keys: set = set()
        seen_hashes: set = set()
        for candidate in all_candidates:
            _upsert_raw_item(session, candidate, seen_keys, seen_hashes)

        raw_items = session.query(RawItem).filter(RawItem.pre_score.is_(None)).all()
        for raw in raw_items:
            source = session.query(Source).filter(Source.id == raw.source_id).first()
            if source is None:
                continue
            raw.pre_score = _compute_pre_score(raw, source)
            decision, reason = _scrape_decision(raw, source)
            raw.scrape_decision = decision
            raw.scrape_reason = reason

        session.flush()

    # ── Phase 2: Identify scrape targets (short read) ──
    settings = get_settings()
    with session_scope() as session:
        to_scrape_ids = [
            row[0]
            for row in session.query(RawItem.id)
            .filter(RawItem.scrape_decision.in_(["fetch_full", "fetch_full_priority"]))
            .outerjoin(Article, Article.raw_item_id == RawItem.id)
            .filter(Article.id.is_(None))
            .order_by(func.coalesce(RawItem.published_at, RawItem.fetched_at).desc(), RawItem.pre_score.desc().nullslast())
            .limit(settings.max_scrape_per_run)
            .all()
        ]

    # ── Phase 2b: Watch band targets (separate quota) ──
    with session_scope() as session:
        watch_ids = [
            row[0]
            for row in session.query(RawItem.id)
            .filter(RawItem.scrape_decision == "fetch_watch")
            .outerjoin(Article, Article.raw_item_id == RawItem.id)
            .filter(Article.id.is_(None))
            .order_by(RawItem.pre_score.desc().nullslast())
            .limit(settings.max_watch_per_run)
            .all()
        ]

    # ── Phase 3: Scrape + score each article ──
    _process_scrape_targets(to_scrape_ids)
    if watch_ids:
        _process_scrape_targets(watch_ids)


def _run_special(kind: str, window_hours: int):
    # ── Phase 1a: Read sources (short read transaction) ──
    with session_scope() as session:
        sources = session.query(Source).filter(Source.enabled.is_(True), Source.kind == kind).all()
        source_ids = [s.id for s in sources]
        for s in sources:
            session.expunge(s)

    if not sources:
        return

    # ── Phase 1b: Fetch candidates for selected sources (NO DB transaction) ──
    now = utcnow()
    all_candidates = []
    for source in sources:
        connector = _connector_for_source(source)
        if not connector:
            continue
        try:
            if kind == "arxiv":
                candidates = connector.fetch_candidates(now, window_hours=window_hours)
            else:
                candidates = connector.fetch_candidates(now)
        except Exception as exc:
            print(f"[pipeline] source fetch failed: {source.name} ({source.kind}) -> {exc}")
            continue
        for item in candidates:
            all_candidates.append({
                "source_id": source.id,
                "external_id": item.external_id,
                "url": item.url,
                "title": item.title,
                "snippet": item.snippet,
                "author": item.author,
                "published_at": item.published_at,
                "fetched_at": item.fetched_at or now,
                "language": item.language,
                "social_hn_points": item.social_hn_points,
                "social_hn_comments": item.social_hn_comments,
                "social_reddit_upvotes": item.social_reddit_upvotes,
                "social_github_stars": item.social_github_stars,
                "canonical_hash": canonical_hash(item.title, item.url),
                "source_kind": source.kind,
            })

    # ── Phase 1c: Write candidates + pre-score for this kind ──
    with session_scope() as session:
        seen_keys: set = set()
        seen_hashes: set = set()
        for candidate in all_candidates:
            _upsert_raw_item(session, candidate, seen_keys, seen_hashes)

        raw_items = session.query(RawItem).filter(
            RawItem.pre_score.is_(None),
            RawItem.source_id.in_(source_ids),
        ).all()
        for raw in raw_items:
            source = session.query(Source).filter(Source.id == raw.source_id).first()
            if source is None:
                continue
            raw.pre_score = _compute_pre_score(raw, source)
            decision, reason = _scrape_decision(raw, source)
            raw.scrape_decision = decision
            raw.scrape_reason = reason
        session.flush()

    # ── Phase 2: Identify scrape targets for this source kind ──
    settings = get_settings()
    with session_scope() as session:
        to_scrape_ids = [
            row[0]
            for row in session.query(RawItem.id)
            .filter(
                RawItem.source_id.in_(source_ids),
                RawItem.scrape_decision.in_(["fetch_full", "fetch_full_priority"]),
            )
            .outerjoin(Article, Article.raw_item_id == RawItem.id)
            .filter(Article.id.is_(None))
            .order_by(func.coalesce(RawItem.published_at, RawItem.fetched_at).desc(), RawItem.pre_score.desc().nullslast())
            .limit(settings.max_scrape_per_run)
            .all()
        ]

    # ── Phase 2b: Watch band targets for this kind ──
    with session_scope() as session:
        watch_ids = [
            row[0]
            for row in session.query(RawItem.id)
            .filter(
                RawItem.source_id.in_(source_ids),
                RawItem.scrape_decision == "fetch_watch",
            )
            .outerjoin(Article, Article.raw_item_id == RawItem.id)
            .filter(Article.id.is_(None))
            .order_by(RawItem.pre_score.desc().nullslast())
            .limit(settings.max_watch_per_run)
            .all()
        ]

    # ── Phase 3: Scrape + score ──
    _process_scrape_targets(to_scrape_ids)
    if watch_ids:
        _process_scrape_targets(watch_ids)


def run_entity_resolution() -> None:
    """Periodic entity resolution refresh.

    Gathers unique entity names from recent articles, clusters them via
    embedding similarity, updates the in-memory cache, and persists the
    canonical mapping to the DB.
    """
    import logging

    from app.features.entity_resolution import resolve_entities, update_entity_resolution_cache

    log = logging.getLogger(__name__)

    with session_scope() as session:
        cutoff = utcnow() - timedelta(days=7)
        recent_articles = (
            session.query(Article)
            .join(RawItem, Article.raw_item_id == RawItem.id)
            .filter(
                or_(
                    RawItem.published_at >= cutoff,
                    RawItem.fetched_at >= cutoff,
                )
            )
            .all()
        )

        all_entity_names: set[str] = set()
        for art in recent_articles:
            if isinstance(art.entities, dict):
                all_entity_names.update(art.entities.keys())

        if not all_entity_names:
            log.info("run_entity_resolution: no entities found in recent articles")
            return

        resolution = resolve_entities(sorted(all_entity_names), distance_threshold=0.15)
        update_entity_resolution_cache(resolution)

        canon_entry = EntityCanonMap(
            canon_map=resolution.canon_map,
            cluster_count=len(resolution.clusters),
            entity_count=len(all_entity_names),
        )
        session.add(canon_entry)
        session.flush()

    log.info(
        "run_entity_resolution: resolved %d entities into %d clusters",
        len(all_entity_names),
        len(resolution.clusters),
    )


def run_relationship_inference() -> None:
    """Periodic LLM relationship inference for cluster pairs.

    Fetches recent clusters, runs mechanical relationship computation with
    Track B candidate generation, then calls the LLM for uncached candidates.
    Results are cached so the graph API can read them with zero latency.
    """
    import logging
    from collections import Counter

    from app.clustering.relationship_inference import infer_relationships
    from app.clustering.relationships import compute_cluster_relationships
    from app.features.entity_resolution import get_cached_entity_resolution

    log = logging.getLogger(__name__)

    with session_scope() as session:
        cutoff = utcnow() - timedelta(hours=48)
        clusters = (
            session.query(Cluster)
            .filter(Cluster.last_seen_at >= cutoff)
            .order_by(Cluster.max_global_score.desc())
            .limit(80)
            .all()
        )

        if len(clusters) < 2:
            log.info("run_relationship_inference: fewer than 2 clusters, skipping")
            return

        cluster_ids = [c.id for c in clusters]

        # Batch-load member articles (same logic as routes_graph.py)
        member_rows = (
            session.query(ClusterMember, Article, RawItem)
            .join(Article, ClusterMember.article_id == Article.id)
            .join(RawItem, Article.raw_item_id == RawItem.id)
            .filter(ClusterMember.cluster_id.in_(cluster_ids))
            .all()
        )

        cluster_articles: dict[str, list[tuple]] = {}
        for cm, article, raw in member_rows:
            cluster_articles.setdefault(cm.cluster_id, []).append((article, raw))

        canon_map = get_cached_entity_resolution()
        now = utcnow().replace(tzinfo=None)

        relationship_inputs = []
        for cluster in clusters:
            members = cluster_articles.get(cluster.id, [])
            articles_list = [art for art, _raw in members]

            # Top article summary
            top_summary = ""
            if articles_list:
                top_art = max(articles_list, key=lambda a: a.global_score or 0)
                top_summary = top_art.summary or ""

            # Dominant topic
            summed: dict[str, float] = {}
            count = 0
            for art in articles_list:
                topics = art.topics if isinstance(art.topics, dict) else {}
                if topics:
                    count += 1
                    for key, val in topics.items():
                        summed[key] = summed.get(key, 0.0) + float(val)
            if count > 0:
                avg = {k: v / count for k, v in summed.items()}
                max_key = max(avg, key=avg.get)
                dominant_topic = max_key if avg[max_key] >= 0.25 else "mixed"
                topic_weights = avg
            else:
                dominant_topic = "mixed"
                topic_weights = {}

            # Dominant event type
            types = [art.event_type for art in articles_list if art.event_type]
            if types:
                counter = Counter(types)
                most_common, cnt = counter.most_common(1)[0]
                dominant_event_type = most_common if cnt / len(types) > 0.5 else "MIXED"
            else:
                dominant_event_type = "MIXED"

            # Entities
            merged: dict[str, float] = {}
            for art in articles_list:
                ents = art.entities if isinstance(art.entities, dict) else {}
                for name, weight in ents.items():
                    canonical = canon_map.get(name.lower(), name) if canon_map else name
                    w = float(weight)
                    if canonical not in merged or w > merged[canonical]:
                        merged[canonical] = w
            sorted_ents = sorted(merged.items(), key=lambda kv: kv[1], reverse=True)[:5]
            entities = [{"name": name, "weight": weight} for name, weight in sorted_ents]

            # Age
            first_seen = cluster.first_seen_at
            if first_seen and first_seen.tzinfo:
                first_seen = first_seen.replace(tzinfo=None)
            last_seen = cluster.last_seen_at
            if last_seen and last_seen.tzinfo:
                last_seen = last_seen.replace(tzinfo=None)
            age_hours = ((last_seen - first_seen).total_seconds() / 3600) if first_seen and last_seen else 0.0

            relationship_inputs.append({
                "id": str(cluster.id),
                "centroid_embedding": cluster.centroid_embedding,
                "entities": entities,
                "dominant_event_type": dominant_event_type,
                "dominant_topic": dominant_topic,
                "topic_weights": topic_weights,
                "age_hours": age_hours,
                "headline": cluster.headline,
                "top_summary": top_summary,
                "coverage_count": cluster.coverage_count or 0,
            })

        _edges, llm_candidates = compute_cluster_relationships(
            relationship_inputs,
            entity_canon_map=canon_map,
            return_llm_candidates=True,
        )

        if not llm_candidates:
            log.info("run_relationship_inference: no LLM candidates")
            return

        # This call does actual LLM inference (cache_only=False)
        results = infer_relationships(llm_candidates, cache_only=False)

        non_unrelated = sum(1 for r in results if r.label != "unrelated")
        log.info(
            "run_relationship_inference: inferred %d relationships from %d candidates",
            non_unrelated,
            len(llm_candidates),
        )
