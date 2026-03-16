from __future__ import annotations

import json
import time

try:
    import redis
except Exception:  # pragma: no cover - optional dependency
    redis = None

from app.config import get_settings


settings = get_settings()
_memory_cache: dict[str, tuple[float | None, dict]] = {}


def _redis_client():
    if redis is None:
        return None
    if not settings.redis_url or not settings.redis_url.startswith("redis"):
        return None
    try:
        client = redis.Redis.from_url(settings.redis_url)
        client.ping()
        return client
    except Exception:
        return None


def get_cached(key: str):
    client = _redis_client()
    if client is not None:
        value = client.get(key)
        if not value:
            return None
        return json.loads(value)

    entry = _memory_cache.get(key)
    if not entry:
        return None
    expires_at, payload = entry
    if expires_at is not None and time.time() > expires_at:
        _memory_cache.pop(key, None)
        return None
    return payload


def set_cached(key: str, payload: dict, ttl: int = 60 * 60 * 24 * 7):
    client = _redis_client()
    if client is not None:
        client.set(key, json.dumps(payload), ex=ttl)
        return
    expires_at = time.time() + ttl if ttl else None
    _memory_cache[key] = (expires_at, payload)


def delete_cached(key: str):
    client = _redis_client()
    if client is not None:
        client.delete(key)
        return
    _memory_cache.pop(key, None)


def delete_by_prefix(prefix: str):
    client = _redis_client()
    if client is not None:
        for k in client.scan_iter(match=f"{prefix}*"):
            client.delete(k)
        return
    keys_to_delete = [k for k in _memory_cache if k.startswith(prefix)]
    for k in keys_to_delete:
        _memory_cache.pop(k, None)
