from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.config import get_settings

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def _require_egress_access(request: Request) -> None:
    settings = get_settings()
    token = (settings.egress_debug_token or "").strip()
    if settings.app_env.lower() == "prod" and not token:
        raise HTTPException(status_code=404, detail="Not found")
    if token and request.headers.get("x-egress-debug-token") != token:
        raise HTTPException(status_code=403, detail="Missing or invalid egress debug token")


@router.post("/refresh")
def refresh():
    from app.tasks.pipeline import run_refresh

    run_refresh()
    return {"status": "ok"}


@router.post("/digest/generate")
def generate_digest():
    """Manually trigger daily digest generation."""
    from app.tasks.daily_digest import run_daily_digest

    run_daily_digest()
    return {"status": "ok"}


@router.get("/egress")
def egress_snapshot(request: Request, limit: int = Query(20, ge=1, le=200)):
    """Return in-memory request/egress diagnostics for the current process."""
    from app.observability.egress import get_egress_metrics_store

    _require_egress_access(request)
    return get_egress_metrics_store().snapshot(limit=limit)


@router.post("/egress/reset")
def reset_egress_snapshot(request: Request):
    """Clear in-memory request/egress diagnostics for the current process."""
    from app.observability.egress import reset_egress_metrics_store

    _require_egress_access(request)
    reset_egress_metrics_store()
    return {"status": "ok"}


@router.get("/egress/postgres")
def pg_egress_snapshot(request: Request, limit: int = Query(30, ge=1, le=200)):
    """Return Postgres wire-level egress diagnostics.

    Shows top queries by bytes, top callers (endpoints/tasks) by bytes,
    and recent query log. Uses SQLAlchemy event hooks to measure actual
    result-set sizes from psycopg3's PGresult.
    """
    from app.observability.pg_egress import get_pg_egress_store

    _require_egress_access(request)
    return get_pg_egress_store().snapshot(limit=limit)


@router.post("/egress/postgres/reset")
def reset_pg_egress_snapshot(request: Request):
    """Clear Postgres egress diagnostics and JSONL log."""
    from app.observability.pg_egress import reset_pg_egress_store

    _require_egress_access(request)
    reset_pg_egress_store()
    return {"status": "ok"}
