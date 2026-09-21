"""Tests for the deterministic intent classifier (TASK-093)."""

from __future__ import annotations

from services.agent.classifier import classify_intent
from services.agent.intents import IntentType


class TestClassifyIntent:
    def test_price_analytics_keywords(self) -> None:
        questions = [
            "Which products had the largest price increase?",
            "Show me the cheapest products in electronics",
            "What is the average price by category?",
            "Compare pricing across sources",
        ]
        for q in questions:
            result = classify_intent(q)
            assert result.intent == IntentType.PRICE_ANALYTICS, f"Failed for: {q}"
            assert result.confidence > 0.0

    def test_pipeline_status_keywords(self) -> None:
        questions = [
            "What is the pipeline status?",
            "Show me consumer lag",
            "What is the current processing rate?",
            "When was the last successful pipeline run?",
        ]
        for q in questions:
            result = classify_intent(q)
            assert result.intent == IntentType.PIPELINE_STATUS, f"Failed for: {q}"

    def test_data_quality_keywords(self) -> None:
        questions = [
            "Which data quality checks failed?",
            "Show me validation results",
            "What is the duplicate rate?",
            "How many invalid records were found?",
        ]
        for q in questions:
            result = classify_intent(q)
            assert result.intent == IntentType.DATA_QUALITY, f"Failed for: {q}"

    def test_source_health_keywords(self) -> None:
        questions = [
            "Which sources have failed their freshness checks?",
            "Show me source health status",
            "Why did observations drop yesterday?",
            "Is the Best Buy adapter working?",
        ]
        for q in questions:
            result = classify_intent(q)
            assert result.intent == IntentType.SOURCE_HEALTH, f"Failed for: {q}"

    def test_product_history_keywords(self) -> None:
        questions = [
            "Show me the product history for Widget X",
            "How many observations do we have for product 123?",
            "What are the past observations for this product?",
        ]
        for q in questions:
            result = classify_intent(q)
            assert result.intent == IntentType.PRODUCT_HISTORY, f"Failed for: {q}"

    def test_general_fallback(self) -> None:
        questions = [
            "Hello",
            "What can you do?",
            "Tell me about this platform",
            "Random question about nothing",
        ]
        for q in questions:
            result = classify_intent(q)
            assert result.intent == IntentType.GENERAL, f"Failed for: {q}"
            assert result.confidence == 1.0

    def test_empty_question(self) -> None:
        result = classify_intent("")
        assert result.intent == IntentType.GENERAL
        assert result.confidence == 1.0

    def test_whitespace_only(self) -> None:
        result = classify_intent("   ")
        assert result.intent == IntentType.GENERAL

    def test_case_insensitive(self) -> None:
        lower = classify_intent("what is the price of widgets?")
        upper = classify_intent("WHAT IS THE PRICE OF WIDGETS?")
        mixed = classify_intent("WhAt Is ThE pRiCe Of WiDgEtS?")
        assert lower.intent == upper.intent == mixed.intent == IntentType.PRICE_ANALYTICS

    def test_deterministic(self) -> None:
        question = "Which products had the largest price increase last week?"
        results = [classify_intent(question) for _ in range(10)]
        assert all(r.intent == results[0].intent for r in results)
        assert all(r.confidence == results[0].confidence for r in results)

    def test_raw_question_preserved(self) -> None:
        question = "  What is the PIPELINE STATUS?  "
        result = classify_intent(question)
        assert result.raw_question == question

    def test_confidence_bounded(self) -> None:
        for q in [
            "price",
            "price increase cost trend cheapest",
            "hello world",
        ]:
            result = classify_intent(q)
            assert 0.0 <= result.confidence <= 1.0

    def test_multi_keyword_boosts_confidence(self) -> None:
        single = classify_intent("What is the price?")
        multi = classify_intent("What is the price increase and cost trend?")
        assert multi.intent == single.intent == IntentType.PRICE_ANALYTICS
        assert multi.confidence >= single.confidence

    def test_no_live_llm_dependency(self) -> None:
        result = classify_intent("Show me the cheapest products")
        assert result.intent == IntentType.PRICE_ANALYTICS
        assert isinstance(result.confidence, float)
