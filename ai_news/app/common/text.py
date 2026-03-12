from __future__ import annotations

import re

from bs4 import BeautifulSoup


_whitespace_re = re.compile(r"\s+")


def strip_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(" ", strip=True)


def normalize_whitespace(text: str) -> str:
    return _whitespace_re.sub(" ", text or "").strip()
