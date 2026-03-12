from __future__ import annotations

import re


_AMOUNT_RE = re.compile(r"(?:\$|USD)\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([BbMmKk])?\b")


def parse_funding_amount(text: str) -> int | None:
    if not text:
        return None
    amounts = []
    for match in _AMOUNT_RE.finditer(text):
        try:
            value = float(match.group(1).replace(",", ""))
        except (TypeError, ValueError):
            continue
        suffix = (match.group(2) or "").lower()
        if suffix == "b":
            value *= 1_000_000_000
        elif suffix == "m":
            value *= 1_000_000
        elif suffix == "k":
            value *= 1_000
        amounts.append(int(value))
    return max(amounts) if amounts else None
