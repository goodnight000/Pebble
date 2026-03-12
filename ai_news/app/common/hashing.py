from __future__ import annotations

import hashlib


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_hash(title: str, url: str) -> str:
    normalized = f"{title.strip().lower()}\n{url.strip().lower()}"
    return sha256_text(normalized)
