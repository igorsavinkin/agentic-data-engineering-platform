"""Deterministic intent classifier for the LangGraph Data Engineer Agent.

Maps natural-language user questions to structured agent intents using
keyword-based matching. Deterministic for test inputs — no live LLM
calls required.
"""

from __future__ import annotations

import re

from services.agent.intents import ClassifiedIntent, IntentType

_INTENT_KEYWORDS: dict[IntentType, list[str]] = {
    IntentType.PRICE_ANALYTICS: [
        "price",
        "pricing",
        "cost",
        "cheapest",
        "expensive",
        "price change",
        "price increase",
        "price decrease",
        "price mover",
        "price trend",
        "average price",
        "price statistics",
        "price comparison",
    ],
    IntentType.PIPELINE_STATUS: [
        "pipeline",
        "pipeline status",
        "pipeline health",
        "consumer lag",
        "processing rate",
        "throughput",
        "last successful",
        "pipeline run",
        "job status",
        "etl status",
    ],
    IntentType.DATA_QUALITY: [
        "quality",
        "data quality",
        "validation",
        "check failed",
        "quality check",
        "quality result",
        "failed records",
        "invalid records",
        "duplicate rate",
        "null rate",
    ],
    IntentType.SOURCE_HEALTH: [
        "source",
        "sources",
        "source health",
        "source status",
        "ingestion",
        "adapter",
        "source failed",
        "source degradation",
        "source freshness",
        "freshness",
        "observations drop",
        "stopped producing",
    ],
    IntentType.PRODUCT_HISTORY: [
        "history",
        "product history",
        "observations",
        "observation count",
        "product look",
        "past observations",
        "historical",
        "time series",
        "trend",
    ],
}

_FALLBACK_INTENT = IntentType.GENERAL


def classify_intent(question: str) -> ClassifiedIntent:
    """Classify a user question into an agent intent.

    Uses keyword matching against known intent patterns. Returns a
    ClassifiedIntent with confidence based on the number of keyword
    matches. Unrecognized questions fall back to GENERAL intent.

    Deterministic: the same input always produces the same output.
    """
    normalized = question.strip().lower()

    if not normalized:
        return ClassifiedIntent(
            intent=_FALLBACK_INTENT,
            confidence=1.0,
            raw_question=question,
        )

    best_intent = _FALLBACK_INTENT
    best_score = 0

    for intent, keywords in _INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if _match_keyword(normalized, kw))
        if score > best_score:
            best_score = score
            best_intent = intent

    if best_score == 0:
        return ClassifiedIntent(
            intent=_FALLBACK_INTENT,
            confidence=1.0,
            raw_question=question,
        )

    max_possible = len(_INTENT_KEYWORDS[best_intent])
    confidence = min(best_score / max(max_possible * 0.3, 1), 1.0)

    return ClassifiedIntent(
        intent=best_intent,
        confidence=round(confidence, 2),
        raw_question=question,
    )


def _match_keyword(text: str, keyword: str) -> bool:
    """Check if a keyword appears in the text as a word-boundary match."""
    pattern = r"\b" + re.escape(keyword) + r"\b"
    return bool(re.search(pattern, text))
