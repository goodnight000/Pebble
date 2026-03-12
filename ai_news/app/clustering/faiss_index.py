from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

try:
    import faiss
except Exception:  # pragma: no cover - optional dependency
    faiss = None
import numpy as np


@dataclass
class ClusterIndex:
    index: object | None
    id_map: Dict[int, str]


class FaissClusterIndex:
    def __init__(self, dim: int = 384):
        self.dim = dim
        self._use_faiss = faiss is not None
        self._index = faiss.IndexFlatIP(dim) if self._use_faiss else None
        self._id_map: Dict[int, str] = {}
        self._embeddings = np.zeros((0, dim), dtype=np.float32)

    def rebuild(self, embeddings: np.ndarray, ids: list[str]) -> None:
        self._id_map = {}
        if embeddings.size == 0:
            self._embeddings = np.zeros((0, self.dim), dtype=np.float32)
            if self._use_faiss:
                self._index = faiss.IndexFlatIP(self.dim)
            return

        normalized = embeddings.astype(np.float32)
        norms = np.linalg.norm(normalized, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        normalized = normalized / norms

        if self._use_faiss:
            self._index = faiss.IndexFlatIP(self.dim)
            faiss.normalize_L2(normalized)
            self._index.add(normalized)
        else:
            self._embeddings = normalized

        self._id_map = {i: cluster_id for i, cluster_id in enumerate(ids)}

    def search(self, embedding: np.ndarray, k: int = 5) -> Tuple[str | None, float]:
        if self._use_faiss:
            if self._index is None or self._index.ntotal == 0:
                return None, 0.0
            emb = embedding.astype(np.float32).reshape(1, -1)
            faiss.normalize_L2(emb)
            scores, idxs = self._index.search(emb, k)
            best_idx = int(idxs[0][0])
            if best_idx < 0:
                return None, 0.0
            cluster_id = self._id_map.get(best_idx)
            return cluster_id, float(scores[0][0])

        if self._embeddings.size == 0:
            return None, 0.0
        emb = embedding.astype(np.float32)
        norm = np.linalg.norm(emb)
        if norm == 0:
            return None, 0.0
        emb = emb / norm
        scores = self._embeddings @ emb
        if scores.size == 0:
            return None, 0.0
        best_idx = int(np.argmax(scores))
        cluster_id = self._id_map.get(best_idx)
        return cluster_id, float(scores[best_idx])
