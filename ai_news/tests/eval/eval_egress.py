#!/usr/bin/env python3
"""
Egress Optimization Measurement
=================================
Measures actual API response sizes, timing, and caching behavior.
Computes estimated daily egress and scores against efficiency budgets.

Usage:
    cd ai_news
    .venv/bin/python tests/eval/eval_egress.py
    .venv/bin/python tests/eval/eval_egress.py --version optimized
    .venv/bin/python tests/eval/eval_egress.py --compare baseline optimized
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

BASE_URL = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EndpointBudget:
    """Efficiency budget for a single endpoint."""
    max_response_bytes: int
    max_bytes_per_item: int | None  # None = N/A (e.g., health, longform)
    max_response_ms: int
    requests_per_day: int  # estimated for 1-user daily egress calc


@dataclass
class EndpointResult:
    """Measurement result for a single endpoint."""
    endpoint: str
    status_code: int
    response_bytes: int
    response_ms: float
    item_count: int
    bytes_per_item: float | None
    has_cache_control: bool
    cache_hit: bool
    second_request_ms: float
    scores: dict[str, float] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass
class EgressSummary:
    """Aggregated egress measurement results."""
    version: str
    endpoint_results: list[dict]
    dimension_averages: dict[str, float]
    overall_score: float
    daily_egress_bytes: int
    daily_egress_mb: float
    monthly_egress_gb: float
    egress_breakdown: list[dict]
    baseline_daily_gb: float = 10.0
    reduction_pct: float = 0.0


# ---------------------------------------------------------------------------
# Budget definitions
# ---------------------------------------------------------------------------

ENDPOINTS: dict[str, tuple[str, EndpointBudget]] = {
    "digest_today": (
        "/api/digest/today?locale=en",
        EndpointBudget(
            max_response_bytes=100 * 1024,
            max_bytes_per_item=5 * 1024,
            max_response_ms=2000,
            requests_per_day=288,  # every 5 min
        ),
    ),
    "news_weekly": (
        "/api/news/weekly?limit=6&locale=en",
        EndpointBudget(
            max_response_bytes=30 * 1024,
            max_bytes_per_item=5 * 1024,
            max_response_ms=1000,
            requests_per_day=2,
        ),
    ),
    "digest_archive": (
        "/api/digest/archive?limit=5",
        EndpointBudget(
            max_response_bytes=10 * 1024,
            max_bytes_per_item=2 * 1024,
            max_response_ms=500,
            requests_per_day=1,
        ),
    ),
    "digest_daily": (
        "/api/digest/daily?locale=en",
        EndpointBudget(
            max_response_bytes=500 * 1024,
            max_bytes_per_item=None,  # longform HTML, no per-item metric
            max_response_ms=2000,
            requests_per_day=1,
        ),
    ),
    "signal_map": (
        "/v1/signal-map",
        EndpointBudget(
            max_response_bytes=200 * 1024,
            max_bytes_per_item=int(2.5 * 1024),
            max_response_ms=3000,
            requests_per_day=4,
        ),
    ),
    "graph": (
        "/v1/graph?hours=48",
        EndpointBudget(
            max_response_bytes=150 * 1024,
            max_bytes_per_item=2 * 1024,
            max_response_ms=3000,
            requests_per_day=4,
        ),
    ),
    "health": (
        "/v1/health",
        EndpointBudget(
            max_response_bytes=200,
            max_bytes_per_item=None,
            max_response_ms=100,
            requests_per_day=0,  # not polled by frontend
        ),
    ),
}


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _score_against_budget(actual: float, budget: float) -> int:
    """Score 1-10 based on ratio of actual to budget.

    10 = under 25% of budget
     9 = under 50% of budget
     7 = under 75% of budget
     5 = at or under budget
     3 = up to 1.5x budget
     2 = up to 2x budget
     1 = over 2x budget
    """
    if budget <= 0:
        return 5
    ratio = actual / budget
    if ratio <= 0.25:
        return 10
    if ratio <= 0.50:
        return 9
    if ratio <= 0.75:
        return 7
    if ratio <= 1.0:
        return 5
    if ratio <= 1.5:
        return 3
    if ratio <= 2.0:
        return 2
    return 1


def _count_items(endpoint_key: str, data: dict) -> int:
    """Extract item count from parsed JSON response."""
    if endpoint_key == "digest_today":
        return len(data.get("items", []))
    if endpoint_key == "news_weekly":
        return len(data.get("items", []))
    if endpoint_key == "digest_archive":
        return len(data.get("digests", []))
    if endpoint_key == "digest_daily":
        return 1  # single longform document
    if endpoint_key == "signal_map":
        return len(data.get("clusters", []))
    if endpoint_key == "graph":
        return len(data.get("clusters", [])) + len(data.get("edges", []))
    if endpoint_key == "health":
        return 1
    return 0


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

def _fetch(url: str) -> tuple[bytes, dict, int, float]:
    """Fetch URL, return (body_bytes, headers_dict, status, elapsed_ms)."""
    req = Request(url)
    req.add_header("Accept", "application/json")
    req.add_header("Accept-Encoding", "identity")  # no compression, measure raw size
    start = time.perf_counter()
    try:
        resp = urlopen(req, timeout=30)
        body = resp.read()
        elapsed = (time.perf_counter() - start) * 1000
        headers = {k.lower(): v for k, v in resp.getheaders()}
        return body, headers, resp.status, elapsed
    except URLError as e:
        elapsed = (time.perf_counter() - start) * 1000
        return b"", {}, getattr(e, "code", 0) or 0, elapsed


def measure_endpoint(endpoint_key: str, path: str, budget: EndpointBudget) -> EndpointResult:
    """Measure a single endpoint: size, timing, caching."""
    url = f"{BASE_URL}{path}"
    errors: list[str] = []

    # First request
    body, headers, status, elapsed_ms = _fetch(url)
    response_bytes = len(body)

    if status == 0 or status >= 400:
        return EndpointResult(
            endpoint=endpoint_key,
            status_code=status,
            response_bytes=0,
            response_ms=elapsed_ms,
            item_count=0,
            bytes_per_item=None,
            has_cache_control=False,
            cache_hit=False,
            second_request_ms=0,
            scores={},
            errors=[f"HTTP {status}: endpoint unreachable or returned error"],
        )

    # Parse JSON to count items
    item_count = 0
    try:
        data = json.loads(body)
        item_count = _count_items(endpoint_key, data)
    except (json.JSONDecodeError, TypeError):
        errors.append("response_not_json")

    bytes_per_item = (response_bytes / item_count) if item_count > 0 else None

    # Check Cache-Control header
    has_cache_control = "cache-control" in headers

    # Second request for cache behavior
    _body2, _headers2, _status2, elapsed_ms_2 = _fetch(url)
    # Heuristic: if second request is significantly faster, likely a cache hit
    cache_hit = elapsed_ms_2 < (elapsed_ms * 0.5) if elapsed_ms > 10 else False

    # Score against budgets
    scores: dict[str, float] = {}
    scores["size"] = _score_against_budget(response_bytes, budget.max_response_bytes)
    scores["time"] = _score_against_budget(elapsed_ms, budget.max_response_ms)

    if budget.max_bytes_per_item is not None and bytes_per_item is not None:
        scores["bytes_per_item"] = _score_against_budget(bytes_per_item, budget.max_bytes_per_item)

    scores["cache"] = 10 if has_cache_control else 0

    return EndpointResult(
        endpoint=endpoint_key,
        status_code=status,
        response_bytes=response_bytes,
        response_ms=round(elapsed_ms, 1),
        item_count=item_count,
        bytes_per_item=round(bytes_per_item, 1) if bytes_per_item is not None else None,
        has_cache_control=has_cache_control,
        cache_hit=cache_hit,
        second_request_ms=round(elapsed_ms_2, 1),
        scores=scores,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Aggregation & reporting
# ---------------------------------------------------------------------------

def _format_bytes(n: int | float) -> str:
    """Human-readable byte size."""
    if n < 1024:
        return f"{int(n)}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}KB"
    return f"{n / (1024 * 1024):.2f}MB"


def run_measurement(version: str = "current") -> EgressSummary:
    """Run the full egress measurement against all endpoints."""
    print(f"\n{'=' * 70}")
    print(f"  EGRESS OPTIMIZATION MEASUREMENT — version: {version}")
    print(f"  Target: {BASE_URL}")
    print(f"{'=' * 70}\n")

    # Connectivity check
    print("  Checking backend connectivity...")
    try:
        body, _, status, _ = _fetch(f"{BASE_URL}/v1/health")
        if status != 200:
            print(f"  ERROR: Backend returned HTTP {status}. Is it running?")
            sys.exit(1)
        print(f"  Backend is up (HTTP {status}).\n")
    except Exception as e:
        print(f"  ERROR: Cannot reach backend at {BASE_URL}: {e}")
        sys.exit(1)

    results: list[EndpointResult] = []
    for key, (path, budget) in ENDPOINTS.items():
        print(f"  Measuring {key} ({path})...")
        result = measure_endpoint(key, path, budget)
        results.append(result)

        if result.errors:
            for err in result.errors:
                print(f"    WARNING: {err}")
            print()
            continue

        status_str = f"HTTP {result.status_code}"
        size_str = _format_bytes(result.response_bytes)
        bpi_str = _format_bytes(result.bytes_per_item) if result.bytes_per_item is not None else "N/A"
        cache_str = "yes" if result.has_cache_control else "NO"
        cache_hit_str = "HIT" if result.cache_hit else "miss"
        print(f"    {status_str} | {size_str:>10s} | {result.response_ms:>7.0f}ms | "
              f"{result.item_count:>3d} items | {bpi_str:>8s}/item | "
              f"Cache-Control: {cache_str} | 2nd req: {result.second_request_ms:.0f}ms ({cache_hit_str})")
        for dim, score in sorted(result.scores.items()):
            bar = "\u2588" * int(score) + "\u2591" * (10 - int(score))
            print(f"      {dim:18s}  {bar}  {score:.0f}/10")
        print()

    # Compute dimension averages
    all_dims: dict[str, list[float]] = {}
    for r in results:
        for dim, score in r.scores.items():
            all_dims.setdefault(dim, []).append(float(score))
    dim_avgs = {dim: round(sum(vals) / len(vals), 2) for dim, vals in all_dims.items()}
    overall = round(sum(dim_avgs.values()) / len(dim_avgs), 2) if dim_avgs else 0.0

    # Print dimension averages
    print(f"\n{'=' * 70}")
    print(f"  DIMENSION AVERAGES")
    print(f"{'=' * 70}")
    for dim, avg in sorted(dim_avgs.items()):
        bar = "\u2588" * int(avg) + "\u2591" * (10 - int(avg))
        print(f"  {dim:25s}  {bar}  {avg:.1f}/10")
    print(f"  {'-' * 55}")
    print(f"  {'OVERALL':25s}  {'':10s}  {overall:.1f}/10")

    # Compute daily egress estimate
    print(f"\n{'=' * 70}")
    print(f"  ESTIMATED DAILY EGRESS (1 user, 1 browser tab)")
    print(f"{'=' * 70}")
    print(f"  {'Endpoint':<25s} {'Size':>10s} {'Req/Day':>8s} {'Daily Transfer':>15s} {'Budget':>10s}")
    print(f"  {'-' * 68}")

    egress_breakdown = []
    daily_total = 0
    for r in results:
        _, budget = ENDPOINTS[r.endpoint]
        daily_bytes = r.response_bytes * budget.requests_per_day
        daily_total += daily_bytes
        budget_daily = budget.max_response_bytes * budget.requests_per_day
        status = "OK" if daily_bytes <= budget_daily else "OVER"
        print(f"  {r.endpoint:<25s} {_format_bytes(r.response_bytes):>10s} "
              f"{budget.requests_per_day:>8d} {_format_bytes(daily_bytes):>15s} "
              f"{status:>10s}")
        egress_breakdown.append({
            "endpoint": r.endpoint,
            "response_bytes": r.response_bytes,
            "requests_per_day": budget.requests_per_day,
            "daily_bytes": daily_bytes,
            "budget_daily_bytes": budget_daily,
            "within_budget": daily_bytes <= budget_daily,
        })

    daily_mb = daily_total / (1024 * 1024)
    monthly_gb = (daily_total * 30) / (1024 * 1024 * 1024)

    print(f"  {'-' * 68}")
    print(f"  {'TOTAL':25s} {'':>10s} {'':>8s} {_format_bytes(daily_total):>15s}")
    print(f"\n  Daily estimate:  {daily_mb:.2f} MB/user/day")
    print(f"  Monthly estimate: {monthly_gb:.2f} GB/user/month")

    # Compare against baseline
    baseline_daily_gb = 10.0
    actual_daily_gb = daily_total / (1024 * 1024 * 1024)
    if actual_daily_gb > 0:
        reduction_pct = (1 - actual_daily_gb / baseline_daily_gb) * 100
    else:
        reduction_pct = 0.0

    print(f"\n  Baseline (pre-optimization): {baseline_daily_gb:.1f} GB/day")
    print(f"  Current:                     {actual_daily_gb * 1000:.2f} MB/day")
    if reduction_pct > 0:
        print(f"  Reduction:                   {reduction_pct:.1f}%")
    print()

    summary = EgressSummary(
        version=version,
        endpoint_results=[asdict(r) for r in results],
        dimension_averages=dim_avgs,
        overall_score=overall,
        daily_egress_bytes=daily_total,
        daily_egress_mb=round(daily_mb, 2),
        monthly_egress_gb=round(monthly_gb, 2),
        egress_breakdown=egress_breakdown,
        baseline_daily_gb=baseline_daily_gb,
        reduction_pct=round(reduction_pct, 1),
    )
    return summary


def save_results(summary: EgressSummary):
    """Save measurement results to JSON."""
    path = RESULTS_DIR / f"egress_{summary.version}.json"
    with open(path, "w") as f:
        json.dump(asdict(summary), f, indent=2, ensure_ascii=False, default=str)
    print(f"  Results saved to {path}")


def print_final_scorecard(summary: EgressSummary):
    """Print a final scorecard similar to run_eval.py."""
    print(f"\n{'=' * 70}")
    print(f"  FINAL SCORECARD — {summary.version}")
    print(f"{'=' * 70}")
    for r in summary.endpoint_results:
        if r["errors"]:
            status = "ERROR"
            score_str = "N/A"
        else:
            scores = r["scores"]
            avg = sum(scores.values()) / len(scores) if scores else 0
            score_str = f"{avg:.1f}/10"
            status = "PASS" if avg >= 5.0 else "WARN" if avg >= 3.0 else "FAIL"
        print(f"  {r['endpoint']:<25s}  {_format_bytes(r['response_bytes']):>10s}  "
              f"{r['response_ms']:>7.0f}ms  {score_str:>8s}  [{status}]")
    print(f"  {'-' * 60}")
    print(f"  {'OVERALL':25s}  {summary.overall_score:.1f}/10")
    print(f"  {'DAILY EGRESS':25s}  {summary.daily_egress_mb:.2f} MB/user/day")
    print(f"  {'MONTHLY EGRESS':25s}  {summary.monthly_egress_gb:.2f} GB/user/month")
    if summary.reduction_pct > 0:
        print(f"  {'REDUCTION vs BASELINE':25s}  {summary.reduction_pct:.1f}%")
    print()


def compare_versions(v1_name: str, v2_name: str):
    """Compare two egress measurement runs."""
    v1_path = RESULTS_DIR / f"egress_{v1_name}.json"
    v2_path = RESULTS_DIR / f"egress_{v2_name}.json"

    if not v1_path.exists():
        print(f"  ERROR: {v1_path} not found")
        sys.exit(1)
    if not v2_path.exists():
        print(f"  ERROR: {v2_path} not found")
        sys.exit(1)

    v1 = json.loads(v1_path.read_text())
    v2 = json.loads(v2_path.read_text())

    print(f"\n{'=' * 70}")
    print(f"  EGRESS COMPARISON: {v1_name} vs {v2_name}")
    print(f"{'=' * 70}")

    # Dimension averages comparison
    print(f"\n  Dimension Averages:")
    all_dims = set(v1.get("dimension_averages", {}).keys()) | set(v2.get("dimension_averages", {}).keys())
    for dim in sorted(all_dims):
        s1 = v1.get("dimension_averages", {}).get(dim, 0)
        s2 = v2.get("dimension_averages", {}).get(dim, 0)
        delta = s2 - s1
        arrow = "\u2191" if delta > 0 else "\u2193" if delta < 0 else "="
        sign = "+" if delta > 0 else ""
        print(f"    {dim:25s}  {s1:.1f} \u2192 {s2:.1f}  ({sign}{delta:.1f} {arrow})")

    o1 = v1.get("overall_score", 0)
    o2 = v2.get("overall_score", 0)
    delta = o2 - o1
    arrow = "\u2191" if delta > 0 else "\u2193" if delta < 0 else "="
    sign = "+" if delta > 0 else ""
    print(f"    {'OVERALL':25s}  {o1:.1f} \u2192 {o2:.1f}  ({sign}{delta:.1f} {arrow})")

    # Per-endpoint comparison
    print(f"\n  Per-Endpoint Response Sizes:")
    v1_endpoints = {r["endpoint"]: r for r in v1.get("endpoint_results", [])}
    v2_endpoints = {r["endpoint"]: r for r in v2.get("endpoint_results", [])}
    all_endpoints = sorted(set(v1_endpoints.keys()) | set(v2_endpoints.keys()))

    for ep in all_endpoints:
        r1 = v1_endpoints.get(ep, {})
        r2 = v2_endpoints.get(ep, {})
        b1 = r1.get("response_bytes", 0)
        b2 = r2.get("response_bytes", 0)
        if b1 > 0:
            change_pct = ((b2 - b1) / b1) * 100
        else:
            change_pct = 0.0
        sign = "+" if change_pct > 0 else ""
        arrow = "\u2191" if change_pct > 0 else "\u2193" if change_pct < 0 else "="
        print(f"    {ep:<25s}  {_format_bytes(b1):>10s} \u2192 {_format_bytes(b2):>10s}  "
              f"({sign}{change_pct:.1f}% {arrow})")

    # Daily egress comparison
    d1 = v1.get("daily_egress_mb", 0)
    d2 = v2.get("daily_egress_mb", 0)
    if d1 > 0:
        egress_change = ((d2 - d1) / d1) * 100
    else:
        egress_change = 0.0
    sign = "+" if egress_change > 0 else ""
    print(f"\n  Daily Egress:")
    print(f"    {v1_name}: {d1:.2f} MB/day")
    print(f"    {v2_name}: {d2:.2f} MB/day")
    print(f"    Change: {sign}{egress_change:.1f}%")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Egress Optimization Measurement")
    parser.add_argument("--version", default="current", help="Version label for this run")
    parser.add_argument("--compare", nargs=2, metavar=("V1", "V2"), help="Compare two versions")
    parser.add_argument("--base-url", default=BASE_URL, help="Backend base URL")
    args = parser.parse_args()

    if args.base_url != BASE_URL:
        BASE_URL = args.base_url

    if args.compare:
        compare_versions(args.compare[0], args.compare[1])
    else:
        summary = run_measurement(version=args.version)
        save_results(summary)
        print_final_scorecard(summary)
