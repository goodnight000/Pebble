from __future__ import annotations

from functools import lru_cache
import hashlib
import re
import warnings
from typing import Iterable, List

import numpy as np

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover - best effort fallback
    SentenceTransformer = None


MODEL_NAME = "all-MiniLM-L6-v2"
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_WARNED = False


def _warn_once(message: str) -> None:
    global _WARNED
    if _WARNED:
        return
    _WARNED = True
    warnings.warn(message)


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    if SentenceTransformer is None:
        _warn_once("sentence-transformers unavailable; falling back to hashed embeddings.")
        return None
    try:
        return SentenceTransformer(MODEL_NAME)
    except Exception as exc:  # pragma: no cover - network/model load errors
        _warn_once(f"Embedding model load failed ({exc}); falling back to hashed embeddings.")
        return None


def _fallback_embed(texts: List[str]) -> np.ndarray:
    vectors = np.zeros((len(texts), 384), dtype=np.float32)
    for idx, text in enumerate(texts):
        tokens = _TOKEN_RE.findall((text or "").lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "little") % 384
            vectors[idx, bucket] += 1.0
        norm = np.linalg.norm(vectors[idx])
        if norm > 0:
            vectors[idx] /= norm
    return vectors


def embed_texts(texts: Iterable[str]) -> np.ndarray:
    text_list = list(texts)
    if not text_list:
        return np.zeros((0, 384), dtype=np.float32)
    model = _model()
    if model is None:
        return _fallback_embed(text_list)
    try:
        embeddings = model.encode(text_list, normalize_embeddings=True)
        return np.asarray(embeddings, dtype=np.float32)
    except Exception as exc:  # pragma: no cover - model/runtime errors
        _warn_once(f"Embedding encode failed ({exc}); falling back to hashed embeddings.")
        return _fallback_embed(text_list)


def embed_text(text: str) -> np.ndarray:
    return embed_texts([text])[0]


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a is None or b is None:
        return 0.0
    return float(np.dot(a, b))
