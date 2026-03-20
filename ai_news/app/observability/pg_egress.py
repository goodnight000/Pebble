"""Postgres wire-level egress tracking via SQLAlchemy event listeners.

Instruments every SELECT query to measure actual data pulled from Supabase
Postgres, logs to JSONL for offline analysis, and exposes an in-memory
ring buffer via admin endpoint.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import deque
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context var for background-task caller correlation
# ---------------------------------------------------------------------------
_task_context: ContextVar[str | None] = ContextVar("pg_egress_task_context", default=None)


def set_task_context(task_name: str) -> None:
    """Set the current background task name for egress correlation."""
    _task_context.set(task_name)


def clear_task_context() -> None:
    _task_context.set(None)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class PgQueryRecord:
    timestamp: str
    sql_fingerprint: str
    sql_hash: str
    row_count: int
    col_count: int
    estimated_bytes: int
    duration_ms: float
    caller: str  # endpoint path or task name
    caller_type: str  # "http" | "task" | "startup" | "unknown"
    columns: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SQL fingerprinting
# ---------------------------------------------------------------------------
def _fingerprint_sql(sql: str) -> str:
    """Normalise SQL for grouping: collapse whitespace, mask literals."""
    s = re.sub(r"\s+", " ", sql.strip())
    # mask string literals
    s = re.sub(r"'[^']*'", "'?'", s)
    # mask numeric literals (standalone numbers, not inside identifiers)
    s = re.sub(r"\b\d+\b", "?", s)
    # collapse IN-lists
    s = re.sub(r"\(\?\s*(?:,\s*\?)*\)", "(?...)", s)
    return s[:500]


def _hash_sql(fingerprint: str) -> str:
    return hashlib.md5(fingerprint.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Wire-byte estimation from psycopg3 PGresult
# ---------------------------------------------------------------------------
def _estimate_bytes_from_pgresult(pgresult: Any, sample_limit: int = 10) -> int:
    """Sample rows from the raw libpq result to estimate wire bytes."""
    try:
        ntuples = pgresult.ntuples
        nfields = pgresult.nfields
        if ntuples == 0 or nfields == 0:
            return 0

        sample_count = min(ntuples, sample_limit)
        sample_bytes = 0
        for row in range(sample_count):
            for col in range(nfields):
                val = pgresult.get_value(row, col)
                if val is not None:
                    sample_bytes += len(val)

        if ntuples <= sample_limit:
            return sample_bytes
        # extrapolate from sample
        avg_per_row = sample_bytes / sample_count
        return int(avg_per_row * ntuples)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Caller detection (HTTP request vs background task)
# ---------------------------------------------------------------------------
def _get_caller() -> tuple[str, str]:
    task = _task_context.get()
    if task:
        return task, "task"
    try:
        from app.observability.egress import _request_context

        ctx = _request_context.get()
        if ctx:
            return f"{ctx.method} {ctx.path}", "http"
    except Exception:
        pass
    return "unknown", "unknown"


# ---------------------------------------------------------------------------
# In-memory store with JSONL persistence
# ---------------------------------------------------------------------------
class PgEgressStore:
    """Ring buffer of recent Postgres query records with aggregation."""

    def __init__(self, recent_limit: int = 500):
        self._entries: deque[PgQueryRecord] = deque(maxlen=recent_limit)
        self._lock = Lock()
        self._total_bytes: int = 0
        self._total_queries: int = 0
        self._log_path: Path | None = None

    def set_log_path(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._log_path = path

    def record(self, entry: PgQueryRecord) -> None:
        with self._lock:
            self._entries.append(entry)
            self._total_bytes += entry.estimated_bytes
            self._total_queries += 1

        if self._log_path:
            try:
                with open(self._log_path, "a") as f:
                    f.write(json.dumps(asdict(entry)) + "\n")
            except Exception:
                pass

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()
            self._total_bytes = 0
            self._total_queries = 0
        if self._log_path and self._log_path.exists():
            try:
                self._log_path.unlink()
            except Exception:
                pass

    def snapshot(self, limit: int = 30) -> dict[str, Any]:
        with self._lock:
            entries = list(self._entries)

        by_sql: dict[str, dict[str, Any]] = {}
        by_caller: dict[str, dict[str, Any]] = {}

        for e in entries:
            # --- aggregate by SQL fingerprint ---
            agg = by_sql.setdefault(
                e.sql_hash,
                {
                    "sql_fingerprint": e.sql_fingerprint,
                    "sql_hash": e.sql_hash,
                    "queries": 0,
                    "total_bytes": 0,
                    "total_rows": 0,
                    "avg_bytes": 0,
                    "avg_duration_ms": 0.0,
                    "_duration_sum": 0.0,
                    "columns": e.columns,
                    "callers": set(),
                },
            )
            agg["queries"] += 1
            agg["total_bytes"] += e.estimated_bytes
            agg["total_rows"] += e.row_count
            agg["_duration_sum"] += e.duration_ms
            agg["callers"].add(e.caller)

            # --- aggregate by caller ---
            cagg = by_caller.setdefault(
                e.caller,
                {
                    "caller": e.caller,
                    "caller_type": e.caller_type,
                    "queries": 0,
                    "total_bytes": 0,
                    "total_rows": 0,
                    "sql_hashes": set(),
                },
            )
            cagg["queries"] += 1
            cagg["total_bytes"] += e.estimated_bytes
            cagg["total_rows"] += e.row_count
            cagg["sql_hashes"].add(e.sql_hash)

        for agg in by_sql.values():
            agg["avg_bytes"] = round(agg["total_bytes"] / max(agg["queries"], 1))
            agg["avg_duration_ms"] = round(agg["_duration_sum"] / max(agg["queries"], 1), 2)
            agg["callers"] = sorted(agg["callers"])
            agg.pop("_duration_sum", None)

        for cagg in by_caller.values():
            cagg["sql_hashes"] = sorted(cagg["sql_hashes"])

        top_queries = sorted(by_sql.values(), key=lambda x: x["total_bytes"], reverse=True)[:limit]
        top_callers = sorted(by_caller.values(), key=lambda x: x["total_bytes"], reverse=True)[:limit]
        recent = [asdict(e) for e in list(entries)[-limit:]]
        recent.reverse()

        total_bytes = sum(e.estimated_bytes for e in entries)
        total_rows = sum(e.row_count for e in entries)

        return {
            "summary": {
                "window_queries": len(entries),
                "window_bytes": total_bytes,
                "window_bytes_human": _human_bytes(total_bytes),
                "window_rows": total_rows,
                "lifetime_queries": self._total_queries,
                "lifetime_bytes": self._total_bytes,
                "lifetime_bytes_human": _human_bytes(self._total_bytes),
                "log_file": str(self._log_path) if self._log_path else None,
            },
            "top_queries_by_bytes": top_queries,
            "top_callers_by_bytes": top_callers,
            "recent": recent,
        }


def _human_bytes(n: int) -> str:
    b = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(b) < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_store = PgEgressStore()


def get_pg_egress_store() -> PgEgressStore:
    return _store


def reset_pg_egress_store() -> None:
    _store.reset()


# ---------------------------------------------------------------------------
# SQLAlchemy event hooks
# ---------------------------------------------------------------------------
def install_pg_egress_hooks(engine: Any) -> None:
    """Attach before/after cursor-execute listeners to the engine."""
    from sqlalchemy import event

    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    _store.set_log_path(log_dir / "pg_egress.jsonl")
    logger.info("pg_egress: logging to %s", log_dir / "pg_egress.jsonl")

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        conn.info["_pg_egress_start"] = perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        start = conn.info.pop("_pg_egress_start", None)
        if start is None:
            return
        duration_ms = round((perf_counter() - start) * 1000, 3)

        stmt_upper = (statement or "").strip().upper()[:30]
        # Only measure data-returning statements
        if not stmt_upper.startswith("SELECT") and "RETURNING" not in stmt_upper:
            return

        estimated_bytes = 0
        row_count = 0
        col_count = 0
        columns: list[str] = []

        pgresult = getattr(cursor, "pgresult", None)
        if pgresult is not None:
            row_count = getattr(pgresult, "ntuples", 0) or 0
            col_count = getattr(pgresult, "nfields", 0) or 0
            estimated_bytes = _estimate_bytes_from_pgresult(pgresult)
            try:
                columns = [pgresult.fname(i).decode() for i in range(min(col_count, 30))]
            except Exception:
                pass
        else:
            row_count = max(getattr(cursor, "rowcount", 0) or 0, 0)
            col_count = len(cursor.description) if cursor.description else 0
            try:
                columns = [d.name for d in (cursor.description or [])[:30]]
            except Exception:
                pass

        fingerprint = _fingerprint_sql(statement or "")
        caller, caller_type = _get_caller()

        _store.record(
            PgQueryRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                sql_fingerprint=fingerprint,
                sql_hash=_hash_sql(fingerprint),
                row_count=row_count,
                col_count=col_count,
                estimated_bytes=estimated_bytes,
                duration_ms=duration_ms,
                caller=caller,
                caller_type=caller_type,
                columns=columns,
            )
        )
