from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.db import get_db
from app.models import User, UserEntityWeight, UserPref, UserSourceWeight, UserTopicWeight

router = APIRouter(prefix="/v1/users", tags=["users"])


class UserPrefUpdate(BaseModel):
    min_show_score: float | None = None
    min_urgent_score: float | None = None
    serendipity: float | None = None
    prefer_official_sources: bool | None = None
    prefer_research: float | None = None
    prefer_startups: float | None = None
    prefer_hardware: float | None = None
    prefer_open_source: float | None = None
    prefer_policy_safety: float | None = None
    prefer_tutorials_tools: float | None = None
    recency_bias: float | None = None
    credibility_bias: float | None = None
    hype_tolerance: float | None = None


class WeightUpdate(BaseModel):
    key: str
    weight: float | None = None
    blocked: bool | None = None


@router.post("")
def create_user(db=Depends(get_db)):
    user = User()
    db.add(user)
    db.flush()
    settings = get_settings()
    min_show = 30 if settings.app_env.lower() == "dev" else 55
    prefs = UserPref(user_id=user.id, min_show_score=min_show)
    db.add(prefs)
    db.commit()
    return {"id": str(user.id)}


@router.put("/{user_id}/prefs")
def update_prefs(user_id: str, payload: UserPrefUpdate, db=Depends(get_db)):
    prefs = db.query(UserPref).filter(UserPref.user_id == user_id).first()
    if not prefs:
        raise HTTPException(status_code=404, detail="user not found")
    for key, value in payload.dict(exclude_none=True).items():
        setattr(prefs, key, value)
    db.commit()
    return {"status": "ok"}


@router.put("/{user_id}/topics")
def update_topics(user_id: str, payload: List[WeightUpdate], db=Depends(get_db)):
    for item in payload:
        row = (
            db.query(UserTopicWeight)
            .filter(UserTopicWeight.user_id == user_id, UserTopicWeight.topic == item.key)
            .first()
        )
        if not row:
            row = UserTopicWeight(user_id=user_id, topic=item.key)
            db.add(row)
        if item.weight is not None:
            row.weight = item.weight
        if item.blocked is not None:
            row.blocked = item.blocked
    db.commit()
    return {"status": "ok"}


@router.put("/{user_id}/entities")
def update_entities(user_id: str, payload: List[WeightUpdate], db=Depends(get_db)):
    for item in payload:
        row = (
            db.query(UserEntityWeight)
            .filter(UserEntityWeight.user_id == user_id, UserEntityWeight.entity == item.key)
            .first()
        )
        if not row:
            row = UserEntityWeight(user_id=user_id, entity=item.key)
            db.add(row)
        if item.weight is not None:
            row.weight = item.weight
        if item.blocked is not None:
            row.blocked = item.blocked
    db.commit()
    return {"status": "ok"}


@router.put("/{user_id}/sources")
def update_sources(user_id: str, payload: List[WeightUpdate], db=Depends(get_db)):
    for item in payload:
        row = (
            db.query(UserSourceWeight)
            .filter(UserSourceWeight.user_id == user_id, UserSourceWeight.source_id == item.key)
            .first()
        )
        if not row:
            row = UserSourceWeight(user_id=user_id, source_id=item.key)
            db.add(row)
        if item.weight is not None:
            row.weight = item.weight
        if item.blocked is not None:
            row.blocked = item.blocked
    db.commit()
    return {"status": "ok"}
