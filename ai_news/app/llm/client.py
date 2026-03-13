from __future__ import annotations

import json
import hashlib
import logging
import time
from typing import Dict

import httpx

from app.config import get_settings
from app.llm.cache import get_cached, set_cached
from app.llm.prompts import CLASSIFY_PROMPT, SUMMARY_PROMPT, EVENT_TYPES, TOPICS

logger = logging.getLogger(__name__)


def _hash_text(title: str, text: str) -> str:
    payload = f"{title}\n{text[:2000]}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LLMClient:
    def __init__(self):
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        if self.settings.llm_provider == "openai":
            return bool(self.settings.openai_api_key)
        if self.settings.llm_provider == "openrouter":
            return bool(self.settings.openrouter_api_key)
        return False

    def _request_with_retry(self, url: str, headers: dict, payload: dict) -> dict:
        timeout = httpx.Timeout(
            timeout=self.settings.llm_request_timeout_seconds,
            connect=min(10, self.settings.llm_request_timeout_seconds),
        )
        retries = max(0, int(self.settings.llm_max_retries))
        backoff = max(0.1, float(self.settings.llm_retry_backoff_seconds))
        attempt = 0
        last_exc: Exception | None = None

        while attempt <= retries:
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.post(url, headers=headers, json=payload)
                # Retry throttling/server failures once or twice.
                if response.status_code in {429, 500, 502, 503, 504}:
                    response.raise_for_status()
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.NetworkError) as exc:
                last_exc = exc
                should_retry = attempt < retries
                if isinstance(exc, httpx.HTTPStatusError):
                    status = exc.response.status_code if exc.response is not None else None
                    should_retry = should_retry and status in {429, 500, 502, 503, 504}
                if not should_retry:
                    raise
                time.sleep(backoff * (2**attempt))
                attempt += 1

        # Defensive fallback (loop either returns or raises).
        if last_exc:
            raise last_exc
        raise RuntimeError("LLM request failed")

    def _call_openai(self, messages: list[dict], *, json_object: bool = False) -> str:
        if not self.settings.openai_api_key:
            raise RuntimeError("Missing OPENAI_API_KEY")
        headers = {"Authorization": f"Bearer {self.settings.openai_api_key}", "Content-Type": "application/json"}
        payload = {"model": self.settings.openai_model, "messages": messages, "temperature": 0.2}
        if json_object:
            payload["response_format"] = {"type": "json_object"}
        data = self._request_with_retry("https://api.openai.com/v1/chat/completions", headers, payload)
        return data["choices"][0]["message"]["content"]

    def _call_openrouter(self, messages: list[dict], *, json_object: bool = False) -> str:
        if not self.settings.openrouter_api_key:
            raise RuntimeError("Missing OPENROUTER_API_KEY")
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.openrouter_app_url,
            "X-Title": self.settings.openrouter_app_title,
        }
        payload = {"model": self.settings.openrouter_model, "messages": messages, "temperature": 0.4}
        if json_object:
            payload["response_format"] = {"type": "json_object"}
        data = self._request_with_retry(
            f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions",
            headers,
            payload,
        )
        return data["choices"][0]["message"]["content"]

    def chat(self, messages: list[dict], *, json_object: bool = False) -> str:
        if not self.enabled:
            raise RuntimeError("LLM disabled")
        if self.settings.llm_provider == "openrouter":
            return self._call_openrouter(messages, json_object=json_object)
        return self._call_openai(messages, json_object=json_object)

    def _translate_cached_json(
        self,
        *,
        cache_namespace: str,
        payload: dict,
        instruction: str,
    ) -> dict | None:
        cache_key = (
            f"{cache_namespace}:"
            f"{hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()}"
        )
        cached = get_cached(cache_key)
        if cached:
            value = cached.get("value")
            return value if isinstance(value, dict) else None
        if not self.enabled:
            return None
        try:
            content = self.chat(
                [
                    {"role": "system", "content": "Translate to zh-CN. Return strict JSON only."},
                    {"role": "user", "content": instruction.format(payload=json.dumps(payload, ensure_ascii=False))},
                ],
                json_object=True,
            )
            parsed = json.loads(content or "{}")
        except Exception:
            return None
        if not isinstance(parsed, dict):
            return None
        set_cached(cache_key, {"value": parsed})
        return parsed

    def classify_event_and_topics(self, title: str, text: str) -> Dict[str, object]:
        cache_key = f"classify:{_hash_text(title, text)}"
        cached = get_cached(cache_key)
        if cached:
            return cached
        if not self.enabled:
            return {"event_type": "OTHER", "topics": {topic: 0.0 for topic in TOPICS}}
        prompt = CLASSIFY_PROMPT.format(event_types=", ".join(EVENT_TYPES), topics=", ".join(TOPICS), text=text[:2000])
        raw = self.chat(
            [
                {"role": "system", "content": "You are a classifier. Return strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            json_object=True,
        )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"event_type": "OTHER", "topics": {topic: 0.0 for topic in TOPICS}}
        set_cached(cache_key, data)
        return data

    def summarize(self, title: str, text: str) -> str | None:
        cache_key = f"summary:{_hash_text(title, text)}"
        cached = get_cached(cache_key)
        if cached:
            return cached.get("summary")
        if not self.enabled:
            return None
        prompt = SUMMARY_PROMPT.format(text=text[:2000])
        summary = self.chat(
            [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            json_object=False,
        )
        summary = summary.strip()
        set_cached(cache_key, {"summary": summary})
        return summary

    _SECTION_PROMPTS = {
        "all": "Summarize these AI news items into a concise headline and executive summary.",
        "news": "Summarize today's key AI industry news, product launches, funding, and business developments. Focus on what matters for industry practitioners.",
        "research": "Highlight the most notable AI research papers and scientific advances. Focus on novel methods, benchmark results, and emerging techniques.",
        "github": "Summarize the trending open-source AI tools, libraries, and notable releases. Focus on what developers should know about.",
    }

    _EMPTY_SECTION_HEADLINES = {
        "all": "Daily AI Pulse",
        "news": "No major industry news today",
        "research": "No notable research papers today",
        "github": "No trending repos today",
    }

    def generate_section_digest(self, items: list[dict], content_type: str = "all") -> dict:
        """Generate a digest for a specific content type section."""
        if not items:
            return {
                "headline": self._EMPTY_SECTION_HEADLINES.get(content_type, "Daily AI Pulse"),
                "executiveSummary": f"No {content_type} updates from the last 24 hours.",
                "llmAuthored": False,
            }
        if not self.enabled:
            return {
                "headline": items[0].get("title") or self._EMPTY_SECTION_HEADLINES.get(content_type, "Daily AI Pulse"),
                "executiveSummary": items[0].get("summary") or f"Key AI {content_type} updates from the last 24 hours.",
                "llmAuthored": False,
            }

        prompt_text = self._SECTION_PROMPTS.get(content_type, self._SECTION_PROMPTS["all"])
        cache_key = f"section_digest:{content_type}:{hashlib.sha256(json.dumps(items, sort_keys=True).encode('utf-8')).hexdigest()}"
        cached = get_cached(cache_key)
        if cached:
            return cached

        try:
            content = self.chat(
                [
                    {"role": "system", "content": "You are a newsroom editor. Return strict JSON only."},
                    {
                        "role": "user",
                        "content": (
                            f"{prompt_text}\n\n"
                            f"ITEMS:\n{json.dumps(items)}\n\n"
                            "Return JSON with keys: headline, executiveSummary."
                        ),
                    },
                ],
                json_object=True,
            )
            parsed = json.loads(content or "{}")
            result = {
                "headline": parsed.get("headline") or items[0].get("title") or "Daily AI Pulse",
                "executiveSummary": parsed.get("executiveSummary") or items[0].get("summary") or "Key AI updates.",
                "llmAuthored": True,
            }
        except Exception:
            result = {
                "headline": items[0].get("title") or "Daily AI Pulse",
                "executiveSummary": items[0].get("summary") or "Key AI updates from the last 24 hours.",
                "llmAuthored": False,
            }

        set_cached(cache_key, result)
        return result

    def generate_digest_copy(self, items: list[dict]) -> dict:
        if not items:
            return {
                "headline": "Daily AI Pulse",
                "executiveSummary": "Key AI updates from the last 24 hours.",
                "llmAuthored": False,
            }
        if not self.enabled:
            return {
                "headline": items[0].get("title") or "Daily AI Pulse",
                "executiveSummary": items[0].get("summary") or "Key AI updates from the last 24 hours.",
                "llmAuthored": False,
            }

        cache_key = f"digest_copy:{hashlib.sha256(json.dumps(items, sort_keys=True).encode('utf-8')).hexdigest()}"
        cached = get_cached(cache_key)
        if cached:
            return cached

        try:
            content = self.chat(
                [
                    {"role": "system", "content": "You are a newsroom editor. Return strict JSON only."},
                    {
                        "role": "user",
                        "content": (
                            "Summarize these AI news items into a concise headline and executive summary.\n\n"
                            f"ITEMS:\n{json.dumps(items)}\n\n"
                            "Return JSON with keys: headline, executiveSummary."
                        ),
                    },
                ],
                json_object=True,
            )
            parsed = json.loads(content or "{}")
            result = {
                "headline": parsed.get("headline") or items[0].get("title") or "Daily AI Pulse",
                "executiveSummary": parsed.get("executiveSummary")
                or items[0].get("summary")
                or "Key AI updates from the last 24 hours.",
                "llmAuthored": True,
            }
        except Exception:
            result = {
                "headline": items[0].get("title") or "Daily AI Pulse",
                "executiveSummary": items[0].get("summary") or "Key AI updates from the last 24 hours.",
                "llmAuthored": False,
            }

        set_cached(cache_key, result)
        return result

    def translate_digest(self, digest: dict) -> dict:
        if not self.enabled:
            return digest
        try:
            content = self.chat(
                [
                    {"role": "system", "content": "Translate to zh-CN. Return strict JSON only."},
                    {
                        "role": "user",
                        "content": (
                            "Translate the following AI News Digest into professional simplified Chinese (zh-CN).\n\n"
                            f"DIGEST:\n{json.dumps(digest)}\n\n"
                            "Return the same JSON structure with translated text fields only."
                        ),
                    },
                ],
                json_object=True,
            )
            parsed = json.loads(content or "{}")
        except Exception:
            return digest

        if not isinstance(parsed, dict):
            return digest

        # Preserve sources/tags since translation models may rewrite arrays.
        original_items = digest.get("items") if isinstance(digest.get("items"), list) else []
        parsed_items = parsed.get("items") if isinstance(parsed.get("items"), list) else None
        if isinstance(parsed_items, list) and original_items:
            merged_items = []
            for idx, item in enumerate(parsed_items):
                if not isinstance(item, dict):
                    continue
                base = original_items[idx] if idx < len(original_items) and isinstance(original_items[idx], dict) else {}
                merged_items.append(
                    {
                        **item,
                        "sources": base.get("sources", item.get("sources", [])),
                        "tags": base.get("tags", item.get("tags", [])),
                    }
                )
            parsed["items"] = merged_items

        breaking = parsed.get("breakingAlert")
        if isinstance(breaking, dict) and isinstance(digest.get("breakingAlert"), dict):
            breaking["sources"] = digest["breakingAlert"].get("sources", breaking.get("sources", []))
            parsed["breakingAlert"] = breaking

        return {**digest, **parsed}

    def translate_digest_sections(self, digests: dict[str, dict]) -> tuple[dict[str, dict], str]:
        if not digests:
            return digests, "ready"
        payload = {
            "digests": {
                key: {
                    "headline": value.get("headline", ""),
                    "executiveSummary": value.get("executiveSummary", ""),
                }
                for key, value in digests.items()
                if isinstance(value, dict)
            }
        }
        parsed = self._translate_cached_json(
            cache_namespace="translate_digest_sections",
            payload=payload,
            instruction=(
                "Translate the following digest sections into professional simplified Chinese (zh-CN).\n\n"
                "PAYLOAD:\n{payload}\n\n"
                "Return the same JSON structure with translated headline and executiveSummary fields only."
            ),
        )
        translated = parsed.get("digests") if isinstance(parsed, dict) else None
        if not isinstance(translated, dict):
            return digests, "unavailable"

        merged: dict[str, dict] = {}
        for key, value in digests.items():
            base = value if isinstance(value, dict) else {}
            localized = translated.get(key) if isinstance(translated.get(key), dict) else {}
            merged[key] = {
                **base,
                "headline": localized.get("headline") or base.get("headline"),
                "executiveSummary": localized.get("executiveSummary") or base.get("executiveSummary"),
            }
        return merged, "ready"

    def translate_news_items(self, items: list[dict]) -> tuple[list[dict], str]:
        if not items:
            return items, "ready"
        payload = {
            "items": [
                {
                    "title": item.get("title", ""),
                    "summary": item.get("summary", ""),
                    "tags": item.get("tags", []),
                }
                for item in items
            ]
        }
        parsed = self._translate_cached_json(
            cache_namespace="translate_news_items",
            payload=payload,
            instruction=(
                "Translate the following news items into professional simplified Chinese (zh-CN).\n\n"
                "PAYLOAD:\n{payload}\n\n"
                "Return JSON with the same structure and translated title, summary, and tags fields only."
            ),
        )
        translated = parsed.get("items") if isinstance(parsed, dict) else None
        if not isinstance(translated, list):
            return items, "unavailable"

        merged: list[dict] = []
        for idx, item in enumerate(items):
            localized = translated[idx] if idx < len(translated) and isinstance(translated[idx], dict) else {}
            tags = localized.get("tags")
            merged_item = {
                **item,
                "title": localized.get("title") or item.get("title"),
                "summary": localized.get("summary") or item.get("summary"),
            }
            if isinstance(tags, list) and tags:
                merged_item["tags"] = [str(tag) for tag in tags]
            merged.append(merged_item)
        return merged, "ready"

    def translate_graph_clusters(self, clusters: list[dict]) -> tuple[list[dict], str]:
        if not clusters:
            return clusters, "ready"
        payload = {
            "clusters": [
                {
                    "headline": cluster.get("headline", ""),
                    "articles": [
                        {
                            "title": article.get("title", ""),
                        }
                        for article in cluster.get("articles", [])
                        if isinstance(article, dict)
                    ],
                }
                for cluster in clusters
            ]
        }
        parsed = self._translate_cached_json(
            cache_namespace="translate_signal_map_clusters",
            payload=payload,
            instruction=(
                "Translate the following signal map cluster headlines and article titles into professional simplified Chinese (zh-CN).\n\n"
                "PAYLOAD:\n{payload}\n\n"
                "Return JSON with the same structure and translated headline/title fields only."
            ),
        )
        translated = parsed.get("clusters") if isinstance(parsed, dict) else None
        if not isinstance(translated, list):
            return clusters, "unavailable"

        merged_clusters: list[dict] = []
        for idx, cluster in enumerate(clusters):
            localized_cluster = translated[idx] if idx < len(translated) and isinstance(translated[idx], dict) else {}
            localized_articles = localized_cluster.get("articles") if isinstance(localized_cluster.get("articles"), list) else []
            merged_articles: list[dict] = []
            for article_idx, article in enumerate(cluster.get("articles", [])):
                if not isinstance(article, dict):
                    continue
                localized_article = (
                    localized_articles[article_idx]
                    if article_idx < len(localized_articles) and isinstance(localized_articles[article_idx], dict)
                    else {}
                )
                merged_articles.append({
                    **article,
                    "title": localized_article.get("title") or article.get("title"),
                })
            merged_clusters.append({
                **cluster,
                "headline": localized_cluster.get("headline") or cluster.get("headline"),
                "articles": merged_articles,
            })
        return merged_clusters, "ready"

    def judge_significance(
        self, title: str, source_name: str, event_type: str, text_preview: str
    ) -> tuple[float, str] | None:
        """Run LLM significance judge. Returns (score, reasoning) or None."""
        from app.scoring.llm_judge import (
            build_significance_prompt,
            parse_llm_response,
            llm_significance_score,
        )

        cache_key = f"judge:{_hash_text(title, f'{source_name}|{event_type}|{text_preview or ""}')}"
        cached = get_cached(cache_key)
        if cached:
            return cached.get("score"), cached.get("reasoning")

        if not self.enabled:
            return None

        prompt = build_significance_prompt(title, source_name, event_type, text_preview)
        try:
            response = self.chat(
                [
                    {"role": "system", "content": "You are a classifier. Return strict JSON only."},
                    {"role": "user", "content": prompt},
                ],
                json_object=True,
            )
            scores = parse_llm_response(response)
            if scores is None:
                return None
            impact, breadth, novelty = scores
            score = llm_significance_score(impact, breadth, novelty)
            reasoning = f"Impact={impact}, Breadth={breadth}, Novelty={novelty}"
            set_cached(cache_key, {"score": score, "reasoning": reasoning})
            return score, reasoning
        except Exception:
            logger.exception("LLM judge failed")
            return None
