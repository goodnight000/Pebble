from __future__ import annotations

from datetime import timedelta, timezone

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import defer

from app.common.mmr import mmr_select
from app.common.time import utcnow
from app.common.url_filters import is_evergreen_or_directory_url
from app.config import get_settings
from app.db import get_db
from app.integrations.supabase import get_realtime_channel_map
from app.models import Article, Cluster, ClusterMember, RawItem, Source, User, UserEntityWeight, UserPref, UserSourceWeight, UserTopicWeight
from app.scoring.signals import log_norm
from app.scoring.user_score import compute_user_score

router = APIRouter(prefix="/v1/news", tags=["news"])
FETCHED_AT_FALLBACK_KINDS = {"hn", "reddit", "twitter", "mastodon", "bluesky", "github", "github_trending", "congress"}
FETCHED_AT_PREFERRED_KINDS = {"github", "github_trending"}
LIVE_MAX_AGE_HOURS = 24.0
WEEK_MAX_AGE_HOURS = 24.0 * 7.0
URGENT_MAX_AGE_HOURS = 6.0


def _naive_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


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


def _normalized_mapping(value):
    return value if isinstance(value, dict) else {}


def _safe_mmr_select(items, *, limit: int):
    if not items:
        return []
    embeddings_arr = np.vstack([item["_embedding"] for item in items]) if items else np.zeros((0, 384), dtype=np.float32)
    try:
        return mmr_select(items, embeddings_arr, lambda_mult=0.80, k=limit, score_key="rank_score")
    except ValueError:
        return items[:limit]


def _load_user_context(db, user_id: str):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
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


def _article_payload(article, raw, source, user_score, rank_score):
    return {
        "id": str(article.id),
        "title": raw.title,
        "url": article.final_url,
        "source": source.name,
        "published_at": raw.published_at or raw.fetched_at,
        "summary": article.summary,
        "event_type": article.event_type,
        "topics": article.topics,
        "entities": article.entities,
        "global_score": article.global_score,
        "user_score": user_score,
        "rank_score": rank_score,
        "urgent": article.urgent,
        "trust_label": article.trust_label,
        "trust_components": article.trust_components,
        "final_score": article.final_score or article.global_score,
    }


def _compute_rank_score(user_score: float, age_hours: float, recency_bias: float, half_life_base: float) -> float:
    half_life_hours = half_life_base / max(recency_bias, 0.01)
    return user_score * 2 ** (-age_hours / half_life_hours)


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


@router.get("/today")
def get_today(user_id: str, db=Depends(get_db)):
    now = _naive_utc(utcnow())
    cutoff = now - timedelta(hours=24)
    max_age_hours = LIVE_MAX_AGE_HOURS
    prefs, entity_weights, topic_weights, source_weights = _load_user_context(db, user_id)

    rows = (
        db.query(Article, RawItem, Source, Cluster)
        .options(defer(Article.html), defer(Article.llm_reasoning))
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .join(Source, RawItem.source_id == Source.id)
        .outerjoin(ClusterMember, ClusterMember.article_id == Article.id)
        .outerjoin(Cluster, Cluster.id == ClusterMember.cluster_id)
        .filter(_freshness_filter(cutoff))
        .all()
    )

    # If we have any real articles, hide the seeded sample feed from the UI.
    has_real = any(source.name != "Local Sample Feed" for _article, _raw, source, _cluster in rows)

    items = []
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
        embedding = _decode_embedding_or_none(article.embedding)
        if embedding is None:
            continue
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
        if user_score < prefs.min_show_score:
            continue
        ts = _event_time(raw, source)
        if ts is None:
            continue
        age_hours = (now - ts).total_seconds() / 3600 if ts else 0.0
        if age_hours < 0 or age_hours > max_age_hours:
            continue
        rank_score = _compute_rank_score(user_score, age_hours, prefs.recency_bias, 18)
        payload = _article_payload(article, raw, source, user_score, rank_score)
        payload["_embedding"] = embedding
        items.append(payload)

    items_sorted = sorted(items, key=lambda x: x["rank_score"], reverse=True)
    selected = _safe_mmr_select(items_sorted, limit=30)

    if prefs.serendipity > 0 and items_sorted:
        n = max(1, round(prefs.serendipity * len(selected)))
        selected_ids = {item["id"] for item in selected}
        global_candidates = [item for item in items_sorted if item["global_score"] >= 75 and item["id"] not in selected_ids]
        selected.extend(global_candidates[:n])

    for item in selected:
        item.pop("_embedding", None)
    return {"items": selected[:30]}


@router.get("/realtime/config")
def get_realtime_config():
    settings = get_settings()
    return {
        "enabled": settings.supabase_realtime_enabled,
        "channels": get_realtime_channel_map(settings) if settings.supabase_realtime_enabled else {},
    }


@router.get("/week")
def get_week(user_id: str, db=Depends(get_db)):
    now = _naive_utc(utcnow())
    cutoff = now - timedelta(days=7)
    max_age_hours = WEEK_MAX_AGE_HOURS
    prefs, entity_weights, topic_weights, source_weights = _load_user_context(db, user_id)

    clusters = db.query(Cluster).filter(Cluster.last_seen_at >= cutoff).all()
    article_ids = [cluster.top_article_id for cluster in clusters if cluster.top_article_id]

    rows = (
        db.query(Article, RawItem, Source, Cluster)
        .options(defer(Article.html), defer(Article.llm_reasoning))
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .join(Source, RawItem.source_id == Source.id)
        .outerjoin(ClusterMember, ClusterMember.article_id == Article.id)
        .outerjoin(Cluster, Cluster.id == ClusterMember.cluster_id)
        .filter(Article.id.in_(article_ids))
        .all()
    )

    has_real = any(source.name != "Local Sample Feed" for _article, _raw, source, _cluster in rows)

    items = []
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
        embedding = _decode_embedding_or_none(article.embedding)
        if embedding is None:
            continue
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
        if user_score < prefs.min_show_score:
            continue
        ts = _event_time(raw, source)
        if ts is None:
            continue
        age_hours = (now - ts).total_seconds() / 3600 if ts else 0.0
        if age_hours < 0 or age_hours > max_age_hours:
            continue
        rank_score = _compute_rank_score(user_score, age_hours, prefs.recency_bias, 72)
        payload = _article_payload(article, raw, source, user_score, rank_score)
        payload["_embedding"] = embedding
        items.append(payload)

    items_sorted = sorted(items, key=lambda x: x["rank_score"], reverse=True)
    selected = _safe_mmr_select(items_sorted, limit=50)

    if prefs.serendipity > 0 and items_sorted:
        n = max(1, round(prefs.serendipity * len(selected)))
        selected_ids = {item["id"] for item in selected}
        global_candidates = [item for item in items_sorted if item["global_score"] >= 75 and item["id"] not in selected_ids]
        selected.extend(global_candidates[:n])

    for item in selected:
        item.pop("_embedding", None)
    return {"items": selected[:50]}


@router.get("/urgent")
def get_urgent(user_id: str, db=Depends(get_db)):
    now = _naive_utc(utcnow())
    cutoff = now - timedelta(hours=6)
    max_age_hours = URGENT_MAX_AGE_HOURS
    prefs, entity_weights, topic_weights, source_weights = _load_user_context(db, user_id)

    rows = (
        db.query(Article, RawItem, Source, Cluster)
        .options(defer(Article.html), defer(Article.text), defer(Article.embedding), defer(Article.llm_reasoning))
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .join(Source, RawItem.source_id == Source.id)
        .outerjoin(ClusterMember, ClusterMember.article_id == Article.id)
        .outerjoin(Cluster, Cluster.id == ClusterMember.cluster_id)
        .filter(Article.urgent.is_(True))
        .filter(_freshness_filter(cutoff))
        .all()
    )

    has_real = any(source.name != "Local Sample Feed" for _article, _raw, source, _cluster in rows)

    items = []
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
        if user_score < prefs.min_urgent_score:
            continue
        ts = _event_time(raw, source)
        if ts is None:
            continue
        age_hours = (now - ts).total_seconds() / 3600 if ts else 0.0
        if age_hours < 0 or age_hours > max_age_hours:
            continue
        items.append(
            _article_payload(
                article,
                raw,
                source,
                user_score,
                article.final_score if article.final_score is not None else article.global_score,
            )
        )

    items_sorted = sorted(items, key=lambda x: x.get("rank_score", 0), reverse=True)
    return {"items": items_sorted}
