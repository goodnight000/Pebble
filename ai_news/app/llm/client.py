from __future__ import annotations

import json
import hashlib
import logging
import time
from typing import Dict

import httpx

from app.common.blurbs import build_article_blurb
from app.common.text import normalize_whitespace
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
                    {"role": "system", "content": "You are a professional translator specializing in AI/tech content. Translate to simplified Chinese (zh-CN). Preserve all JSON structure, URLs, technical terms, company/product names, and proper nouns in their original form. Return strict JSON only."},
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
                {"role": "system", "content": "You are an AI news classifier. Return strict JSON only with keys: event_type (string), topics (object mapping topic names to float probabilities)."},
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
            cached_summary = normalize_whitespace(cached.get("summary") or "")
            if cached_summary:
                return cached_summary
        if not self.enabled:
            return None
        prompt = SUMMARY_PROMPT.format(text=text[:2000])
        summary = ""
        try:
            summary = self.chat(
                [
                    {"role": "system", "content": "You are an AI news editor. Write concise, factual summaries. Return only the summary text, no preamble."},
                    {"role": "user", "content": prompt},
                ],
                json_object=False,
            )
        except Exception:
            logger.exception("LLM summarize failed")

        normalized_summary = normalize_whitespace(summary)
        if not normalized_summary:
            try:
                structured = self.chat(
                    [
                        {"role": "system", "content": "You are an AI news editor. Return strict JSON only with one key: summary. The summary must be concise, factual, and 2-3 sentences maximum."},
                        {"role": "user", "content": prompt},
                    ],
                    json_object=True,
                )
                parsed = json.loads(structured or "{}")
                normalized_summary = normalize_whitespace(parsed.get("summary") or "")
            except Exception:
                logger.exception("LLM summarize JSON retry failed")

        if not normalized_summary:
            return None

        summary_value = build_article_blurb(title=title, summary=normalized_summary)
        if not summary_value:
            return None
        set_cached(cache_key, {"summary": summary_value})
        return summary_value

    _SECTION_PROMPTS = {
        "all": "Synthesize these AI news items into a compelling headline and 2-3 sentence executive summary. Lead with the single most important development, then note 1-2 other key themes.",
        "news": "Synthesize today's AI industry news into a headline and executive summary. Focus on the most consequential product launches, funding rounds, partnerships, or strategic moves. Mention specific company names and concrete numbers.",
        "research": "Synthesize today's AI research into a headline and executive summary. Lead with the most impactful finding, then note other notable papers. Explain what was found and why it matters — not just that a paper was published.",
        "github": "Synthesize today's trending open-source AI tools into a headline and executive summary. Focus on what developers can actually use — new libraries, framework updates, or tools that solve real problems.",
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
                    {"role": "system", "content": "You write headlines and summaries for an AI news digest. You may ONLY reference stories from the numbered list below. NEVER invent stories. Return strict JSON only."},
                    {
                        "role": "user",
                        "content": self._build_digest_user_prompt(items, prompt_text),
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

    @staticmethod
    def _build_digest_user_prompt(items: list[dict], task_text: str) -> str:
        """Build a digest prompt with explicit numbered story list to prevent hallucination."""
        titles = "\n".join(f"  {i+1}. {item.get('title', '?')}" for i, item in enumerate(items))
        return (
            f"AVAILABLE STORIES (you may ONLY reference these — nothing else exists):\n{titles}\n\n"
            f"Full items with summaries:\n{json.dumps(items)}\n\n"
            f"Task: {task_text}\n\n"
            "RULES:\n"
            "- Every company, product, or fact you mention MUST come from the numbered list above\n"
            "- If a story is not in the list, it does not exist — do not invent it\n"
            "- Prefer shorter, accurate output over longer, padded output\n\n"
            'Return JSON: {"headline": "...", "executiveSummary": "..."}'
        )

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
                    {"role": "system", "content": "You write headlines and summaries for an AI news digest. You may ONLY reference stories from the numbered list below. NEVER invent stories. Return strict JSON only."},
                    {
                        "role": "user",
                        "content": self._build_digest_user_prompt(items, "Synthesize these into a headline and executive summary."),
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

    def generate_longform_digest(self, articles: list[dict]) -> dict | None:
        """Generate a longform daily digest article with personality and inline source links."""
        from app.llm.prompts import LONGFORM_DIGEST_SYSTEM_PROMPT, LONGFORM_DIGEST_USER_PROMPT

        if not articles:
            return None
        if not self.enabled:
            return None

        cache_key = f"longform_digest:{hashlib.sha256(json.dumps(articles, sort_keys=True).encode('utf-8')).hexdigest()}"
        cached = get_cached(cache_key)
        if cached:
            return cached

        try:
            content = self.chat(
                [
                    {"role": "system", "content": LONGFORM_DIGEST_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": LONGFORM_DIGEST_USER_PROMPT.format(
                            articles_json=json.dumps(articles, ensure_ascii=False)
                        ),
                    },
                ],
                json_object=True,
            )
            parsed = json.loads(content or "{}")
            if not parsed.get("title") or not parsed.get("sections"):
                return None
            set_cached(cache_key, parsed)
            return parsed
        except Exception:
            logger.exception("Longform digest generation failed")
            return None

    def translate_longform_digest(self, digest: dict) -> dict | None:
        """Translate a longform digest to zh-CN, preserving markdown links."""
        if not digest:
            return None
        payload = {
            "title": digest.get("title", ""),
            "subtitle": digest.get("subtitle", ""),
            "sections": [
                {"heading": s.get("heading", ""), "body": s.get("body", "")}
                for s in digest.get("sections", [])
            ],
            "sign_off": digest.get("sign_off", ""),
        }
        result = self._translate_cached_json(
            cache_namespace="translate_longform_digest",
            payload=payload,
            instruction=(
                "Translate the following AI news digest into professional simplified Chinese (zh-CN). "
                "Preserve all markdown formatting and [link](url) references exactly. "
                "Translate the prose but keep URLs, proper nouns (company/product names), and technical terms unchanged.\n\n"
                "PAYLOAD:\n{payload}\n\n"
                "Return the same JSON structure with translated text fields."
            ),
        )
        if not isinstance(result, dict) or not result.get("title"):
            return None
        return {**digest, **result}

    def translate_digest(self, digest: dict) -> dict:
        if not self.enabled:
            return digest
        try:
            content = self.chat(
                [
                    {"role": "system", "content": "You are a professional translator specializing in AI/tech content. Translate to simplified Chinese (zh-CN). Preserve all JSON structure, URLs, technical terms, company/product names, and proper nouns. Return strict JSON only."},
                    {
                        "role": "user",
                        "content": (
                            "Translate this AI News Digest into professional simplified Chinese (zh-CN).\n\n"
                            f"DIGEST:\n{json.dumps(digest)}\n\n"
                            "Rules:\n"
                            "- Translate text fields (headline, executiveSummary, title, summary) only\n"
                            "- Preserve sources, tags, URLs, and structural fields unchanged\n"
                            "- Keep company/product names and technical terms in English\n"
                            "- Return the same JSON structure"
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
                "Translate these AI digest section headlines and summaries into professional simplified Chinese (zh-CN).\n\n"
                "PAYLOAD:\n{payload}\n\n"
                "Rules:\n"
                "- Translate headline and executiveSummary fields only\n"
                "- Keep company/product names and technical terms in English\n"
                "- Headlines should be punchy and natural in Chinese, not literal translations\n"
                "- Return the same JSON structure"
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
                "Translate these AI news items into professional simplified Chinese (zh-CN).\n\n"
                "PAYLOAD:\n{payload}\n\n"
                "Rules:\n"
                "- Translate title, summary, and tags fields only\n"
                "- Keep company names (OpenAI, Google, Meta), product names, and technical terms in English\n"
                "- Use natural Chinese phrasing, not word-for-word translation\n"
                "- Return the same JSON structure"
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
                "Translate these AI news cluster headlines and article titles into professional simplified Chinese (zh-CN).\n\n"
                "PAYLOAD:\n{payload}\n\n"
                "Rules:\n"
                "- Translate headline and title fields only\n"
                "- Keep company/product names, model names, and technical terms in English\n"
                "- Use concise, journalistic Chinese phrasing\n"
                "- Return the same JSON structure"
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
                    {"role": "system", "content": "You are an AI industry analyst scoring news significance. Score conservatively — most articles are 3-6 on each dimension. Return strict JSON only."},
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
