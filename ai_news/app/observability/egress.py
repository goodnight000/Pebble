from __future__ import annotations

from collections import Counter, deque
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Lock
from time import perf_counter
from typing import Any


@dataclass
class RequestEgressContext:
    path: str
    method: str
    user_agent: str
    cache_hits: int = 0
    cache_misses: int = 0
    cache_sets: int = 0
    cache_keys: list[str] = field(default_factory=list)
    dependency_bytes: int = 0
    dependency_services: Counter[str] = field(default_factory=Counter)
    dependency_targets: list[dict[str, Any]] = field(default_factory=list)


class EgressMetricsStore:
    def __init__(self, recent_limit: int = 200):
        self._recent_limit = recent_limit
        self._entries: deque[dict[str, Any]] = deque(maxlen=recent_limit)
        self._lock = Lock()

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()

    def record(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self._entries.append(entry)

    def snapshot(self, limit: int = 20) -> dict[str, Any]:
        with self._lock:
            entries = list(self._entries)

        total_requests = len(entries)
        total_response_bytes = sum(int(entry.get("response_bytes", 0)) for entry in entries)
        total_dependency_bytes = sum(int(entry.get("dependency_bytes", 0)) for entry in entries)
        dependency_target_totals: Counter[tuple[str, str]] = Counter()

        by_path: dict[str, dict[str, Any]] = {}
        for entry in entries:
            path = entry.get("path") or "unknown"
            aggregate = by_path.setdefault(
                path,
                {
                    "path": path,
                    "method": entry.get("method"),
                    "user_agent": entry.get("user_agent") or "",
                    "requests": 0,
                    "response_bytes": 0,
                    "dependency_bytes": 0,
                    "cache_hits": 0,
                    "cache_misses": 0,
                    "cache_sets": 0,
                    "duration_ms_total": 0.0,
                    "dependency_services": Counter(),
                },
            )
            aggregate["requests"] += 1
            aggregate["response_bytes"] += int(entry.get("response_bytes", 0))
            aggregate["dependency_bytes"] += int(entry.get("dependency_bytes", 0))
            aggregate["cache_hits"] += int(entry.get("cache_hits", 0))
            aggregate["cache_misses"] += int(entry.get("cache_misses", 0))
            aggregate["cache_sets"] += int(entry.get("cache_sets", 0))
            aggregate["duration_ms_total"] += float(entry.get("duration_ms", 0.0))
            aggregate["user_agent"] = entry.get("user_agent") or aggregate["user_agent"]
            aggregate["dependency_services"].update(entry.get("dependency_services", {}))
            for target in entry.get("dependency_targets", []):
                service = str(target.get("service") or "unknown")
                target_name = str(target.get("target") or "unknown")
                dependency_target_totals[(service, target_name)] += int(target.get("bytes", 0))

        top_paths = sorted(
            by_path.values(),
            key=lambda item: (item["response_bytes"] + item["dependency_bytes"], item["requests"]),
            reverse=True,
        )[:limit]

        for item in top_paths:
            item["avg_response_bytes"] = round(item["response_bytes"] / max(item["requests"], 1), 2)
            item["avg_duration_ms"] = round(item["duration_ms_total"] / max(item["requests"], 1), 2)
            item["dependency_services"] = dict(item["dependency_services"])
            item.pop("duration_ms_total", None)

        recent = list(reversed(entries[-limit:]))
        top_dependency_targets = [
            {
                "service": service,
                "target": target,
                "bytes": bytes_count,
            }
            for (service, target), bytes_count in dependency_target_totals.most_common(limit)
        ]

        return {
            "summary": {
                "total_requests": total_requests,
                "total_response_bytes": total_response_bytes,
                "total_dependency_bytes": total_dependency_bytes,
                "recent_window_size": len(entries),
                "cache_metrics_scope": (
                    "cache_hits/cache_misses/cache_sets are counts of internal cache operations "
                    "observed during each request, not endpoint-level response cache outcomes."
                ),
            },
            "top_paths": top_paths,
            "top_dependency_targets": top_dependency_targets,
            "recent": recent,
        }


_request_context: ContextVar[RequestEgressContext | None] = ContextVar("request_egress_context", default=None)
_store = EgressMetricsStore()


def get_egress_metrics_store() -> EgressMetricsStore:
    return _store


def reset_egress_metrics_store() -> None:
    _store.reset()


def note_cache_event(event: str, key: str) -> None:
    context = _request_context.get()
    if context is None:
        return
    if event == "hit":
        context.cache_hits += 1
    elif event == "miss":
        context.cache_misses += 1
    elif event == "set":
        context.cache_sets += 1
    if len(context.cache_keys) < 10:
        context.cache_keys.append(key)


def note_dependency_egress(*, service: str, bytes_count: int, target: str | None = None) -> None:
    context = _request_context.get()
    if context is None:
        return
    safe_bytes = max(int(bytes_count), 0)
    context.dependency_bytes += safe_bytes
    context.dependency_services[service] += safe_bytes
    if target and len(context.dependency_targets) < 10:
        context.dependency_targets.append({"service": service, "target": target, "bytes": safe_bytes})


class EgressMetricsMiddleware:
    def __init__(self, app, store: EgressMetricsStore | None = None):
        self.app = app
        self.store = store or get_egress_metrics_store()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        status_code = 500
        response_bytes = 0
        start = perf_counter()
        headers = {
            key.decode("latin-1"): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        context = RequestEgressContext(
            path=scope.get("path") or "",
            method=scope.get("method") or "GET",
            user_agent=headers.get("user-agent", ""),
        )
        token = _request_context.set(context)

        async def send_wrapper(message):
            nonlocal response_bytes, status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            elif message["type"] == "http.response.body":
                response_bytes += len(message.get("body", b"") or b"")
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((perf_counter() - start) * 1000, 3)
            self.store.record(
                {
                    "path": context.path,
                    "method": context.method,
                    "user_agent": context.user_agent,
                    "status_code": status_code,
                    "response_bytes": response_bytes,
                    "duration_ms": duration_ms,
                    "cache_hits": context.cache_hits,
                    "cache_misses": context.cache_misses,
                    "cache_sets": context.cache_sets,
                    "cache_keys": list(context.cache_keys),
                    "dependency_bytes": context.dependency_bytes,
                    "dependency_services": dict(context.dependency_services),
                    "dependency_targets": list(context.dependency_targets),
                }
            )
            _request_context.reset(token)
