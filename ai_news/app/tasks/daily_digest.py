from __future__ import annotations

import re
from datetime import timedelta

import numpy as np

from app.common.mmr import mmr_select
from app.common.time import utcnow
from app.config import get_settings
from app.db import session_scope
from app.services.digest_storage import build_digest_artifact, store_digest_artifact
from app.services.realtime_events import build_digest_refresh_event, publish_realtime_event
from app.models import Article, Cluster, ClusterMember, DailyDigest, EntityCanonMap, RawItem, Source, User, UserEntityWeight, UserPref, UserSourceWeight, UserTopicWeight
from app.scoring.signals import log_norm
from app.scoring.time_decay import rank_score as compute_rank_score
from app.scoring.user_score import compute_user_score
from app.tasks.celery_app import celery_app
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import defer


FETCHED_AT_FALLBACK_KINDS = {"hn", "reddit", "twitter", "mastodon", "bluesky", "github", "github_trending", "congress"}
FETCHED_AT_PREFERRED_KINDS = {"github", "github_trending"}


def _warm_digest_cache():
    """Pre-populate the digest/today API cache after generation."""
    import logging
    log = logging.getLogger(__name__)
    try:
        from urllib.request import urlopen, Request
        req = Request("http://127.0.0.1:8000/api/digest/today?locale=en", headers={"Accept": "application/json"})
        resp = urlopen(req, timeout=60)
        if resp.status == 200:
            log.info("Warmed digest/today cache successfully")
        else:
            log.warning("Warming digest/today cache returned status %s", resp.status)
    except Exception as exc:
        log.warning("Failed to warm digest/today cache: %s", exc)


def _event_time(raw, source):
    if source.kind in FETCHED_AT_PREFERRED_KINDS:
        ts = raw.fetched_at
    else:
        ts = raw.published_at
        if ts is None and source.kind in FETCHED_AT_FALLBACK_KINDS:
            ts = raw.fetched_at
    return ts


def _load_user_context(db, user_id: str):
    prefs = db.query(UserPref).filter(UserPref.user_id == user_id).first()
    if not prefs:
        prefs = UserPref(user_id=user_id)
        db.add(prefs)
        db.flush()
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


def _build_today_for_user(db, user_id: str) -> list[dict]:
    now = utcnow().replace(tzinfo=None)  # naive UTC to match DB timestamps
    cutoff = now - timedelta(hours=24)
    max_age_hours = 24.0
    prefs, entity_weights, topic_weights, source_weights = _load_user_context(db, user_id)

    rows = (
        db.query(Article, RawItem, Source, Cluster)
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .join(Source, RawItem.source_id == Source.id)
        .outerjoin(ClusterMember, ClusterMember.article_id == Article.id)
        .outerjoin(Cluster, Cluster.id == ClusterMember.cluster_id)
        .filter(
            or_(
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
        )
        .all()
    )

    items = []
    for article, raw, source, cluster in rows:
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
        ts = _event_time(raw, source)
        if ts is None:
            continue
        ts_naive = ts.replace(tzinfo=None) if ts.tzinfo else ts
        age_hours = (now - ts_naive).total_seconds() / 3600
        if age_hours < 0 or age_hours > max_age_hours:
            continue
        # Per-event-type decay with user recency bias
        adjusted_score = user_score / max(prefs.recency_bias, 0.01)
        rs = compute_rank_score(adjusted_score, article.event_type, age_hours, content_type=article.content_type)
        payload = {
            "id": str(article.id),
            "rank_score": rs,
            "global_score": base_score,
            "content_type": article.content_type,
            "embedding": np.frombuffer(article.embedding, dtype=np.float32),
        }
        items.append(payload)

    items_sorted = sorted(items, key=lambda x: x["rank_score"], reverse=True)
    embeddings_arr = (
        np.vstack([item["embedding"] for item in items_sorted])
        if items_sorted
        else np.zeros((0, 384), dtype=np.float32)
    )
    selected = mmr_select(items_sorted, embeddings_arr, lambda_mult=0.80, k=30, score_key="rank_score")

    if prefs.serendipity > 0 and items_sorted:
        n = max(1, round(prefs.serendipity * len(selected)))
        selected_ids = {item["id"] for item in selected}
        global_candidates = [item for item in items_sorted if item["global_score"] >= 75 and item["id"] not in selected_ids]
        selected.extend(global_candidates[:n])

    return [{"id": item["id"], "content_type": item.get("content_type", "news")} for item in selected[:30]]


def _refresh_entity_resolution(session) -> None:
    """Gather entities from recent articles, resolve aliases, cache & persist."""
    from app.features.entity_resolution import resolve_entities, update_entity_resolution_cache

    cutoff = utcnow().replace(tzinfo=None) - timedelta(days=7)
    recent_articles = (
        session.query(Article)
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .filter(
            or_(
                RawItem.published_at >= cutoff,
                and_(RawItem.published_at.is_(None), RawItem.fetched_at >= cutoff),
            )
        )
        .all()
    )

    all_entity_names: set[str] = set()
    for art in recent_articles:
        if isinstance(art.entities, dict):
            all_entity_names.update(art.entities.keys())

    if not all_entity_names:
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


def _render_longform_html(digest_json: dict) -> str:
    """Convert the structured longform digest JSON into rendered HTML."""
    parts: list[str] = []
    parts.append(f'<h1 class="digest-title">{_escape(digest_json.get("title", ""))}</h1>')
    subtitle = digest_json.get("subtitle", "")
    if subtitle:
        parts.append(f'<p class="digest-subtitle">{_escape(subtitle)}</p>')

    for section in digest_json.get("sections", []):
        heading = section.get("heading", "")
        body = section.get("body", "")
        if heading:
            parts.append(f'<h2 class="digest-section-heading">{_escape(heading)}</h2>')
        if body:
            parts.append(_markdown_to_html(body))

    sign_off = digest_json.get("sign_off", "")
    if sign_off:
        parts.append(f'<p class="digest-sign-off">{_md_inline(sign_off)}</p>')

    return "\n".join(parts)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _md_inline(text: str) -> str:
    """Convert inline markdown (bold, links) to HTML."""
    text = _escape(text)
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Links — only allow http/https URLs
    def _safe_link(m):
        label, url = m.group(1), m.group(2)
        if not url.startswith(('http://', 'https://')):
            return label
        return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _safe_link, text)
    return text


def _markdown_to_html(md: str) -> str:
    """Minimal markdown-to-HTML: paragraphs, bold, links, bullet lists."""
    lines = md.strip().split("\n")
    html_parts: list[str] = []
    in_list = False
    paragraph_lines: list[str] = []

    def flush_paragraph():
        nonlocal paragraph_lines
        if paragraph_lines:
            text = " ".join(paragraph_lines)
            html_parts.append(f"<p>{_md_inline(text)}</p>")
            paragraph_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            flush_paragraph()
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{_md_inline(stripped[2:])}</li>")
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            paragraph_lines.append(stripped)

    flush_paragraph()
    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)


@celery_app.task(name="app.tasks.daily_digest.run_daily_digest")
def run_daily_digest():
    from app.llm.client import LLMClient

    pending_realtime_events: list[dict] = []
    with session_scope() as session:
        # Refresh entity resolution before building per-user digests
        try:
            _refresh_entity_resolution(session)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Entity resolution during digest failed: %s", exc)

        users = session.query(User).all()
        now = utcnow()
        llm = LLMClient()
        settings = get_settings()

        for user in users:
            all_items = _build_today_for_user(session, str(user.id))
            all_ids = [item["id"] for item in all_items]

            # Group by content_type
            groups: dict[str, list] = {"all": all_items, "news": [], "research": [], "github": []}
            for item in all_items:
                ct = item.get("content_type", "news")
                if ct in groups:
                    groups[ct].append(item)

            for ct, items in groups.items():
                article_ids = [item["id"] for item in items] if ct != "all" else all_ids

                # Build lightweight payload for LLM (title + summary only)
                llm_items = []
                if items:
                    art_ids = [item["id"] for item in items]
                    articles = session.query(Article, RawItem).join(RawItem, Article.raw_item_id == RawItem.id).filter(Article.id.in_(art_ids)).all()
                    for article, raw in articles:
                        llm_items.append({
                            "title": raw.title,
                            "summary": article.summary or raw.snippet or (article.text[:240] if article.text else ""),
                        })

                copy = llm.generate_section_digest(llm_items, content_type=ct)

                # Upsert: check for existing digest for this user/date/content_type
                existing = (
                    session.query(DailyDigest)
                    .options(defer(DailyDigest.longform_html))
                    .filter(
                        DailyDigest.user_id == user.id,
                        func.date(DailyDigest.date) == now.date(),
                        DailyDigest.content_type == ct,
                    )
                    .first()
                )
                if existing:
                    existing.article_ids = article_ids
                    existing.headline = copy.get("headline")
                    existing.executive_summary = copy.get("executiveSummary")
                    existing.llm_authored = bool(copy.get("llmAuthored"))
                    target_digest = existing
                else:
                    digest = DailyDigest(
                        user_id=user.id,
                        date=now,
                        article_ids=article_ids,
                        content_type=ct,
                        headline=copy.get("headline"),
                        executive_summary=copy.get("executiveSummary"),
                        llm_authored=bool(copy.get("llmAuthored")),
                    )
                    session.add(digest)
                    target_digest = digest

                if settings.supabase_storage_enabled:
                    artifact = build_digest_artifact(
                        user_id=str(user.id),
                        date=now,
                        content_type=ct,
                        article_ids=article_ids,
                        headline=copy.get("headline"),
                        executive_summary=copy.get("executiveSummary"),
                        llm_authored=bool(copy.get("llmAuthored")),
                        settings=settings,
                    )
                    storage_metadata = store_digest_artifact(artifact, settings=settings)
                    target_digest.storage_bucket = storage_metadata["bucket"]
                    target_digest.storage_path = storage_metadata["path"]

                if settings.supabase_realtime_enabled:
                    pending_realtime_events.append(
                        build_digest_refresh_event(
                            user_id=str(user.id),
                            digest_date=now.date().isoformat(),
                            content_type=ct,
                            headline=copy.get("headline"),
                            storage_path=target_digest.storage_path,
                        )
                    )

            # ── Generate longform digest ──
            longform_articles = []
            if all_items:
                art_ids = [item["id"] for item in all_items]
                articles_with_raw = (
                    session.query(Article, RawItem, Source)
                    .join(RawItem, Article.raw_item_id == RawItem.id)
                    .join(Source, RawItem.source_id == Source.id)
                    .filter(Article.id.in_(art_ids))
                    .all()
                )
                for article, raw, source in articles_with_raw:
                    longform_articles.append({
                        "title": raw.title,
                        "summary": article.summary or raw.snippet or (article.text[:400] if article.text else ""),
                        "source_name": source.name,
                        "url": article.final_url,
                        "category": article.event_type,
                        "content_type": article.content_type,
                        "significance_score": article.final_score or article.global_score or 0,
                    })
                # Sort by significance so LLM sees most important first
                longform_articles.sort(key=lambda x: x["significance_score"], reverse=True)

            longform_result = llm.generate_longform_digest(longform_articles[:30])
            if longform_result:
                longform_html = _render_longform_html(longform_result)

                existing_lf = (
                    session.query(DailyDigest)
                    .filter(
                        DailyDigest.user_id == user.id,
                        func.date(DailyDigest.date) == now.date(),
                        DailyDigest.content_type == "longform",
                    )
                    .first()
                )
                if existing_lf:
                    existing_lf.article_ids = all_ids
                    existing_lf.headline = longform_result.get("title")
                    existing_lf.executive_summary = longform_result.get("subtitle")
                    existing_lf.longform_html = longform_html
                    existing_lf.llm_authored = True
                else:
                    lf_digest = DailyDigest(
                        user_id=user.id,
                        date=now,
                        article_ids=all_ids,
                        content_type="longform",
                        headline=longform_result.get("title"),
                        executive_summary=longform_result.get("subtitle"),
                        longform_html=longform_html,
                        llm_authored=True,
                    )
                    session.add(lf_digest)

    # Invalidate digest response caches so the next API request picks up fresh data
    from app.llm.cache import delete_by_prefix
    delete_by_prefix("api_digest_today:")
    delete_by_prefix("api_digest_daily:")
    delete_by_prefix("api_digest_archive:")
    delete_by_prefix("api_news_weekly:")

    for payload in pending_realtime_events:
        publish_realtime_event("digests", "digest_refresh", payload)

    # Warm the API cache so the first user request is instant
    _warm_digest_cache()
