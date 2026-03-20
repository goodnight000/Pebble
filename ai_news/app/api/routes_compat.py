from __future__ import annotations

import asyncio
import json
from datetime import timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import defer, load_only
from starlette.responses import StreamingResponse

from app.common.blurbs import build_article_blurb
from app.common.mmr import mmr_select
from app.common.time import utcnow
from app.common.url_filters import is_evergreen_or_directory_url
from app.config import get_settings
from app.api.card_taxonomy import CATEGORY_PRIORITY, Category, build_topic_chips, category_for
from app.api.source_labels import build_grounding_source
from app.db import get_db, session_scope
from app.integrations.supabase import get_realtime_channel_map
from app.llm.client import LLMClient
from app.models import Article, Cluster, ClusterMember, DailyDigest, RawItem, Source, UserEntityWeight, UserPref, UserSourceWeight, UserTopicWeight
from app.scoring.signals import log_norm
from app.scoring.user_score import compute_user_score
from app.tasks.pipeline import run_refresh


router = APIRouter(prefix="/api", tags=["compat"])


def _content_type_for(source_kind: str, event_type: str) -> str:
    if source_kind in ("github", "github_trending"):
        return "github"
    if source_kind == "arxiv" or event_type == "RESEARCH_PAPER":
        return "research"
    return "news"
MIN_ITEMS_FALLBACK = 20
FETCHED_AT_FALLBACK_KINDS = {"hn", "reddit", "twitter", "mastodon", "bluesky", "github", "github_trending", "congress"}
# For these source kinds, always use fetched_at (discovery time) as the event time
FETCHED_AT_PREFERRED_KINDS = {"github", "github_trending"}
LIVE_MAX_AGE_HOURS = 24.0
WEEKLY_MAX_AGE_HOURS = 24.0 * 7.0


def _naive_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _load_user_context(db, user_id: str):
    prefs = db.query(UserPref).filter(UserPref.user_id == user_id).first()
    if not prefs:
        settings = get_settings()
        min_show = 30 if settings.app_env.lower() == "dev" else 55
        prefs = UserPref(user_id=user_id, min_show_score=min_show)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)

    entity_weights = {
        row.entity: {"weight": row.weight, "blocked": row.blocked}
        for row in db.query(UserEntityWeight).filter(UserEntityWeight.user_id == user_id).all()
    }
    topic_weights = {
        row.topic: {"weight": row.weight, "blocked": row.blocked}
        for row in db.query(UserTopicWeight).filter(UserTopicWeight.user_id == user_id).all()
    }
    source_weights = {
        str(row.source_id): {"weight": row.weight, "blocked": row.blocked}
        for row in db.query(UserSourceWeight).filter(UserSourceWeight.user_id == user_id).all()
    }
    return prefs, entity_weights, topic_weights, source_weights


def _to_iso(dt) -> str:
    if dt is None:
        return utcnow().isoformat()
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.astimezone(timezone.utc).isoformat()


def _decode_embedding_or_none(raw_embedding: bytes | None) -> np.ndarray | None:
    if not raw_embedding:
        return None
    try:
        embedding = np.frombuffer(raw_embedding, dtype=np.float32)
    except ValueError:
        return None
    if embedding.size != 384:
        return None
    return embedding


def _normalized_mapping(value: Any) -> Dict[str, float]:
    return value if isinstance(value, dict) else {}


def _safe_mmr_select(items: List[dict], *, limit: int, score_key: str) -> List[dict]:
    if not items:
        return []
    embeddings_arr = np.vstack([item["_embedding"] for item in items]) if items else np.zeros((0, 384), dtype=np.float32)
    try:
        return mmr_select(items, embeddings_arr, lambda_mult=0.80, k=max(limit, 1), score_key=score_key)
    except ValueError:
        return items[:limit]


def _event_time(raw, source):
    if source.kind in FETCHED_AT_PREFERRED_KINDS:
        ts = raw.fetched_at
    else:
        ts = raw.published_at
        if ts is None and source.kind in FETCHED_AT_FALLBACK_KINDS:
            ts = raw.fetched_at
    return _naive_utc(ts)


def _freshness_filter(cutoff):
    return or_(
        RawItem.published_at >= cutoff,
        and_(
            RawItem.published_at.is_(None),
            Source.kind.in_(tuple(FETCHED_AT_FALLBACK_KINDS)),
            RawItem.fetched_at >= cutoff,
        ),
        # For GitHub sources, use fetched_at (discovery time) regardless of published_at
        and_(
            Source.kind.in_(tuple(FETCHED_AT_PREFERRED_KINDS)),
            RawItem.fetched_at >= cutoff,
        ),
    )


def _diversify_by_category(items: List[dict], limit: int) -> List[dict]:
    if len(items) <= limit:
        return items
    buckets: Dict[Category, List[dict]] = {}
    for item in items:
        cat = item.get("category", "General")
        buckets.setdefault(cat, []).append(item)
    for bucket in buckets.values():
        bucket.sort(key=lambda x: x.get("significanceScore", 0), reverse=True)

    selected: List[dict] = []
    while len(selected) < limit:
        picked = False
        for cat in CATEGORY_PRIORITY:
            bucket = buckets.get(cat) or []
            if bucket:
                selected.append(bucket.pop(0))
                picked = True
                if len(selected) >= limit:
                    break
        if not picked:
            break
    return selected


def _compute_rank_score(user_score: float, age_hours: float, recency_bias: float, half_life_base: float) -> float:
    half_life_hours = half_life_base / max(recency_bias, 0.01)
    return user_score * 2 ** (-age_hours / half_life_hours)


def _soft_cap_by_source(
    items: List[dict],
    *,
    limit: int,
    max_per_source: int = 4,
) -> List[dict]:
    if not items:
        return items
    primary: List[dict] = []
    overflow: List[dict] = []
    counts: Dict[str, int] = {}

    for item in items:
        src = ((item.get("sources") or [{}])[0]).get("source") or "unknown"
        if counts.get(src, 0) < max_per_source and len(primary) < limit:
            primary.append(item)
            counts[src] = counts.get(src, 0) + 1
        else:
            overflow.append(item)

    if len(primary) >= limit:
        return primary[:limit]

    for item in overflow:
        if len(primary) >= limit:
            break
        primary.append(item)
    return primary


def _backfill_with_low_score(
    selected: List[dict],
    low_score_items: List[dict],
    *,
    limit: int,
    min_items: int = MIN_ITEMS_FALLBACK,
) -> List[dict]:
    target = min(limit, max(1, min_items))
    if len(selected) >= target:
        return selected
    selected_ids = {item["id"] for item in selected}
    source_counts: Dict[str, int] = {}
    for item in selected:
        src = ((item.get("sources") or [{}])[0]).get("source") or "unknown"
        source_counts[src] = source_counts.get(src, 0) + 1
    low_sorted = sorted(low_score_items, key=lambda x: x.get("_rank_score", 0), reverse=True)

    # Pass 1: backfill with a soft per-source cap so one feed doesn't dominate.
    for item in low_sorted:
        if len(selected) >= target:
            break
        if item["id"] in selected_ids:
            continue
        src = ((item.get("sources") or [{}])[0]).get("source") or "unknown"
        if source_counts.get(src, 0) >= 2:
            continue
        selected.append(item)
        selected_ids.add(item["id"])
        source_counts[src] = source_counts.get(src, 0) + 1

    # Pass 2: if still short, fill by score regardless of source cap.
    for item in low_sorted:
        if len(selected) >= target:
            break
        if item["id"] in selected_ids:
            continue
        src = ((item.get("sources") or [{}])[0]).get("source") or "unknown"
        selected.append(item)
        selected_ids.add(item["id"])
        source_counts[src] = source_counts.get(src, 0) + 1
    return selected


def _merge_translation_status(*statuses: str) -> str:
    return "ready" if all(status == "ready" for status in statuses) else "unavailable"


def _localize_news_items(items: List[dict], locale: str, llm: LLMClient) -> tuple[List[dict], str]:
    if locale != "zh":
        return items, "ready"
    return llm.translate_news_items(items)


def _localize_digest_sections(digests: Dict[str, dict], locale: str, llm: LLMClient) -> tuple[Dict[str, dict], str]:
    if locale != "zh":
        return digests, "ready"
    return llm.translate_digest_sections(digests)


def _select_articles(
    db,
    *,
    user_id: str,
    cutoff: Any,
    half_life_base: float,
    limit: int,
    content_type: str | None = None,
) -> List[dict]:
    now = _naive_utc(utcnow())
    max_age_hours = max(0.0, (now - cutoff).total_seconds() / 3600)
    prefs, entity_weights, topic_weights, source_weights = _load_user_context(db, user_id)

    query = (
        db.query(Article, RawItem, Source, Cluster)
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .join(Source, RawItem.source_id == Source.id)
        .outerjoin(ClusterMember, ClusterMember.article_id == Article.id)
        .outerjoin(Cluster, Cluster.id == ClusterMember.cluster_id)
        .options(
            load_only(
                Article.id, Article.final_url, Article.summary, Article.event_type,
                Article.topics, Article.entities, Article.content_type,
                Article.final_score, Article.global_score, Article.urgent,
                Article.trust_label, Article.trust_components,
                Article.verification_state, Article.verification_confidence,
                Article.freshness_state,
            ),
            load_only(
                RawItem.id, RawItem.title, RawItem.snippet,
                RawItem.published_at, RawItem.fetched_at,
                RawItem.social_hn_points, RawItem.social_reddit_upvotes,
                RawItem.social_github_stars, RawItem.source_id,
            ),
            load_only(Source.id, Source.name, Source.kind, Source.authority),
            load_only(
                Cluster.id, Cluster.sources_count, Cluster.max_global_score,
                Cluster.coverage_count, Cluster.independent_sources_count,
                Cluster.has_official_confirmation, Cluster.cluster_trust_score,
            ),
        )
        .filter(_freshness_filter(cutoff))
    )
    if content_type:
        query = query.filter(Article.content_type == content_type)
    rows = query.all()

    has_real = any(source.name != "Local Sample Feed" for _article, _raw, source, _cluster in rows)

    # Use a lower score threshold for content-type-specific queries so
    # tabs like GitHub (which score lower globally) still have items.
    min_score = prefs.min_show_score
    if content_type and content_type != "news":
        min_score = min(min_score, 25)

    items: List[dict] = []
    low_score_items: List[dict] = []
    for article, raw, source, cluster in rows:
        if has_real and source.name == "Local Sample Feed":
            continue
        if is_evergreen_or_directory_url(article.final_url):
            continue

        sources_count = cluster.sources_count if cluster else 1
        coverage_score = log_norm(sources_count, 8)
        social_score = log_norm(raw.social_hn_points or 0, 500)
        social_score = max(social_score, log_norm(raw.social_reddit_upvotes or 0, 5000))
        social_score = max(social_score, log_norm(raw.social_github_stars or 0, 5000))
        topics = _normalized_mapping(article.topics)
        entities = _normalized_mapping(article.entities)
        base_score = article.final_score if article.final_score is not None else article.global_score
        user_score = compute_user_score(
            global_score=base_score,
            event_type=article.event_type,
            topics=topics,
            entities=entities,
            source_id=str(source.id),
            source_authority=source.authority,
            coverage_score=coverage_score,
            social_score=social_score,
            final_url=article.final_url,
            user_pref=prefs,
            user_entity_weights=entity_weights,
            user_topic_weights=topic_weights,
            user_source_weights=source_weights,
        )
        ts = _event_time(raw, source)
        if ts is None:
            continue
        age_hours = (now - ts).total_seconds() / 3600 if ts else 0.0
        if age_hours < 0 or age_hours > max_age_hours:
            continue
        rank_score = _compute_rank_score(user_score, age_hours, prefs.recency_bias, half_life_base)

        summary = build_article_blurb(title=raw.title, summary=article.summary, snippet=raw.snippet)
        category: Category = category_for(article.event_type, topics)
        tags = build_topic_chips(
            category,
            article.event_type,
            topics,
            title=raw.title,
            summary=summary,
            source_name=source.name,
        )
        effective_score = article.final_score if article.final_score is not None else article.global_score
        score_int = int(round(user_score if user_score is not None else effective_score or 0))
        score_int = max(0, min(100, score_int))

        payload = {
            "id": str(article.id),
            "title": raw.title,
            "summary": summary,
            "significanceScore": score_int,
            "category": category,
            "contentType": _content_type_for(source.kind, article.event_type),
            "timestamp": _to_iso(ts),
            "tags": tags,
            "sources": [build_grounding_source(source=source, url=article.final_url)],
            "trustLabel": article.trust_label,
            "trustComponents": article.trust_components,
            "verificationState": getattr(article, "verification_state", None),
            "verificationConfidence": getattr(article, "verification_confidence", None),
            "freshnessState": getattr(article, "freshness_state", None),
            "finalScore": article.final_score or article.global_score,
            "_rank_score": float(rank_score),
            "_article_id": article.id,
        }
        if user_score < min_score:
            low_score_items.append(payload)
        else:
            items.append(payload)

    items_sorted = sorted(items, key=lambda x: x["_rank_score"], reverse=True)

    # Lazy-load embeddings for top-N candidates only
    mmr_candidate_count = min(len(items_sorted), limit * 2)
    mmr_candidates = items_sorted[:mmr_candidate_count]
    if mmr_candidates:
        candidate_article_ids = [item["_article_id"] for item in mmr_candidates]
        embedding_rows = (
            db.query(Article.id, Article.embedding)
            .filter(Article.id.in_(candidate_article_ids))
            .all()
        )
        embedding_map = {}
        for art_id, raw_emb in embedding_rows:
            emb = _decode_embedding_or_none(raw_emb)
            if emb is not None:
                embedding_map[str(art_id)] = emb

        # Attach embeddings to candidates; drop any without valid embedding
        for item in mmr_candidates:
            item["_embedding"] = embedding_map.get(item["id"])
        mmr_candidates = [item for item in mmr_candidates if item["_embedding"] is not None]

    selected = _safe_mmr_select(mmr_candidates, limit=limit, score_key="_rank_score")

    # Serendipity: reintroduce some high-global-score items not selected.
    if prefs.serendipity > 0 and items_sorted:
        n = max(1, round(prefs.serendipity * len(selected)))
        selected_ids = {item["id"] for item in selected}
        global_candidates = [
            item for item in items_sorted if item["significanceScore"] >= 75 and item["id"] not in selected_ids
        ]
        selected.extend(global_candidates[:n])

    selected = _soft_cap_by_source(selected, limit=limit, max_per_source=4)
    selected = _backfill_with_low_score(selected, low_score_items, limit=limit)

    for item in selected:
        item.pop("_embedding", None)
        item.pop("_rank_score", None)
        item.pop("_article_id", None)
    return selected[:limit]


def _select_weekly_top(db, *, user_id: str, limit: int) -> List[dict]:
    now = _naive_utc(utcnow())
    cutoff = now - timedelta(days=7)
    max_age_hours = WEEKLY_MAX_AGE_HOURS

    article_ids = [
        row[0] for row in
        db.query(Cluster.top_article_id)
        .filter(Cluster.last_seen_at >= cutoff, Cluster.top_article_id.isnot(None))
        .all()
    ]
    if not article_ids:
        return []

    prefs, entity_weights, topic_weights, source_weights = _load_user_context(db, user_id)

    rows = (
        db.query(Article, RawItem, Source, Cluster)
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .join(Source, RawItem.source_id == Source.id)
        .outerjoin(ClusterMember, ClusterMember.article_id == Article.id)
        .outerjoin(Cluster, Cluster.id == ClusterMember.cluster_id)
        .options(
            load_only(
                Article.id, Article.final_url, Article.summary, Article.event_type,
                Article.topics, Article.entities, Article.content_type,
                Article.final_score, Article.global_score, Article.urgent,
                Article.trust_label, Article.trust_components,
                Article.verification_state, Article.verification_confidence,
                Article.freshness_state,
            ),
            load_only(
                RawItem.id, RawItem.title, RawItem.snippet,
                RawItem.published_at, RawItem.fetched_at,
                RawItem.social_hn_points, RawItem.social_reddit_upvotes,
                RawItem.social_github_stars, RawItem.source_id,
            ),
            load_only(Source.id, Source.name, Source.kind, Source.authority),
            load_only(
                Cluster.id, Cluster.sources_count, Cluster.max_global_score,
                Cluster.coverage_count, Cluster.independent_sources_count,
                Cluster.has_official_confirmation, Cluster.cluster_trust_score,
            ),
        )
        .filter(Article.id.in_(article_ids))
        .filter(func.coalesce(Article.final_score, Article.global_score) >= 30)
        .order_by(func.coalesce(Article.final_score, Article.global_score).desc())
        .limit(200)
        .all()
    )
    has_real = any(source.name != "Local Sample Feed" for _article, _raw, source, _cluster in rows)

    items: List[dict] = []
    low_score_items: List[dict] = []
    for article, raw, source, cluster in rows:
        if has_real and source.name == "Local Sample Feed":
            continue
        if is_evergreen_or_directory_url(article.final_url):
            continue
        sources_count = cluster.sources_count if cluster else 1
        coverage_score = log_norm(sources_count, 8)
        social_score = log_norm(raw.social_hn_points or 0, 500)
        social_score = max(social_score, log_norm(raw.social_reddit_upvotes or 0, 5000))
        social_score = max(social_score, log_norm(raw.social_github_stars or 0, 5000))
        topics = _normalized_mapping(article.topics)
        entities = _normalized_mapping(article.entities)
        base_score = article.final_score if article.final_score is not None else article.global_score
        user_score = compute_user_score(
            global_score=base_score,
            event_type=article.event_type,
            topics=topics,
            entities=entities,
            source_id=str(source.id),
            source_authority=source.authority,
            coverage_score=coverage_score,
            social_score=social_score,
            final_url=article.final_url,
            user_pref=prefs,
            user_entity_weights=entity_weights,
            user_topic_weights=topic_weights,
            user_source_weights=source_weights,
        )
        ts = _event_time(raw, source)
        if ts is None:
            continue
        age_hours = (now - ts).total_seconds() / 3600 if ts else 0.0
        if age_hours < 0 or age_hours > max_age_hours:
            continue
        rank_score = _compute_rank_score(user_score, age_hours, prefs.recency_bias, 72)

        summary = build_article_blurb(title=raw.title, summary=article.summary, snippet=raw.snippet)
        category: Category = category_for(article.event_type, topics)
        tags = build_topic_chips(
            category,
            article.event_type,
            topics,
            title=raw.title,
            summary=summary,
            source_name=source.name,
        )
        effective_score = article.final_score if article.final_score is not None else article.global_score
        score_int = int(round(user_score if user_score is not None else effective_score or 0))
        score_int = max(0, min(100, score_int))

        payload = {
            "id": str(article.id),
            "title": raw.title,
            "summary": summary,
            "significanceScore": score_int,
            "category": category,
            "contentType": _content_type_for(source.kind, article.event_type),
            "timestamp": _to_iso(ts),
            "tags": tags,
            "sources": [build_grounding_source(source=source, url=article.final_url)],
            "trustLabel": article.trust_label,
            "trustComponents": article.trust_components,
            "verificationState": getattr(article, "verification_state", None),
            "verificationConfidence": getattr(article, "verification_confidence", None),
            "freshnessState": getattr(article, "freshness_state", None),
            "finalScore": article.final_score or article.global_score,
            "_rank_score": float(rank_score),
            "_article_id": article.id,
        }
        if user_score < prefs.min_show_score:
            low_score_items.append(payload)
        else:
            items.append(payload)

    items_sorted = sorted(items, key=lambda x: x["_rank_score"], reverse=True)

    # Lazy-load embeddings for top-N candidates only
    mmr_candidate_count = min(len(items_sorted), limit * 2)
    mmr_candidates = items_sorted[:mmr_candidate_count]
    if mmr_candidates:
        candidate_article_ids = [item["_article_id"] for item in mmr_candidates]
        embedding_rows = (
            db.query(Article.id, Article.embedding)
            .filter(Article.id.in_(candidate_article_ids))
            .all()
        )
        embedding_map = {}
        for art_id, raw_emb in embedding_rows:
            emb = _decode_embedding_or_none(raw_emb)
            if emb is not None:
                embedding_map[str(art_id)] = emb

        # Attach embeddings to candidates; drop any without valid embedding
        for item in mmr_candidates:
            item["_embedding"] = embedding_map.get(item["id"])
        mmr_candidates = [item for item in mmr_candidates if item["_embedding"] is not None]

    selected = _safe_mmr_select(mmr_candidates, limit=limit, score_key="_rank_score")
    selected = _soft_cap_by_source(selected, limit=limit, max_per_source=3)
    selected = _backfill_with_low_score(selected, low_score_items, limit=limit)

    for item in selected:
        item.pop("_embedding", None)
        item.pop("_rank_score", None)
        item.pop("_article_id", None)
    return selected[:limit]


@router.get("/news")
def compat_news(limit: int = 30, locale: str = Query("en", pattern="^(en|zh)$"), db=Depends(get_db)):
    settings = get_settings()
    now = _naive_utc(utcnow())
    cutoff = now - timedelta(hours=24)
    items = _select_articles(db, user_id=settings.public_user_id, cutoff=cutoff, half_life_base=18, limit=limit)
    llm = LLMClient()
    localized_items, translation_status = _localize_news_items(items, locale, llm)
    return {
        "items": localized_items,
        "locale": locale,
        "sourceLocale": "en",
        "translationStatus": translation_status,
    }


@router.get("/news/weekly")
def compat_news_weekly(limit: int = 10, locale: str = Query("en", pattern="^(en|zh)$"), db=Depends(get_db)):
    settings = get_settings()
    items = _select_weekly_top(db, user_id=settings.public_user_id, limit=limit)
    llm = LLMClient()
    localized_items, translation_status = _localize_news_items(items, locale, llm)
    return {
        "items": localized_items,
        "locale": locale,
        "sourceLocale": "en",
        "translationStatus": translation_status,
    }


@router.get("/digest/today")
def compat_digest_today(locale: str = Query("en", pattern="^(en|zh)$"), db=Depends(get_db)):
    settings = get_settings()
    now = _naive_utc(utcnow())
    cutoff = now - timedelta(hours=24)
    candidates = _select_articles(db, user_id=settings.public_user_id, cutoff=cutoff, half_life_base=18, limit=30)
    all_items = _diversify_by_category(sorted(candidates, key=lambda x: x["significanceScore"], reverse=True), 12)
    all_ids = {item["id"] for item in all_items}

    # Select top items per content type so each tab has content
    for ct in ("news", "research", "github"):
        ct_candidates = _select_articles(
            db, user_id=settings.public_user_id, cutoff=cutoff,
            half_life_base=18, limit=10, content_type=ct,
        )
        for c in ct_candidates:
            if c["id"] not in all_ids:
                all_items.append(c)
                all_ids.add(c["id"])

    items = all_items

    # Try to load stored per-content-type digests
    content_types = ["all", "news", "research", "github"]
    stored_rows = (
        db.query(DailyDigest)
        .options(defer(DailyDigest.longform_html))
        .filter(
            DailyDigest.user_id == settings.public_user_id,
            func.date(DailyDigest.date) == now.date(),
            DailyDigest.content_type.in_(content_types),
        )
        .all()
    )
    stored_map = {row.content_type: row for row in stored_rows}

    if stored_map:
        digests = {}
        for ct in content_types:
            row = stored_map.get(ct)
            if row:
                digests[ct] = {
                    "headline": row.headline or "Daily AI Pulse",
                    "executiveSummary": row.executive_summary or "Key AI updates from the last 24 hours.",
                    "llmAuthored": row.llm_authored,
                }
            else:
                digests[ct] = {
                    "headline": "Daily AI Pulse",
                    "executiveSummary": "Key AI updates from the last 24 hours.",
                    "llmAuthored": False,
                }
    else:
        # Fallback: generate on-the-fly for "all" only
        llm = LLMClient()
        copy = llm.generate_digest_copy(items)
        fallback_digest = {
            "headline": copy.get("headline"),
            "executiveSummary": copy.get("executiveSummary"),
            "llmAuthored": bool(copy.get("llmAuthored")),
        }
        digests = {ct: fallback_digest for ct in content_types}

    _trusted_labels = {"official", "confirmed", "likely", None}
    breaking = next(
        (item for item in items
         if item.get("significanceScore", 0) >= 90
         and item.get("trustLabel") in _trusted_labels),
        None,
    )
    llm = LLMClient()
    localized_items, items_status = _localize_news_items(items, locale, llm)
    localized_digests, digests_status = _localize_digest_sections(digests, locale, llm)
    if breaking:
        localized_breaking_candidates, breaking_status = _localize_news_items([breaking], locale, llm)
        localized_breaking = localized_breaking_candidates[0] if localized_breaking_candidates else breaking
    else:
        localized_breaking = None
        breaking_status = "ready"
    translation_status = _merge_translation_status(items_status, digests_status, breaking_status)
    return {
        "digests": localized_digests,
        # Keep top-level fields for backward compat
        "headline": localized_digests["all"]["headline"],
        "executiveSummary": localized_digests["all"]["executiveSummary"],
        "items": localized_items,
        "breakingAlert": localized_breaking,
        "llmAuthored": localized_digests["all"].get("llmAuthored", False),
        "locale": locale,
        "sourceLocale": "en",
        "translationStatus": translation_status,
    }


@router.post("/refresh")
async def compat_refresh(background_tasks: BackgroundTasks):
    # Kick off refresh in the background so the endpoint returns immediately.
    # In production, Celery beat/worker should drive polling instead.
    import os
    if not os.environ.get("DISABLE_SCHEDULER"):
        background_tasks.add_task(run_refresh)
    return {"status": "ok"}


@router.post("/translate")
def compat_translate(payload: dict):
    llm = LLMClient()
    return llm.translate_digest(payload)


@router.get("/news/realtime/config")
def compat_realtime_config():
    settings = get_settings()
    return {
        "enabled": settings.supabase_realtime_enabled,
        "channels": get_realtime_channel_map(settings) if settings.supabase_realtime_enabled else {},
    }


@router.get("/stream")
async def compat_stream(request: Request):
    settings = get_settings()

    async def event_generator():
        yield "event: ping\n"
        yield f"data: {json.dumps({'ts': utcnow().isoformat()})}\n\n"

        last_seen = _naive_utc(utcnow())

        while True:
            if await request.is_disconnected():
                return

            matches = []
            try:
                with session_scope() as db:
                    prefs, entity_weights, topic_weights, source_weights = _load_user_context(db, settings.public_user_id)
                    rows = (
                        db.query(Article, RawItem, Source, Cluster)
                        .join(RawItem, Article.raw_item_id == RawItem.id)
                        .join(Source, RawItem.source_id == Source.id)
                        .outerjoin(ClusterMember, ClusterMember.article_id == Article.id)
                        .outerjoin(Cluster, Cluster.id == ClusterMember.cluster_id)
                        .options(
                            load_only(
                                Article.id, Article.final_url, Article.summary, Article.event_type,
                                Article.topics, Article.entities, Article.content_type,
                                Article.final_score, Article.global_score, Article.urgent,
                                Article.trust_label, Article.trust_components,
                                Article.verification_state, Article.verification_confidence,
                                Article.freshness_state, Article.created_at,
                            ),
                            load_only(
                                RawItem.id, RawItem.title, RawItem.snippet,
                                RawItem.published_at, RawItem.fetched_at,
                                RawItem.social_hn_points, RawItem.social_reddit_upvotes,
                                RawItem.social_github_stars, RawItem.source_id,
                            ),
                            load_only(Source.id, Source.name, Source.kind, Source.authority),
                            load_only(
                                Cluster.id, Cluster.sources_count, Cluster.max_global_score,
                                Cluster.coverage_count, Cluster.independent_sources_count,
                                Cluster.has_official_confirmation, Cluster.cluster_trust_score,
                            ),
                        )
                        .filter(Article.created_at > last_seen)
                        .order_by(Article.created_at.asc())
                        .limit(25)
                        .all()
                    )

                    if rows:
                        last_seen = max((article.created_at for article, _raw, _source, _cluster in rows if article.created_at), default=last_seen)

                    now = _naive_utc(utcnow())
                    for article, raw, source, cluster in rows:
                        if is_evergreen_or_directory_url(article.final_url):
                            continue
                        ts = _event_time(raw, source)
                        if ts is None:
                            continue
                        age_hours = (now - ts).total_seconds() / 3600
                        if age_hours < 0 or age_hours > LIVE_MAX_AGE_HOURS:
                            continue
                        sources_count = cluster.sources_count if cluster else 1
                        coverage_score = log_norm(sources_count, 8)
                        social_score = log_norm(raw.social_hn_points or 0, 500)
                        social_score = max(social_score, log_norm(raw.social_reddit_upvotes or 0, 5000))
                        social_score = max(social_score, log_norm(raw.social_github_stars or 0, 5000))
                        base_score = article.final_score if article.final_score is not None else article.global_score
                        user_score = compute_user_score(
                            global_score=base_score,
                            event_type=article.event_type,
                            topics=article.topics,
                            entities=article.entities,
                            source_id=str(source.id),
                            source_authority=source.authority,
                            coverage_score=coverage_score,
                            social_score=social_score,
                            final_url=article.final_url,
                            user_pref=prefs,
                            user_entity_weights=entity_weights,
                            user_topic_weights=topic_weights,
                            user_source_weights=source_weights,
                        )
                        if user_score < prefs.min_show_score:
                            continue

                        category: Category = category_for(article.event_type, article.topics)
                        summary = build_article_blurb(title=raw.title, summary=article.summary, snippet=raw.snippet)
                        effective_score = article.final_score if article.final_score is not None else article.global_score
                        matches.append({
                            "id": str(article.id),
                            "title": raw.title,
                            "summary": summary,
                            "significanceScore": int(round(user_score if user_score is not None else effective_score or 0)),
                            "category": category,
                            "contentType": _content_type_for(source.kind, article.event_type),
                            "timestamp": _to_iso(ts),
                            "tags": build_topic_chips(
                                category,
                                article.event_type,
                                _normalized_mapping(article.topics),
                                title=raw.title,
                                summary=summary,
                                source_name=source.name,
                            ),
                            "sources": [build_grounding_source(source=source, url=article.final_url)],
                            "trustLabel": article.trust_label,
                            "trustComponents": article.trust_components,
                            "verificationState": getattr(article, "verification_state", None),
                            "verificationConfidence": getattr(article, "verification_confidence", None),
                            "freshnessState": getattr(article, "freshness_state", None),
                            "finalScore": article.final_score or article.global_score,
                        })
            except Exception:
                matches = []

            for match in matches:
                yield "event: news\n"
                yield f"data: {json.dumps(match)}\n\n"

            await asyncio.sleep(60)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
