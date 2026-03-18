from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.common.time import utcnow

router = APIRouter(prefix="/v1", tags=["health"])


@router.get("/health")
def health():
    return JSONResponse(
        content={"status": "ok", "timestamp": utcnow().isoformat()},
        headers={"Cache-Control": "no-cache, no-store"},
    )
