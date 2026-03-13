from __future__ import annotations

from celery.schedules import crontab

from app.tasks.celery_app import celery_app


celery_app.conf.beat_schedule = {
    "daily-digest": {
        "task": "app.tasks.daily_digest.run_daily_digest",
        "schedule": crontab(hour=6, minute=0),
    },
    "priority-poll": {
        "task": "app.tasks.pipeline.run_priority_poll",
        "schedule": 300.0,
    },
    "normal-poll": {
        "task": "app.tasks.pipeline.run_normal_poll",
        "schedule": 3600.0,
    },
    "arxiv-poll": {
        "task": "app.tasks.pipeline.run_arxiv_poll",
        "schedule": 10800.0,
    },
    "github-poll": {
        "task": "app.tasks.pipeline.run_github_poll",
        "schedule": 21600.0,
    },
    "rebuild-faiss": {
        "task": "app.tasks.pipeline.rebuild_faiss_index",
        "schedule": 1800.0,
    },
    "sitemap-poll": {
        "task": "app.tasks.pipeline.run_sitemap_poll",
        "schedule": 1800.0,
    },
    "gov-api-poll": {
        "task": "app.tasks.pipeline.run_gov_api_poll",
        "schedule": crontab(hour=8, minute=0),
    },
    "twitter-poll": {
        "task": "app.tasks.pipeline.run_twitter_poll",
        "schedule": 10800.0,
    },
    "social-poll": {
        "task": "app.tasks.pipeline.run_social_poll",
        "schedule": 1800.0,
    },
    "urgent-notify": {
        "task": "app.tasks.urgent_monitor.notify_urgent",
        "schedule": 300.0,
    },
    "relationship-inference": {
        "task": "app.tasks.pipeline.run_relationship_inference",
        "schedule": 3600.0,
    },
}
