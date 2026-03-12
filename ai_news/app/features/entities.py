from __future__ import annotations

from collections import Counter
from functools import lru_cache
from typing import Dict

try:
    import spacy
except Exception:  # pragma: no cover - optional dependency
    spacy = None

from app.config import load_entity_aliases


@lru_cache(maxsize=1)
def _nlp():
    if spacy is None:
        return None
    try:
        return spacy.load("en_core_web_sm")
    except Exception:
        return None


@lru_cache(maxsize=1)
def _alias_map() -> Dict[str, str]:
    data = load_entity_aliases()
    aliases = data.get("aliases", {})
    mapping: Dict[str, str] = {}
    for canonical, names in aliases.items():
        for name in names:
            mapping[name.lower()] = canonical
    return mapping


def _canonicalize(name: str) -> str:
    mapping = _alias_map()
    return mapping.get(name.lower(), name)


def extract_entities(text: str) -> Dict[str, float]:
    if not text:
        return {}
    nlp = _nlp()
    if nlp is None:
        return {}
    doc = nlp(text)
    counts = Counter()
    for ent in doc.ents:
        if ent.label_ in {"ORG", "PERSON", "GPE", "PRODUCT"}:
            canonical = _canonicalize(ent.text.strip())
            counts[canonical] += 1
    if not counts:
        return {}
    most_common = counts.most_common(5)
    total = sum(count for _, count in most_common)
    return {entity: count / total for entity, count in most_common}
