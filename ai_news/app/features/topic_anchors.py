from __future__ import annotations

from functools import lru_cache
from typing import Dict, List

import numpy as np

from app.common.embeddings import embed_text, embed_texts


TOPIC_ANCHORS: Dict[str, List[str]] = {
    "llms": ["large language model", "foundation model", "LLM", "instruction tuning"],
    "multimodal": ["multimodal model", "vision-language model", "text and image model"],
    "agents": ["AI agent", "tool use", "function calling", "agent framework"],
    "robotics": ["robotics", "robot", "manipulation", "autonomy"],
    "vision": ["computer vision", "image recognition", "object detection"],
    "audio_speech": ["speech recognition", "text to speech", "audio model"],
    "hardware_chips": ["GPU", "TPU", "AI chip", "accelerator", "HBM"],
    "open_source": ["open source", "GitHub", "repository", "Apache license"],
    "startups_funding": ["startup", "funding round", "venture", "Series A"],
    "enterprise_apps": ["enterprise AI", "business AI", "productivity", "SaaS"],
    "safety_policy": ["AI safety", "policy", "regulation", "governance"],
    "research_methods": ["research paper", "benchmark", "dataset", "experiment"],
}


@lru_cache(maxsize=1)
def _anchor_embeddings() -> Dict[str, np.ndarray]:
    embeddings: Dict[str, np.ndarray] = {}
    for topic, phrases in TOPIC_ANCHORS.items():
        emb = embed_texts(phrases)
        embeddings[topic] = emb
    return embeddings


def topic_probabilities(text: str) -> Dict[str, float]:
    """Compute topic probabilities from text (title, or title+body excerpt).

    Accepts any text input — callers should pass title+body for full-content
    classification, or title-only when body is unavailable.
    """
    text_emb = embed_text(text)
    sims = []
    topics = list(TOPIC_ANCHORS.keys())
    anchor_embs = _anchor_embeddings()
    for topic in topics:
        emb = anchor_embs[topic]
        sim = float(np.max(emb @ text_emb))
        sims.append(sim)
    sims_arr = np.array(sims, dtype=np.float32)
    temp = 0.07
    exp_scores = np.exp((sims_arr / temp) - np.max(sims_arr))
    probs = exp_scores / exp_scores.sum()
    return {topic: float(prob) for topic, prob in zip(topics, probs)}
