from __future__ import annotations

import hashlib
from collections import Counter
from datetime import timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import defer

from app.common.time import utcnow
from app.db import get_db
from app.llm.cache import get_cached, set_cached
from app.llm.client import LLMClient
from app.models import Article, Cluster, ClusterMember, RawItem, Source

router = APIRouter(prefix="/v1/signal-map", tags=["signal-map"])

TOPIC_TAGS = {
    "llms": "LLM",
    "multimodal": "Multimodal",
    "agents": "Agents",
    "robotics": "Robotics",
    "vision": "Vision",
    "audio_speech": "Audio",
    "hardware_chips": "Hardware",
    "open_source": "Open Source",
    "startups_funding": "Funding",
    "enterprise_apps": "Enterprise",
    "safety_policy": "Policy",
    "research_methods": "Research",
}


def _naive_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


@lru_cache
def _build_tier_map() -> dict[str, int]:
    config_path = Path(__file__).resolve().parent.parent / "config_entities.yml"
    with open(config_path) as f:
        data = yaml.safe_load(f)
    tiers = data.get("ENTITY_TIERS", {})
    tier_map: dict[str, int] = {}
    for tier_key, names in tiers.items():
        tier_int = int(tier_key.replace("tier", ""))
        for name in names:
            tier_map[name] = tier_int
    return tier_map


def _pca_2d(embeddings: np.ndarray) -> np.ndarray:
    """Project Nx384 embeddings to Nx2 via SVD, normalize to [0,1]."""
    n = embeddings.shape[0]
    if n < 3:
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
        coords = np.column_stack([np.cos(angles), np.sin(angles)])
        mins = coords.min(axis=0)
        ptp = coords.max(axis=0) - mins
        return (coords - mins) / (ptp + 1e-9)
    centered = embeddings - embeddings.mean(axis=0)
    _, _, Vt = np.linalg.svd(centered, full_matrices=False)
    projected = centered @ Vt[:2].T
    mins = projected.min(axis=0)
    ptp = projected.max(axis=0) - mins
    ptp[ptp == 0] = 1.0
    return (projected - mins) / ptp


def _compute_cluster_trust(cluster, top_article, now) -> tuple[float, str]:
    if getattr(cluster, "cluster_verification_confidence", None) is not None:
        return (
            float(cluster.cluster_verification_confidence or 0),
            cluster.cluster_trust_label or top_article.trust_label or "unverified",
        )

    corroboration_boost = 10 if (cluster.independent_sources_count or 0) >= 3 else 0
    cluster_trust_score = min(100, (top_article.trust_score or 0) + corroboration_boost)

    top_label = top_article.trust_label
    if top_label in ("disputed", "official"):
        trust_label = top_label
    elif cluster_trust_score >= 75 and (cluster.independent_sources_count or 0) >= 3:
        trust_label = "confirmed"
    elif cluster_trust_score >= 55 and (cluster.independent_sources_count or 0) >= 2:
        trust_label = "likely"
    else:
        first_seen = _naive_utc(cluster.first_seen_at)
        age_hours = (now - first_seen).total_seconds() / 3600 if first_seen else 0
        if age_hours < 6:
            trust_label = "developing"
        elif cluster_trust_score < 40:
            trust_label = "unverified"
        else:
            trust_label = top_label or "unverified"

    return cluster_trust_score, trust_label


def _compute_dominant_topic(articles: list) -> tuple[str, dict]:
    if not articles:
        return "mixed", {}

    summed: dict[str, float] = {}
    count = 0
    for art in articles:
        topics = art.topics if isinstance(art.topics, dict) else {}
        if not topics:
            continue
        count += 1
        for key, val in topics.items():
            summed[key] = summed.get(key, 0.0) + float(val)

    if count == 0:
        return "mixed", {}

    avg = {k: v / count for k, v in summed.items()}
    max_key = max(avg, key=avg.get)
    if avg[max_key] >= 0.25:
        return max_key, avg
    return "mixed", avg


def _compute_dominant_event_type(articles: list) -> str:
    if not articles:
        return "MIXED"
    types = [art.event_type for art in articles if art.event_type]
    if not types:
        return "MIXED"
    counter = Counter(types)
    most_common, count = counter.most_common(1)[0]
    if count / len(types) > 0.5:
        return most_common
    return "MIXED"


def _merge_entities(articles: list) -> list[dict[str, Any]]:
    tier_map = _build_tier_map()
    merged: dict[str, float] = {}
    for art in articles:
        entities = art.entities if isinstance(art.entities, dict) else {}
        for name, weight in entities.items():
            w = float(weight)
            if name not in merged or w > merged[name]:
                merged[name] = w

    sorted_entities = sorted(merged.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return [
        {"name": name, "weight": weight, "tier": tier_map.get(name)}
        for name, weight in sorted_entities
    ]


def _to_iso(dt) -> str | None:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.astimezone(timezone.utc).isoformat()


@router.get("")
def get_signal_map(
    hours: int = Query(48, ge=1, le=168),
    locale: str = Query("en", pattern="^(en|zh)$"),
    db=Depends(get_db),
):
    # Check response cache (5-min TTL, keyed by hour bucket)
    now = _naive_utc(utcnow())
    bucket = now.strftime("%Y-%m-%dT%H:") + str(now.minute // 5 * 5).zfill(2)
    cache_key = f"api_signal_map:{hours}:{locale}:{bucket}"
    cached = get_cached(cache_key)
    if cached:
        return JSONResponse(content=cached, headers={"Cache-Control": "public, max-age=300"})

    cutoff = now - timedelta(hours=hours)

    # Step 1: Query clusters
    clusters = (
        db.query(Cluster)
        .filter(Cluster.last_seen_at >= cutoff)
        .order_by(Cluster.max_global_score.desc())
        .limit(80)
        .all()
    )

    if not clusters:
        return {"clusters": [], "projection_seed": "", "generated_at": utcnow().isoformat()}

    cluster_ids = [c.id for c in clusters]

    # Step 2: Batch-load member articles
    member_rows = (
        db.query(ClusterMember, Article, RawItem, Source)
        .join(Article, ClusterMember.article_id == Article.id)
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .join(Source, RawItem.source_id == Source.id)
        .options(defer(Article.html), defer(Article.text), defer(Article.embedding), defer(Article.llm_reasoning))
        .filter(ClusterMember.cluster_id.in_(cluster_ids))
        .all()
    )

    # Group by cluster_id
    cluster_articles: dict[str, list[tuple]] = {}
    for cm, article, raw, source in member_rows:
        cluster_articles.setdefault(cm.cluster_id, []).append((article, raw, source))

    # Step 3: Compute per-cluster data
    cluster_data = []
    valid_embeddings = []
    valid_indices = []

    for idx, cluster in enumerate(clusters):
        members = cluster_articles.get(cluster.id, [])
        articles_list = [art for art, _raw, _src in members]

        # Find top article
        top_article = None
        for art, _raw, _src in members:
            if str(art.id) == str(cluster.top_article_id):
                top_article = art
                break
        if top_article is None and articles_list:
            top_article = articles_list[0]

        # Trust aggregation
        if top_article:
            trust_score, trust_label = _compute_cluster_trust(cluster, top_article, now)
        else:
            trust_score = cluster.cluster_trust_score or 0
            trust_label = cluster.cluster_trust_label or "unverified"

        # Dominant topic
        dominant_topic, topic_weights = _compute_dominant_topic(articles_list)

        # Dominant event type
        dominant_event_type = _compute_dominant_event_type(articles_list)

        # Top entities
        entities = _merge_entities(articles_list)

        # Velocity
        first_seen = _naive_utc(cluster.first_seen_at)
        last_seen = _naive_utc(cluster.last_seen_at)
        if first_seen and last_seen:
            age_hours = (last_seen - first_seen).total_seconds() / 3600
        else:
            age_hours = 0.0
        velocity = (cluster.coverage_count or 0) / max(age_hours, 0.1)

        # Sparkline (7 days)
        sparkline = [0] * 7
        today = now.date()
        for _art, raw, _src in members:
            pub = _naive_utc(raw.published_at)
            if pub is None:
                pub = _naive_utc(raw.fetched_at)
            if pub is None:
                continue
            delta_days = (today - pub.date()).days
            if 0 <= delta_days < 7:
                sparkline[6 - delta_days] += 1

        # Build article list sorted by global_score desc
        article_payloads = []
        for art, raw, src in sorted(members, key=lambda m: m[0].global_score or 0, reverse=True):
            article_payloads.append({
                "id": str(art.id),
                "title": raw.title,
                "url": art.final_url,
                "source": src.name,
                "published_at": _to_iso(raw.published_at),
                "global_score": art.global_score or 0,
                "trust_label": art.trust_label,
                "event_type": art.event_type,
                "summary": art.summary,
            })

        # Decode centroid embedding for PCA
        centroid = None
        if cluster.centroid_embedding:
            try:
                centroid = np.frombuffer(cluster.centroid_embedding, dtype=np.float32)
                if centroid.size != 384:
                    centroid = None
            except ValueError:
                centroid = None

        cluster_data.append({
            "cluster": cluster,
            "trust_score": trust_score,
            "trust_label": trust_label,
            "dominant_topic": dominant_topic,
            "topic_weights": topic_weights,
            "dominant_event_type": dominant_event_type,
            "entities": entities,
            "velocity": velocity,
            "sparkline": sparkline,
            "age_hours": age_hours,
            "articles": article_payloads,
            "centroid": centroid,
        })

        if centroid is not None:
            valid_embeddings.append(centroid)
            valid_indices.append(idx)

    # Step 4: Rank by velocity, mark top 5 (velocity >= 1.0) as pulsing
    velocities = [(i, cd["velocity"]) for i, cd in enumerate(cluster_data)]
    velocities.sort(key=lambda x: x[1], reverse=True)
    pulsing_set: set[int] = set()
    for rank, (i, vel) in enumerate(velocities):
        if rank < 5 and vel >= 1.0:
            pulsing_set.add(i)

    # Step 5: PCA projection
    coords = np.zeros((len(cluster_data), 2), dtype=np.float64)
    if valid_embeddings:
        emb_matrix = np.vstack(valid_embeddings)
        projected = _pca_2d(emb_matrix)
        for j, orig_idx in enumerate(valid_indices):
            coords[orig_idx] = projected[j]

    # Step 6: Build response
    result_clusters = []
    for i, cd in enumerate(cluster_data):
        c = cd["cluster"]
        result_clusters.append({
            "id": str(c.id),
            "headline": c.headline,
            "x": float(coords[i][0]),
            "y": float(coords[i][1]),
            "coverage_count": c.coverage_count or 0,
            "sources_count": c.sources_count or 0,
            "max_global_score": c.max_global_score or 0,
            "velocity": cd["velocity"],
            "pulsing": i in pulsing_set,
            "trust_score": cd["trust_score"],
            "trust_label": cd["trust_label"],
            "dominant_topic": cd["dominant_topic"],
            "topic_weights": cd["topic_weights"],
            "dominant_event_type": cd["dominant_event_type"],
            "entities": cd["entities"],
            "sparkline": cd["sparkline"],
            "first_seen_at": _to_iso(c.first_seen_at),
            "last_seen_at": _to_iso(c.last_seen_at),
            "age_hours": cd["age_hours"],
            "articles": cd["articles"],
        })

    projection_seed = hashlib.sha256(
        ",".join(sorted(str(c.id) for c in clusters)).encode()
    ).hexdigest()

    llm = LLMClient()
    translation_status = "ready"
    localized_clusters = result_clusters
    if locale == "zh":
        localized_clusters, translation_status = llm.translate_signal_map_clusters(result_clusters)

    response = {
        "clusters": localized_clusters,
        "projection_seed": projection_seed,
        "generated_at": utcnow().isoformat(),
        "locale": locale,
        "source_locale": "en",
        "translation_status": translation_status,
    }
    set_cached(cache_key, response, ttl=60 * 5)  # 5-min TTL
    return JSONResponse(content=response, headers={"Cache-Control": "public, max-age=300"})


@router.get("/topic-trends")
def get_topic_trends(locale: str = Query("en", pattern="^(en|zh)$"), db=Depends(get_db)):
    now = _naive_utc(utcnow())
    cutoff = now - timedelta(days=7)
    today = now.date()

    # Query all articles from past 7 days
    rows = (
        db.query(Article, RawItem)
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .filter(
            (RawItem.published_at >= cutoff) | (
                RawItem.published_at.is_(None) & (RawItem.fetched_at >= cutoff)
            )
        )
        .all()
    )

    # Initialize daily buckets for each topic
    topic_daily: dict[str, list[float]] = {k: [0.0] * 7 for k in TOPIC_TAGS}

    for article, raw in rows:
        topics = article.topics if isinstance(article.topics, dict) else {}
        pub = _naive_utc(raw.published_at) or _naive_utc(raw.fetched_at)
        if pub is None:
            continue
        delta_days = (today - pub.date()).days
        if delta_days < 0 or delta_days >= 7:
            continue
        bucket_idx = 6 - delta_days  # oldest first
        for topic_key, prob in topics.items():
            if topic_key in topic_daily:
                topic_daily[topic_key][bucket_idx] += float(prob)

    # Build response sorted by total descending
    topic_list = []
    for topic_key, daily in topic_daily.items():
        total = sum(daily)
        topic_list.append({
            "topic": topic_key,
            "label": TOPIC_TAGS[topic_key],
            "daily_intensity": [round(v, 2) for v in daily],
            "total_intensity": round(total, 2),
        })

    topic_list.sort(key=lambda t: t["total_intensity"], reverse=True)

    return {
        "topics": topic_list,
        "generated_at": utcnow().isoformat(),
        "locale": locale,
        "source_locale": "en",
        "translation_status": "ready",
    }
