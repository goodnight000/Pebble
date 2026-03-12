from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.post("/refresh")
def refresh():
    from app.tasks.pipeline import run_refresh

    run_refresh()
    return {"status": "ok"}
