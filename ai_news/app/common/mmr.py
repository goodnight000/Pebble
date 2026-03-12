from __future__ import annotations

from typing import List, Sequence

import numpy as np


def mmr_select(
    items: Sequence[dict],
    embeddings: np.ndarray,
    lambda_mult: float = 0.8,
    k: int = 10,
    score_key: str = "score",
) -> List[dict]:
    if not items:
        return []
    selected = []
    selected_indices = []
    candidate_indices = list(range(len(items)))

    scores = np.array([item.get(score_key, 0.0) for item in items], dtype=np.float32)
    if embeddings.shape[0] != len(items):
        raise ValueError("Embeddings count must match items count")

    while candidate_indices and len(selected) < k:
        if not selected_indices:
            best_idx = int(candidate_indices[np.argmax(scores[candidate_indices])])
            selected_indices.append(best_idx)
            selected.append(items[best_idx])
            candidate_indices.remove(best_idx)
            continue

        selected_emb = embeddings[selected_indices]
        candidate_emb = embeddings[candidate_indices]
        similarity = candidate_emb @ selected_emb.T
        max_sim = similarity.max(axis=1)

        candidate_scores = scores[candidate_indices]
        mmr_scores = lambda_mult * candidate_scores - (1 - lambda_mult) * max_sim
        best_local = int(np.argmax(mmr_scores))
        best_idx = candidate_indices[best_local]
        selected_indices.append(best_idx)
        selected.append(items[best_idx])
        candidate_indices.remove(best_idx)

    return selected
