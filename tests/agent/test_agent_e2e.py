"""End-to-end agent tests verifying tool usage, routing, and response composition.

These tests exercise the full graph pipeline (classify -> route -> tool -> compose)
with mocked providers to verify the agent uses controlled tools rather than
hallucinating platform state.  All dependencies are deterministic.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from services.agent.graph import (
    GraphContext,
    build_agent_graph,
)
from services.agent.intents import IntentType


def _fake_db(**overrides: Any) -> MagicMock:
    db = MagicMock()
    db.list_tables.return_value = overrides.get("tables", ["products"])
    db.get_columns.return_value = overrides.get(
        "columns",
        [
            {"name": "id", "data_type": "integer", "is_nullable": False, "is_primary_key": True},
            {"name": "name", "data_type": "text", "is_nullable": False, "is_primary_key": False},
            {"name": "price", "data_type": "real", "is_nullable": True, "is_primary_key": False},
        ],
    )
    db.get_row_count.return_value = overrides.get("row_count", 42)
    db.execute.return_value = overrides.get("rows", [])
    return db


def _fake_pipeline_provider(
    runs: list[dict[str, Any]] | None = None,
    total: int = 5,
    sources: list[dict[str, Any]] | None = None,
    lag: list[dict[str, Any]] | None = None,
) -> MagicMock:
    provider = MagicMock()
    provider.list_recent_runs.return_value = runs or []
    provider.get_total_run_count.return_value = total
    provider.list_source_health.return_value = sources or []
    provider.get_lag_samples.return_value = lag or []
    return provider


def _fake_quality_provider(
    checks: list[dict[str, Any]] | None = None,
    summary: list[dict[str, Any]] | None = None,
) -> MagicMock:
    provider = MagicMock()
    provider.list_recent_checks.return_value = checks or []
    provider.get_quality_summary.return_value = summary or []
    return provider


def _fake_source_health_provider(
    sources: list[dict[str, Any]] | None = None,
) -> MagicMock:
    provider = MagicMock()
    provider.list_source_health.return_value = sources or []
    return provider


class TestEndToEndPipelineStatus:
    def test_pipeline_status_question_uses_tool(self) -> None:
        runs = [
            {
                "run_type": "full_load",
                "overall_status": "healthy",
                "started_at": "2026-09-20T10:00:00+00:00",
                "finished_at": "2026-09-20T11:00:00+00:00",
                "records_loaded": 1000,
                "error_message": None,
            },
        ]
        ctx = GraphContext(pipeline_status_provider=_fake_pipeline_provider(runs=runs))
        graph = build_agent_graph(ctx)

        state = graph.run("What is the status of the pipeline?")

        assert state.response is not None
        assert state.response.intent == IntentType.PIPELINE_STATUS
        assert len(state.tool_calls) == 1
        assert state.tool_calls[0].tool_name == "get_pipeline_status"
        assert len(state.tool_results) == 1
        assert state.tool_results[0].success is True
        assert state.tool_results[0].tool_name == "get_pipeline_status"
        assert "get_pipeline_status" in state.response.sources

    def test_pipeline_status_answer_contains_tool_data(self) -> None:
        runs = [
            {
                "run_type": "incremental",
                "overall_status": "healthy",
                "started_at": "2026-09-20T10:00:00+00:00",
                "finished_at": "2026-09-20T10:30:00+00:00",
                "records_loaded": 500,
                "error_message": None,
            },
        ]
        ctx = GraphContext(pipeline_status_provider=_fake_pipeline_provider(runs=runs, total=1))
        graph = build_agent_graph(ctx)

        state = graph.run("What is the pipeline health?")

        assert state.response is not None
        assert state.response.answer
        assert state.response.intent == IntentType.PIPELINE_STATUS
        assert state.tool_results[0].success is True


class TestEndToEndDataQuality:
    def test_data_quality_question_uses_tool(self) -> None:
        checks = [
            {
                "check_name": "null_check",
                "severity": "error",
                "passed": False,
                "message": "10 null values found",
                "checked_at": "2026-09-20T12:00:00+00:00",
                "records_checked": 1000,
                "failed_records": 10,
                "details": None,
            },
        ]
        summary = [
            {
                "check_name": "null_check",
                "total_runs": 5,
                "passed_runs": 3,
                "failed_runs": 2,
                "last_checked_at": "2026-09-20T12:00:00+00:00",
                "severity": "error",
            },
        ]
        ctx = GraphContext(
            data_quality_provider=_fake_quality_provider(checks=checks, summary=summary)
        )
        graph = build_agent_graph(ctx)

        state = graph.run("Why did the quality check fail yesterday?")

        assert state.response is not None
        assert state.response.intent == IntentType.DATA_QUALITY
        assert len(state.tool_calls) == 1
        assert state.tool_calls[0].tool_name == "get_data_quality"
        assert state.tool_results[0].success is True


class TestEndToEndSourceHealth:
    def test_source_freshness_question_uses_tool(self) -> None:
        sources = [
            {
                "source_name": "best_buy",
                "overall_status": "stale",
                "degradation_state": "stale",
                "freshness_state": "stale",
                "freshness_age_seconds": 172800.0,
                "assessed_at": "2026-09-20T12:00:00+00:00",
                "reasons": ["no_data"],
                "signals": None,
            },
        ]
        ctx = GraphContext(source_health_provider=_fake_source_health_provider(sources=sources))
        graph = build_agent_graph(ctx)

        state = graph.run("Which sources have freshness problems?")

        assert state.response is not None
        assert state.response.intent == IntentType.SOURCE_HEALTH
        assert len(state.tool_calls) == 1
        assert state.tool_calls[0].tool_name == "get_source_health"
        assert state.tool_results[0].success is True
        assert "get_source_health" in state.response.sources

    def test_source_health_answer_references_tool_data(self) -> None:
        sources = [
            {
                "source_name": "fake_store",
                "overall_status": "healthy",
                "degradation_state": "healthy",
                "freshness_state": "fresh",
                "freshness_age_seconds": 300.0,
                "assessed_at": "2026-09-20T12:00:00+00:00",
                "reasons": None,
                "signals": None,
            },
        ]
        ctx = GraphContext(source_health_provider=_fake_source_health_provider(sources=sources))
        graph = build_agent_graph(ctx)

        state = graph.run("What is the source health status?")

        assert state.response is not None
        assert (
            "healthy_count: 1" in state.response.answer
            or "healthy" in state.response.answer.lower()
        )


class TestEndToEndPriceAnalytics:
    def test_price_question_routes_to_sql(self) -> None:
        ctx = GraphContext(db=_fake_db())
        graph = build_agent_graph(ctx)

        state = graph.run("Which products had the largest price increases?")

        assert state.response is not None
        assert state.response.intent == IntentType.PRICE_ANALYTICS
        assert len(state.tool_calls) == 1
        assert state.tool_calls[0].tool_name == "get_dataset_metadata"
        assert state.tool_results[0].success is True

    def test_price_answer_uses_metadata_not_hallucination(self) -> None:
        ctx = GraphContext(db=_fake_db(row_count=42))
        graph = build_agent_graph(ctx)

        state = graph.run("What are the price statistics?")

        assert state.response is not None
        assert len(state.tool_results) == 1
        assert state.tool_results[0].success is True
        assert state.response.answer
        assert (
            "total_tables" in state.response.answer
            or "Result with keys" in state.response.answer
            or "result" in state.response.answer.lower()
        )


class TestEndToEndToolFailures:
    def test_tool_failure_produces_error_answer(self) -> None:
        provider = MagicMock()
        provider.list_recent_runs.side_effect = RuntimeError("DB connection lost")
        ctx = GraphContext(pipeline_status_provider=provider)
        graph = build_agent_graph(ctx)

        state = graph.run("What is the pipeline status?")

        assert state.response is not None
        assert state.response.intent == IntentType.PIPELINE_STATUS
        assert len(state.tool_results) == 1
        assert state.tool_results[0].success is False
        assert (
            "error" in state.response.answer.lower()
            or "encountered errors" in state.response.answer.lower()
        )

    def test_missing_db_for_sql_intent(self) -> None:
        ctx = GraphContext(db=None)
        graph = build_agent_graph(ctx)

        state = graph.run("What are the price trends?")

        assert state.response is not None
        assert state.response.intent == IntentType.PRICE_ANALYTICS
        assert len(state.tool_results) == 1
        assert state.tool_results[0].success is False
        assert state.tool_results[0].error is not None
        assert "not available" in state.tool_results[0].error

    def test_all_tools_fail(self) -> None:
        provider = MagicMock()
        provider.list_source_health.side_effect = RuntimeError("connection refused")
        ctx = GraphContext(source_health_provider=provider)
        graph = build_agent_graph(ctx)

        state = graph.run("Which sources are unhealthy?")

        assert state.response is not None
        assert state.tool_results[0].success is False
        assert state.response.sources == []
        assert "error" in state.response.answer.lower()


class TestEndToEndUnrecognizedIntents:
    def test_random_question_goes_to_fallback(self) -> None:
        ctx = GraphContext()
        graph = build_agent_graph(ctx)

        state = graph.run("What is the meaning of life?")

        assert state.response is not None
        assert state.response.intent == IntentType.GENERAL
        assert len(state.tool_calls) == 0
        assert (
            "rephrase" in state.response.answer.lower() or "help" in state.response.answer.lower()
        )

    def test_empty_question_goes_to_fallback(self) -> None:
        ctx = GraphContext()
        graph = build_agent_graph(ctx)

        state = graph.run("")

        assert state.response is not None
        assert state.response.intent == IntentType.GENERAL

    def test_greeting_goes_to_fallback(self) -> None:
        ctx = GraphContext()
        graph = build_agent_graph(ctx)

        state = graph.run("Hello there!")

        assert state.response is not None
        assert state.response.intent == IntentType.GENERAL


class TestAgentUsesToolsNotHallucination:
    def test_pipeline_question_does_not_answer_without_tool(self) -> None:
        ctx = GraphContext(pipeline_status_provider=None)
        graph = build_agent_graph(ctx)

        state = graph.run("What is the pipeline status?")

        assert len(state.tool_calls) == 1
        assert state.tool_calls[0].tool_name == "get_pipeline_status"
        assert state.tool_results[0].success is False
        assert state.response is not None
        assert (
            "not available" in state.response.answer.lower()
            or "error" in state.response.answer.lower()
        )

    def test_quality_question_does_not_answer_without_tool(self) -> None:
        ctx = GraphContext(data_quality_provider=None)
        graph = build_agent_graph(ctx)

        state = graph.run("How is the data quality?")

        assert len(state.tool_calls) == 1
        assert state.tool_calls[0].tool_name == "get_data_quality"
        assert state.tool_results[0].success is False

    def test_source_question_does_not_answer_without_tool(self) -> None:
        ctx = GraphContext(source_health_provider=None)
        graph = build_agent_graph(ctx)

        state = graph.run("Which sources are stale?")

        assert len(state.tool_calls) == 1
        assert state.tool_calls[0].tool_name == "get_source_health"
        assert state.tool_results[0].success is False


class TestAgentReadOnlyGuarantee:
    def test_agent_graph_has_no_write_capability(self) -> None:
        ctx = GraphContext(db=_fake_db())
        graph = build_agent_graph(ctx)

        state = graph.run("Show me the price data")

        assert state.response is not None
        for tool_call in state.tool_calls:
            assert tool_call.tool_name in (
                "get_dataset_metadata",
                "get_pipeline_status",
                "get_data_quality",
                "get_source_health",
            )

    def test_execute_sql_node_calls_metadata_not_raw_sql(self) -> None:
        db = _fake_db()
        ctx = GraphContext(db=db)
        graph = build_agent_graph(ctx)

        graph.run("What are the price trends?")

        db.execute.assert_not_called()
        db.list_tables.assert_called()


class TestEndToEndWithAllProviders:
    def test_full_context_routes_correctly(self) -> None:
        ctx = GraphContext(
            db=_fake_db(),
            pipeline_status_provider=_fake_pipeline_provider(),
            data_quality_provider=_fake_quality_provider(),
            source_health_provider=_fake_source_health_provider(),
        )
        graph = build_agent_graph(ctx)

        pipeline_state = graph.run("What is the pipeline status?")
        assert pipeline_state.response is not None
        assert pipeline_state.response.intent == IntentType.PIPELINE_STATUS

        quality_state = graph.run("How is the data quality?")
        assert quality_state.response is not None
        assert quality_state.response.intent == IntentType.DATA_QUALITY

        source_state = graph.run("Which sources have problems?")
        assert source_state.response is not None
        assert source_state.response.intent == IntentType.SOURCE_HEALTH

        price_state = graph.run("What are the price statistics?")
        assert price_state.response is not None
        assert price_state.response.intent == IntentType.PRICE_ANALYTICS

    def test_each_intent_invokes_exactly_one_tool(self) -> None:
        ctx = GraphContext(
            db=_fake_db(),
            pipeline_status_provider=_fake_pipeline_provider(),
            data_quality_provider=_fake_quality_provider(),
            source_health_provider=_fake_source_health_provider(),
        )
        graph = build_agent_graph(ctx)

        questions = [
            ("What is the pipeline status?", "get_pipeline_status"),
            ("How is the data quality?", "get_data_quality"),
            ("Which sources are stale?", "get_source_health"),
            ("What are the price trends?", "get_dataset_metadata"),
        ]
        for question, expected_tool in questions:
            state = graph.run(question)
            assert len(state.tool_calls) == 1, (
                f"Expected 1 tool call for '{question}', got {len(state.tool_calls)}"
            )
            assert state.tool_calls[0].tool_name == expected_tool
