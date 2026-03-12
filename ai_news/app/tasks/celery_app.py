from __future__ import annotations

from celery import Celery

from app.config import get_settings


settings = get_settings()

celery_app = Celery(
    "ai_news",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.timezone = "America/New_York"
celery_app.conf.task_routes = {
    "app.tasks.pipeline.*": {"queue": "pipeline"},
}

celery_app.autodiscover_tasks(["app.tasks"])

# Load beat schedules
from app.tasks import schedules  # noqa: E402,F401
