"""Evaluate the impact of bidirectional LLM judge scoring.

Read-only script — queries articles from the last 7 days where llm_score
is not NULL and computes what the bidirectional scoring would produce
vs. the current max-only approach.

Usage:
    python -m scripts.eval_llm_judge_bidirectional
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

# Allow running as `python -m scripts.eval_llm_judge_bidirectional` from ai_news/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.common.time import utcnow
from app.db import session_scope
from app.models import Article


def _bidirectional_score(
    rule_score: float,
    llm_score: float,
    confirmation_level: str | None,
    trust_label: str | None,
) -> float:
    blended = 0.70 * rule_score + 0.30 * llm_score
    if blended >= rule_score:
        return round(blended, 2)
    delta = rule_score - blended
    if confirmation_level == "official":
        delta = min(delta, 5.0)
    if trust_label in ("official", "confirmed", "likely"):
        delta = delta * 0.5
    delta = min(delta, 15.0)
    return round(rule_score - delta, 2)


def main():
    cutoff = utcnow() - timedelta(days=7)
    with session_scope() as session:
        articles = (
            session.query(Article)
            .filter(Article.llm_score.isnot(None), Article.created_at >= cutoff)
            .all()
        )

    if not articles:
        print("No articles with LLM scores in the last 7 days.")
        return

    print(f"Articles with LLM scores (last 7 days): {len(articles)}\n")

    changes = []
    for art in articles:
        old_final = max(art.global_score, 0.70 * art.global_score + 0.30 * art.llm_score)
        new_final = _bidirectional_score(
            art.global_score, art.llm_score,
            art.confirmation_level, art.trust_label,
        )
        delta = new_final - old_final
        if abs(delta) > 0.01:
            changes.append({
                "id": art.id,
                "global": art.global_score,
                "llm": art.llm_score,
                "old_final": round(old_final, 2),
                "new_final": new_final,
                "delta": round(delta, 2),
                "confirmation": art.confirmation_level,
                "trust": art.trust_label,
            })

    print(f"Articles changing score: {len(changes)}")
    big_changes = [c for c in changes if abs(c['delta']) > 5]
    print(f"  > 5pt change: {len(big_changes)}")

    lowered_official = [c for c in changes if c['confirmation'] == 'official' and c['delta'] < 0]
    print(f"  Official-source lowerings: {len(lowered_official)}")

    if changes:
        deltas = [c['delta'] for c in changes]
        print(f"\nDelta distribution:")
        print(f"  Min: {min(deltas):.2f}")
        print(f"  Max: {max(deltas):.2f}")
        print(f"  Mean: {sum(deltas)/len(deltas):.2f}")

        print(f"\nTop 10 largest changes:")
        for c in sorted(changes, key=lambda x: abs(x['delta']), reverse=True)[:10]:
            print(f"  id={c['id'][:8]} global={c['global']:.1f} llm={c['llm']:.1f} "
                  f"old={c['old_final']:.1f} new={c['new_final']:.1f} delta={c['delta']:+.1f} "
                  f"conf={c['confirmation']} trust={c['trust']}")


if __name__ == "__main__":
    main()
