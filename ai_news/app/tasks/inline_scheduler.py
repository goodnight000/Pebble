from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.tasks.daily_digest import generate_weekly_artifact, run_daily_digest
from app.tasks.pipeline import (
    rebuild_faiss_index,
    run_arxiv_poll,
    run_entity_resolution,
    run_github_poll,
    run_gov_api_poll,
    run_normal_poll,
    run_priority_poll,
    run_relationship_inference,
    run_sitemap_poll,
    run_social_poll,
    run_twitter_poll,
)
from app.tasks.urgent_monitor import notify_urgent


async def _run_periodic(name: str, interval_seconds: float, fn, initial_delay: float = 0) -> None:
    if initial_delay > 0:
        await asyncio.sleep(initial_delay)
    while True:
        try:
            def _wrapped():
                from app.observability.pg_egress import clear_task_context, set_task_context

                set_task_context(name)
                try:
                    fn()
                finally:
                    clear_task_context()

            await asyncio.to_thread(_wrapped)
        except Exception as exc:
            print(f"[inline-scheduler] {name} failed: {exc}")
        await asyncio.sleep(interval_seconds)


def _digest_exists_for_today() -> bool:
    """Check if a daily digest row already exists for today (UTC)."""
    from sqlalchemy import func as sa_func

    from app.db import session_scope
    from app.models import DailyDigest

    today = datetime.now(timezone.utc).date()
    settings = get_settings()
    with session_scope() as session:
        count = (
            session.query(DailyDigest)
            .filter(
                DailyDigest.user_id == settings.public_user_id,
                sa_func.date(DailyDigest.date) == today,
            )
            .count()
        )
        return count > 0


async def _run_daily(name: str, hour_utc: int, minute_utc: int, fn, catch_up: bool = False) -> None:
    def _wrapped():
        from app.observability.pg_egress import clear_task_context, set_task_context

        set_task_context(name)
        try:
            fn()
        finally:
            clear_task_context()

    # If catch_up is enabled and scheduled time already passed today, run immediately
    if catch_up:
        now = datetime.now(timezone.utc)
        target_today = now.replace(hour=hour_utc, minute=minute_utc, second=0, microsecond=0)
        if now > target_today:
            try:
                needs_run = not _digest_exists_for_today()
            except Exception:
                needs_run = True
            if needs_run:
                print(f"[inline-scheduler] {name} catch-up: scheduled time already passed, running now")
                try:
                    await asyncio.to_thread(_wrapped)
                except Exception as exc:
                    print(f"[inline-scheduler] {name} catch-up failed: {exc}")

    while True:
        now = datetime.now(timezone.utc)
        target = now.replace(hour=hour_utc, minute=minute_utc, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        try:
            await asyncio.to_thread(_wrapped)
        except Exception as exc:
            print(f"[inline-scheduler] {name} failed: {exc}")


def maybe_start_inline_scheduler() -> None:
    settings = get_settings()
    if settings.app_env.lower() != "dev":
        return
    # If Celery is configured with a real broker, prefer beat+worker.
    if settings.celery_broker_url and not settings.celery_broker_url.startswith("memory://"):
        return
    # Skip scheduler if DISABLE_SCHEDULER env var is set (useful for testing).
    import os
    if os.environ.get("DISABLE_SCHEDULER"):
        print("[inline-scheduler] Disabled via DISABLE_SCHEDULER env var")
        return

    loop = asyncio.get_event_loop()
    # Stagger startup: let the API settle before background tasks begin,
    # and avoid multiple polls competing for the SQLite write lock.
    loop.create_task(_run_periodic("priority-poll", 300.0, run_priority_poll, initial_delay=30))
    loop.create_task(_run_periodic("normal-poll", 3600.0, run_normal_poll, initial_delay=60))
    loop.create_task(_run_periodic("arxiv-poll", 10800.0, run_arxiv_poll, initial_delay=90))
    loop.create_task(_run_periodic("github-poll", 21600.0, run_github_poll, initial_delay=120))
    loop.create_task(_run_periodic("sitemap-poll", 3600.0, run_sitemap_poll, initial_delay=75))
    loop.create_task(_run_periodic("twitter-poll", 10800.0, run_twitter_poll, initial_delay=105))
    loop.create_task(_run_periodic("social-poll", 3600.0, run_social_poll, initial_delay=135))
    loop.create_task(_run_daily("gov-api-poll", 8, 0, run_gov_api_poll))
    loop.create_task(_run_periodic("rebuild-faiss", 21600.0, rebuild_faiss_index, initial_delay=15))
    loop.create_task(_run_periodic("urgent-notify", 300.0, notify_urgent, initial_delay=10))
    loop.create_task(_run_periodic("entity-resolution", 21600.0, run_entity_resolution, initial_delay=180))
    loop.create_task(_run_periodic("relationship-inference", 10800.0, run_relationship_inference, initial_delay=210))
    loop.create_task(_run_periodic("weekly-artifact", 1800.0, generate_weekly_artifact, initial_delay=45))
    loop.create_task(_run_daily("daily-digest", 6, 0, run_daily_digest, catch_up=True))
