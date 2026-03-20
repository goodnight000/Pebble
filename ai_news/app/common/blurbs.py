from __future__ import annotations

from app.common.text import normalize_whitespace


def _clip_blurb(text: str, max_length: int) -> str:
    compact = normalize_whitespace(text)
    if len(compact) <= max_length:
        return compact

    clipped = compact[:max_length]
    sentence_break = max(
        clipped.rfind(". "),
        clipped.rfind("! "),
        clipped.rfind("? "),
        clipped.rfind("; "),
        clipped.rfind(": "),
    )
    if sentence_break >= max_length // 2:
        cut = sentence_break + 1
    else:
        cut = clipped.rfind(" ")
        if cut < max_length // 2:
            cut = max_length

    return f"{clipped[:cut].rstrip(' ,;:-')}..."


def _strip_title_prefix(text: str, title: str) -> str:
    clean_text = normalize_whitespace(text)
    clean_title = normalize_whitespace(title)
    if not clean_text or not clean_title:
        return clean_text
    if clean_text.lower().startswith(clean_title.lower()):
        remainder = clean_text[len(clean_title):].lstrip(" :-|.,")
        if remainder:
            return remainder
    return clean_text


def _looks_like_readable_excerpt(text: str) -> bool:
    sample = normalize_whitespace(text)[:240]
    if len(sample) < 40:
        return False

    alpha_count = sum(1 for ch in sample if ch.isalpha())
    weird_count = sum(1 for ch in sample if ch in "_|\\/<>`{}[]")
    space_count = sample.count(" ")

    if alpha_count / max(len(sample), 1) < 0.55:
        return False
    if weird_count / max(len(sample), 1) > 0.03:
        return False
    if space_count < 5:
        return False

    return True


def _looks_like_display_candidate(text: str) -> bool:
    sample = normalize_whitespace(text)[:240]
    if not sample:
        return False
    weird_count = sum(1 for ch in sample if ch in "_|\\/<>`{}[]")
    return weird_count / max(len(sample), 1) <= 0.03


def build_article_blurb(
    *,
    title: str,
    summary: str | None = None,
    snippet: str | None = None,
    text: str | None = None,
    max_length: int = 240,
) -> str:
    for candidate in (summary, snippet):
        compact = normalize_whitespace(candidate or "")
        if compact and _looks_like_display_candidate(compact):
            return _clip_blurb(compact, max_length)

    compact_text = _strip_title_prefix(text or "", title)
    if compact_text and _looks_like_readable_excerpt(compact_text):
        return _clip_blurb(compact_text, max_length)

    return _clip_blurb(title or "", max_length)
