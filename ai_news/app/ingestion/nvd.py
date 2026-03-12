"""NVD (National Vulnerability Database) connector for AI-related CVEs."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import List

import httpx

from app.common.text import normalize_whitespace
from app.common.time import utcnow
from app.ingestion.base import CandidateItem


NVD_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"

# AI/ML-related keywords to search for in NVD
NVD_KEYWORDS = [
    "pytorch", "tensorflow", "langchain", "openai", "anthropic",
    "cuda", "huggingface", "transformers", "llama", "ollama",
    "vllm", "onnx", "keras", "scikit-learn", "numpy",
    "jupyter", "mlflow", "ray", "triton", "tensorrt",
]

# Rate limit: 5 requests per 30 seconds without API key
RATE_LIMIT_DELAY = 6.5


class NVDConnector:
    def __init__(self, source_id: str):
        self.source_id = source_id

    def fetch_candidates(
        self,
        now: datetime | None = None,
        lookback_days: int = 7,
    ) -> List[CandidateItem]:
        now = now or utcnow()
        cutoff = now - timedelta(days=lookback_days)
        items: List[CandidateItem] = []
        seen_ids: set[str] = set()

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            for i, keyword in enumerate(NVD_KEYWORDS):
                if i > 0:
                    time.sleep(RATE_LIMIT_DELAY)
                try:
                    params = {
                        "keywordSearch": keyword,
                        "resultsPerPage": 20,
                    }
                    response = client.get(NVD_API_URL, params=params)
                    response.raise_for_status()
                    data = response.json()
                except Exception:
                    continue

                for vuln in data.get("vulnerabilities", []):
                    cve = vuln.get("cve", {})
                    cve_id = cve.get("id")
                    if not cve_id or cve_id in seen_ids:
                        continue

                    published_str = cve.get("published", "")
                    published_at = None
                    if published_str:
                        try:
                            published_at = datetime.fromisoformat(
                                published_str.replace("Z", "+00:00")
                            )
                            if published_at.tzinfo is None:
                                published_at = published_at.replace(tzinfo=timezone.utc)
                        except ValueError:
                            pass

                    if published_at and published_at < cutoff:
                        continue

                    seen_ids.add(cve_id)

                    descriptions = cve.get("descriptions", [])
                    en_desc = ""
                    for desc in descriptions:
                        if desc.get("lang") == "en":
                            en_desc = desc.get("value", "")
                            break

                    title = f"{cve_id}: {normalize_whitespace(en_desc[:200])}"
                    url = f"https://nvd.nist.gov/vuln/detail/{cve_id}"

                    items.append(
                        CandidateItem(
                            source_id=self.source_id,
                            external_id=cve_id,
                            url=url,
                            title=title,
                            snippet=normalize_whitespace(en_desc),
                            published_at=published_at,
                            fetched_at=now,
                        )
                    )

        return items
