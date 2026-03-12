from __future__ import annotations

from fastapi import APIRouter

from app.common.time import utcnow

router = APIRouter(prefix="/v1", tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok", "timestamp": utcnow().isoformat()}
