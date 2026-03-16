from __future__ import annotations

import argparse
from datetime import timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.common.time import utcnow
from app.db import session_scope
from app.models import Article, Cluster, ClusterMember, RawItem, Source
from app.scoring.llm_judge import compute_final_score
from app.scoring.signals import is_official_source
from app.scoring.time_decay import compute_urgent
from app.scoring.trust import estimate_independent_sources
from app.scoring.verification import (
    VerificationInputs,
    compute_verification,
    legacy_trust_components,
    legacy_trust_label_for_state,
)


def refresh_article_verification_fields(session: Session, article: Article, raw: RawItem, source: Source) -> Article:
    member = session.query(ClusterMember).filter(ClusterMember.article_id == article.id).first()
    cluster = session.query(Cluster).filter(Cluster.id == member.cluster_id).first() if member else None

    cluster_articles: list[Article] = []
    if cluster:
        rows = (
            session.query(Article, Source.name)
            .join(ClusterMember, ClusterMember.article_id == Article.id)
            .join(RawItem, Article.raw_item_id == RawItem.id)
            .join(Source, RawItem.source_id == Source.id)
            .filter(ClusterMember.cluster_id == cluster.id)
            .all()
        )
        cluster_articles = [cluster_article for cluster_article, _source_name in rows]

    independent_count = estimate_independent_sources(cluster_articles) if cluster_articles else 1
    primary_entity = max(article.entities, key=article.entities.get) if article.entities else None

    verification = compute_verification(
        VerificationInputs(
            cluster_articles=cluster_articles,
            source_authority=source.authority,
            text=article.text,
            url=article.final_url,
            primary_entity=primary_entity,
            independent_sources=independent_count,
            event_type=article.event_type or "OTHER",
            source_kind=source.kind,
            source_name=source.name,
            created_at=article.created_at,
        )
    )
    trust_label = legacy_trust_label_for_state(
        verification.verification_state,
        verification.verification_confidence,
    )
    trust_components = legacy_trust_components(verification, article.text)

    article.independent_sources = independent_count
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
    article.final_score = compute_final_score(
        article.global_score or 0.0,
        article.llm_score,
        confirmation_level=article.confirmation_level,
        trust_label=article.trust_label,
        verification_state=article.verification_state,
        verification_confidence=article.verification_confidence,
        update_status=article.update_status,
    )

    now = utcnow().replace(tzinfo=None)
    ts = raw.published_at or raw.fetched_at or article.created_at
    if ts and ts.tzinfo is not None:
        ts = ts.replace(tzinfo=None)
    age_hours = max(0.1, (now - ts).total_seconds() / 3600) if ts else 1.0
    article.urgent = compute_urgent(
        article.final_score or 0.0,
        age_hours,
        independent_count,
        is_official_source(article.final_url),
        article.trust_label,
        verification_state=article.verification_state,
        verification_confidence=article.verification_confidence,
    )

    if cluster:
        cluster.independent_sources_count = independent_count
        cluster.has_official_confirmation = verification.verification_state == "official_statement"
        cluster.cluster_trust_score = verification.verification_confidence
        cluster.cluster_trust_label = trust_label
        cluster.cluster_verification_state = verification.verification_state
        cluster.cluster_freshness_state = verification.freshness_state
        cluster.cluster_verification_confidence = verification.verification_confidence
        cluster.cluster_verification_signals = verification.verification_signals

    return article


def backfill_verification_session(
    session: Session,
    *,
    window_hours: int = 72,
    batch_size: int = 200,
    dry_run: bool = False,
    force_all: bool = False,
) -> dict[str, Any]:
    cutoff = utcnow() - timedelta(hours=window_hours)
    query = (
        session.query(Article, RawItem, Source)
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .join(Source, RawItem.source_id == Source.id)
        .filter(func.coalesce(RawItem.fetched_at, Article.created_at) >= cutoff)
        .order_by(func.coalesce(RawItem.fetched_at, Article.created_at).desc())
    )
    if not force_all:
        query = query.filter(Article.verification_state.is_(None))

    rows = query.limit(batch_size).all()
    updated = 0

    for article, raw, source in rows:
        if dry_run:
            continue

        refresh_article_verification_fields(session, article, raw, source)
        updated += 1

    return {
        "candidates": len(rows),
        "updated": updated,
        "dry_run": dry_run,
        "window_hours": window_hours,
        "batch_size": batch_size,
        "force_all": force_all,
    }


def backfill_verification(
    *,
    window_hours: int = 72,
    batch_size: int = 200,
    dry_run: bool = False,
    force_all: bool = False,
) -> dict[str, Any]:
    with session_scope() as session:
        return backfill_verification_session(
            session,
            window_hours=window_hours,
            batch_size=batch_size,
            dry_run=dry_run,
            force_all=force_all,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill verification fields for recent articles.")
    parser.add_argument("--window-hours", type=int, default=72)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-all", action="store_true")
    args = parser.parse_args()

    result = backfill_verification(
        window_hours=args.window_hours,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        force_all=args.force_all,
    )
    print(result)


if __name__ == "__main__":
    main()
