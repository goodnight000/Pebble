from __future__ import annotations

from fastapi import FastAPI

from app.api.routes_admin import router as admin_router
from app.api.routes_compat import router as compat_router
from app.api.routes_health import router as health_router
from app.api.routes_news import router as news_router
from app.api.routes_signal_map import router as signal_map_router
from app.api.routes_users import router as users_router
from app.config import get_settings
from app.db import session_scope
from app.models import User, UserPref
from app.scripts.seed_sources import seed_sources
from app.tasks.inline_scheduler import maybe_start_inline_scheduler


app = FastAPI(title="AI News API")

app.include_router(compat_router)
app.include_router(news_router)
app.include_router(users_router)
app.include_router(admin_router)
app.include_router(health_router)
app.include_router(signal_map_router)


@app.on_event("startup")
def on_startup():
    bootstrap_application()


def ensure_public_user_and_prefs(session, settings) -> None:
    user = session.query(User).filter(User.id == settings.public_user_id).first()
    if not user:
        user = User(id=settings.public_user_id)
        session.add(user)
        session.flush()
    prefs = session.query(UserPref).filter(UserPref.user_id == user.id).first()
    if not prefs:
        min_show = 30 if settings.app_env.lower() == "dev" else 55
        session.add(UserPref(user_id=user.id, min_show_score=min_show))


def _load_entity_resolution_cache() -> None:
    """Load the latest EntityCanonMap from DB into the in-memory cache."""
    from app.features.entity_resolution import EntityResolutionResult, update_entity_resolution_cache
    from app.models import EntityCanonMap

    with session_scope() as session:
        latest = session.query(EntityCanonMap).order_by(EntityCanonMap.generated_at.desc()).first()
        if latest:
            update_entity_resolution_cache(EntityResolutionResult(
                canon_map=latest.canon_map,
                clusters=[],  # clusters not persisted, only canon_map matters
                generated_at=latest.generated_at.isoformat() if latest.generated_at else "",
            ))


def bootstrap_application() -> None:
    seed_sources()
    settings = get_settings()
    with session_scope() as session:
        ensure_public_user_and_prefs(session, settings)
    try:
        _load_entity_resolution_cache()
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Failed to load entity resolution cache on startup", exc_info=True)
    maybe_start_inline_scheduler()
