from __future__ import annotations

import httpx

from app.common.time import utcnow
from app.config import get_settings
from app.db import session_scope
from app.models import Article, RawItem, Source
from app.tasks.celery_app import celery_app
from sqlalchemy import func


@celery_app.task(name="app.tasks.urgent_monitor.notify_urgent")
def notify_urgent():
    settings = get_settings()
    if not settings.webhook_urgent_url:
        return
    cutoff = utcnow().timestamp() - 6 * 3600
    with session_scope() as session:
        rows = (
            session.query(Article, RawItem, Source)
            .join(RawItem, Article.raw_item_id == RawItem.id)
            .join(Source, RawItem.source_id == Source.id)
            .filter(Article.urgent.is_(True))
            .filter(func.extract("epoch", func.coalesce(RawItem.published_at, RawItem.fetched_at)) >= cutoff)
            .all()
        )
        payload = [
            {
                "title": raw.title,
                "url": article.final_url,
                "source": source.name,
                "global_score": article.global_score,
            }
            for article, raw, source in rows
        ]
        if not payload:
            return
        with httpx.Client(timeout=10) as client:
            client.post(settings.webhook_urgent_url, json={"items": payload})
