"""
Extract diverse sample data from the production database for prompt evaluation.

Usage:
    cd ai_news && PYTHONPATH=. .venv/bin/python -u tests/eval/extract_samples.py

Outputs JSON fixtures to tests/eval/fixtures/.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from sqlalchemy import func

from app.db import SessionLocal
from app.models import Article, Cluster, ClusterMember, RawItem, Source


def _print(msg: str = ""):
    """Print with immediate flush for visibility in piped/background runs."""
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

random.seed(42)


def _serialize(obj):
    """JSON-safe fallback for non-standard types."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def _dump(name: str, data):
    path = FIXTURES_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=_serialize)
    _print(f"  -> {path}  ({_count_desc(data)})")


def _count_desc(data) -> str:
    if isinstance(data, list):
        return f"{len(data)} items"
    if isinstance(data, dict) and "groups" in data:
        return f"{len(data['groups'])} groups"
    return "ok"


# ─────────────────────────────────────────────────────────────────────
# 1. classification_samples.json
# ─────────────────────────────────────────────────────────────────────

def extract_classification_samples(db) -> list[dict]:
    """30 articles with diverse event types, including some OTHER."""
    _print("Extracting classification samples...")

    # Bulk-fetch all articles with their source info (only the columns we need).
    # Avoid ORDER BY RANDOM() and func.length() which are slow on remote PG.
    rows = (
        db.query(
            Article.id, Article.event_type, Article.text, Article.topics,
            RawItem.title, Source.name, Source.kind,
        )
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .join(Source, RawItem.source_id == Source.id)
        .filter(Article.text.isnot(None))
        .all()
    )
    _print(f"  Fetched {len(rows)} article rows")

    # Filter for sufficient text length in Python
    rows = [r for r in rows if r.text and len(r.text) > 200]

    # Group by event type
    by_type: dict[str, list] = {}
    for r in rows:
        by_type.setdefault(r.event_type, []).append(r)

    event_types = sorted(by_type.keys())
    _print(f"  Found event types: {event_types}")

    samples = []
    target = 30
    real_types = [et for et in event_types if et != "OTHER"]
    per_type = max(2, target // (len(real_types) + 1)) if real_types else target

    for et in real_types:
        pool = by_type.get(et, [])
        random.shuffle(pool)
        for r in pool[:per_type]:
            samples.append({
                "id": str(r.id),
                "title": r.title,
                "text": r.text[:2000],
                "source_name": r.name,
                "source_kind": r.kind,
                "current_event_type": r.event_type,
                "current_topics": r.topics,
            })

    # Fill remaining with OTHER
    remaining = target - len(samples)
    if remaining > 0 and "OTHER" in by_type:
        pool = by_type["OTHER"]
        random.shuffle(pool)
        for r in pool[:remaining]:
            samples.append({
                "id": str(r.id),
                "title": r.title,
                "text": r.text[:2000],
                "source_name": r.name,
                "source_kind": r.kind,
                "current_event_type": r.event_type,
                "current_topics": r.topics,
            })

    random.shuffle(samples)
    return samples[:target]


# ─────────────────────────────────────────────────────────────────────
# 2. summary_samples.json
# ─────────────────────────────────────────────────────────────────────

def extract_summary_samples(db) -> list[dict]:
    """20 articles that have both text and existing summaries."""
    _print("Extracting summary samples...")

    rows = (
        db.query(
            Article.id, Article.text, Article.summary,
            RawItem.title, Source.name,
        )
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .join(Source, RawItem.source_id == Source.id)
        .filter(Article.summary.isnot(None))
        .filter(Article.text.isnot(None))
        .all()
    )
    _print(f"  Fetched {len(rows)} articles with summaries")

    # Filter in Python for quality thresholds
    rows = [r for r in rows if r.summary and len(r.summary) > 30
            and r.text and len(r.text) > 500]

    random.shuffle(rows)
    samples = []
    for r in rows[:20]:
        samples.append({
            "id": str(r.id),
            "title": r.title,
            "text": r.text[:2000],
            "current_summary": r.summary,
            "source_name": r.name,
        })

    return samples


# ─────────────────────────────────────────────────────────────────────
# 3. significance_samples.json
# ─────────────────────────────────────────────────────────────────────

def extract_significance_samples(db) -> list[dict]:
    """25 articles spanning low/mid/high scores."""
    _print("Extracting significance samples...")

    rows = (
        db.query(
            Article.id, Article.text, Article.event_type,
            Article.global_score, Article.final_score,
            RawItem.title, Source.name,
        )
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .join(Source, RawItem.source_id == Source.id)
        .filter(Article.text.isnot(None))
        .all()
    )
    _print(f"  Fetched {len(rows)} articles")

    # Filter for text length in Python
    rows = [r for r in rows if r.text and len(r.text) > 200]

    # Stratified sampling: low (<40), mid (40-70), high (>70)
    samples = []
    for label, lo, hi, count in [("low", 0, 40, 8), ("mid", 40, 70, 9), ("high", 70, 101, 8)]:
        bucket = []
        for r in rows:
            score = r.final_score if r.final_score is not None else r.global_score
            if score is not None and lo <= score < hi:
                bucket.append(r)
        random.shuffle(bucket)
        for r in bucket[:count]:
            samples.append({
                "id": str(r.id),
                "title": r.title,
                "text_preview": r.text[:800],
                "source_name": r.name,
                "event_type": r.event_type,
                "global_score": r.global_score,
                "final_score": r.final_score,
            })
        _print(f"    {label} ({lo}-{hi}): got {min(len(bucket), count)} articles")

    random.shuffle(samples)
    return samples[:25]


# ─────────────────────────────────────────────────────────────────────
# 4. digest_samples.json
# ─────────────────────────────────────────────────────────────────────

def extract_digest_samples(db) -> dict:
    """3 groups of 10-15 articles each, simulating digest input."""
    _print("Extracting digest samples...")

    # Fetch top articles by score — no ORDER BY RANDOM needed
    rows = (
        db.query(
            Article.id, Article.text, Article.summary, Article.content_type,
            Article.final_score, Article.global_score,
            RawItem.title, RawItem.snippet,
        )
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .filter(Article.text.isnot(None))
        .all()
    )
    _print(f"  Fetched {len(rows)} articles")

    groups = []
    for ct in ["all", "news", "research"]:
        pool = rows if ct == "all" else [r for r in rows if r.content_type == ct]
        # Sort by score descending, take top 50
        pool_sorted = sorted(
            pool,
            key=lambda r: (r.final_score if r.final_score is not None else r.global_score) or 0,
            reverse=True,
        )[:50]

        # Sample 10-15 from top 50
        n = min(len(pool_sorted), random.randint(10, 15))
        if n > 0:
            selected = random.sample(pool_sorted, n) if len(pool_sorted) > n else pool_sorted
        else:
            selected = []

        articles = []
        for r in selected:
            articles.append({
                "title": r.title,
                "summary": r.summary or r.snippet or (r.text[:240] if r.text else ""),
            })

        groups.append({
            "content_type": ct,
            "article_count": len(articles),
            "articles": articles,
        })
        _print(f"    {ct}: {len(articles)} articles")

    return {"groups": groups}


# ─────────────────────────────────────────────────────────────────────
# 5. relationship_samples.json
# ─────────────────────────────────────────────────────────────────────

def extract_relationship_samples(db) -> list[dict]:
    """10 pairs of clusters. Some should be related, some not."""
    _print("Extracting relationship samples...")

    # Get recent clusters with top_article_id
    clusters = (
        db.query(Cluster)
        .filter(Cluster.top_article_id.isnot(None))
        .filter(Cluster.coverage_count >= 2)
        .order_by(Cluster.updated_at.desc())
        .limit(100)
        .all()
    )
    _print(f"  Fetched {len(clusters)} clusters with coverage >= 2")

    if len(clusters) < 4:
        _print("    Not enough clusters. Trying without coverage filter...")
        clusters = (
            db.query(Cluster)
            .filter(Cluster.top_article_id.isnot(None))
            .order_by(Cluster.updated_at.desc())
            .limit(100)
            .all()
        )
        _print(f"  Fetched {len(clusters)} clusters (no coverage filter)")

    if len(clusters) < 2:
        _print("    WARNING: Not enough clusters to form pairs. Skipping.")
        return []

    # Batch-fetch all top articles for these clusters
    top_article_ids = [c.top_article_id for c in clusters]
    articles_by_id = {}
    for article in db.query(Article).filter(Article.id.in_(top_article_ids)).all():
        articles_by_id[str(article.id)] = article

    _print(f"  Fetched {len(articles_by_id)} top articles for clusters")

    # Enrich each cluster
    enriched = []
    for cluster in clusters:
        article = articles_by_id.get(str(cluster.top_article_id))
        if not article:
            continue

        # Get entities (top 3 by weight)
        entities_top3 = []
        if isinstance(article.entities, dict):
            sorted_ents = sorted(
                article.entities.items(),
                key=lambda x: x[1] if isinstance(x[1], (int, float)) else 0,
                reverse=True,
            )
            entities_top3 = [e[0] for e in sorted_ents[:3]]

        # Determine dominant topic
        dominant_topic = None
        if isinstance(article.topics, list) and article.topics:
            dominant_topic = article.topics[0]
        elif isinstance(article.topics, dict) and article.topics:
            dominant_topic = max(article.topics, key=article.topics.get)

        enriched.append({
            "cluster_id": str(cluster.id),
            "headline": cluster.headline,
            "top_summary": article.summary or (article.text[:300] if article.text else ""),
            "entities": entities_top3,
            "dominant_event_type": article.event_type,
            "dominant_topic": dominant_topic,
        })

    _print(f"  Enriched {len(enriched)} clusters")

    if len(enriched) < 2:
        _print("    WARNING: Not enough enriched clusters to form pairs.")
        return []

    pairs = []

    # Strategy 1: pairs that share entities (likely related)
    entity_index: dict[str, list[int]] = {}
    for i, c in enumerate(enriched):
        for ent in c["entities"]:
            entity_index.setdefault(ent.lower(), []).append(i)

    related_pairs_seen = set()
    for ent, indices in entity_index.items():
        if len(indices) >= 2:
            for a in indices:
                for b in indices:
                    if a < b:
                        key = (a, b)
                        if key not in related_pairs_seen:
                            related_pairs_seen.add(key)
                            pairs.append({
                                "cluster_a": enriched[a],
                                "cluster_b": enriched[b],
                                "expected_related": True,
                                "shared_entity": ent,
                            })

    # Strategy 2: pairs with same event_type (might be related)
    type_index: dict[str, list[int]] = {}
    for i, c in enumerate(enriched):
        type_index.setdefault(c["dominant_event_type"], []).append(i)

    for et, indices in type_index.items():
        if len(indices) >= 2 and et != "OTHER":
            idx_a, idx_b = random.sample(indices, 2)
            key = (min(idx_a, idx_b), max(idx_a, idx_b))
            if key not in related_pairs_seen:
                related_pairs_seen.add(key)
                pairs.append({
                    "cluster_a": enriched[idx_a],
                    "cluster_b": enriched[idx_b],
                    "expected_related": None,  # unknown — same event type but may not be related
                    "same_event_type": et,
                })

    # Strategy 3: random pairs (likely unrelated)
    attempts = 0
    while len(pairs) < 10 and attempts < 50:
        attempts += 1
        a, b = random.sample(range(len(enriched)), 2)
        key = (min(a, b), max(a, b))
        if key not in related_pairs_seen:
            related_pairs_seen.add(key)
            shared = set(e.lower() for e in enriched[a]["entities"]) & set(e.lower() for e in enriched[b]["entities"])
            pairs.append({
                "cluster_a": enriched[a],
                "cluster_b": enriched[b],
                "expected_related": False if not shared else None,
            })

    random.shuffle(pairs)
    return pairs[:10]


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

def main():
    _print("Connecting to database...")
    db = SessionLocal()

    try:
        # Quick sanity check
        article_count = db.query(func.count(Article.id)).scalar()
        cluster_count = db.query(func.count(Cluster.id)).scalar()
        _print(f"  Database has {article_count} articles, {cluster_count} clusters")
        _print()

        classification = extract_classification_samples(db)
        _dump("classification_samples.json", classification)
        _print()

        summary = extract_summary_samples(db)
        _dump("summary_samples.json", summary)
        _print()

        significance = extract_significance_samples(db)
        _dump("significance_samples.json", significance)
        _print()

        digest = extract_digest_samples(db)
        _dump("digest_samples.json", digest)
        _print()

        relationships = extract_relationship_samples(db)
        _dump("relationship_samples.json", relationships)
        _print()

        _print("Done! All fixtures written to tests/eval/fixtures/")

    finally:
        db.close()


if __name__ == "__main__":
    main()
