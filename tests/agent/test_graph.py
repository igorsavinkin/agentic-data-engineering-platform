"""Tests for the LangGraph agent routing graph (TASK-098)."""

from __future__ import annotations

from typing import Any, Optional

from services.agent.graph import (
    AgentGraph,
    GraphContext,
    _compose_response_node,
    _format_tool_answer,
    _route_intent,
    _summarize_dict,
    build_agent_graph,
)
from services.agent.intents import ClassifiedIntent, IntentType
from services.agent.state import (
    AgentState,
    ToolCallResult,
)


class FakePipelineStatusProvider:
    def list_recent_runs(self, limit: int = 5) -> list[dict[str, Any]]:
        return []

    def get_total_run_count(self) -> int:
        return 0

    def list_source_health(self) -> list[dict[str, Any]]:
        return []

    def get_lag_samples(self) -> list[dict[str, Any]]:
        return []


class FakeDataQualityProvider:
    def list_recent_checks(
        self, limit: int = 10, check_name: Optional[str] = None
    ) -> list[dict[str, Any]]:
        return []


class FakeSourceHealthProvider:
    def list_source_health(self, source_name: Optional[str] = None) -> list[dict[str, Any]]:
        return [
            {
                "source_name": "test_source",
                "overall_status": "healthy",
                "degradation_state": "nominal",
                "freshness_state": "fresh",
                "freshness_age_seconds": 30.0,
                "assessed_at": "2026-01-01T00:00:00Z",
                "reasons": None,
                "signals": None,
            }
        ]


class FakeDatabase:
    def execute_read_only(self, query: str) -> list[dict[str, Any]]:
        return [{"table_name": "prices", "row_count": 100}]


class TestRouteIntent:
    def test_price_analytics_routes_to_sql(self) -> None:
        classified = ClassifiedIntent(
            intent=IntentType.PRICE_ANALYTICS, confidence=0.8, raw_question="price?"
        )
        assert _route_intent(classified) == "execute_sql"

    def test_pipeline_status_routes_to_pipeline(self) -> None:
        classified = ClassifiedIntent(
            intent=IntentType.PIPELINE_STATUS, confidence=0.9, raw_question="pipeline?"
        )
        assert _route_intent(classified) == "pipeline_status"

    def test_data_quality_routes_to_quality(self) -> None:
        classified = ClassifiedIntent(
            intent=IntentType.DATA_QUALITY, confidence=0.7, raw_question="quality?"
        )
        assert _route_intent(classified) == "data_quality"

    def test_source_health_routes_to_source(self) -> None:
        classified = ClassifiedIntent(
            intent=IntentType.SOURCE_HEALTH, confidence=0.85, raw_question="source?"
        )
        assert _route_intent(classified) == "source_health"

    def test_product_history_routes_to_sql(self) -> None:
        classified = ClassifiedIntent(
            intent=IntentType.PRODUCT_HISTORY, confidence=0.6, raw_question="history?"
        )
        assert _route_intent(classified) == "execute_sql"

    def test_general_routes_to_fallback(self) -> None:
        classified = ClassifiedIntent(
            intent=IntentType.GENERAL, confidence=1.0, raw_question="hello"
        )
        assert _route_intent(classified) == "fallback"


class TestGraphRouting:
    def test_pipeline_status_intent(self) -> None:
        provider = FakePipelineStatusProvider()
        ctx = GraphContext(pipeline_status_provider=provider)
        graph = build_agent_graph(ctx)

        state = graph.run("What is the pipeline status?")

        assert state.classified_intent is not None
        assert state.classified_intent.intent == IntentType.PIPELINE_STATUS
        assert len(state.tool_calls) == 1
        assert state.tool_calls[0].tool_name == "get_pipeline_status"
        assert len(state.tool_results) == 1
        assert state.tool_results[0].success is True
        assert state.response is not None
        assert state.response.intent == IntentType.PIPELINE_STATUS

    def test_data_quality_intent(self) -> None:
        provider = FakeDataQualityProvider()
        ctx = GraphContext(data_quality_provider=provider)  # type: ignore[arg-type]
        graph = build_agent_graph(ctx)

        state = graph.run("Show me data quality results")

        assert state.classified_intent is not None
        assert state.classified_intent.intent == IntentType.DATA_QUALITY
        assert len(state.tool_calls) == 1
        assert state.tool_calls[0].tool_name == "get_data_quality"
        assert state.response is not None
        assert state.response.intent == IntentType.DATA_QUALITY

    def test_source_health_intent(self) -> None:
        provider = FakeSourceHealthProvider()
        ctx = GraphContext(source_health_provider=provider)
        graph = build_agent_graph(ctx)

        state = graph.run("What is the source health status?")

        assert state.classified_intent is not None
        assert state.classified_intent.intent == IntentType.SOURCE_HEALTH
        assert len(state.tool_calls) == 1
        assert state.tool_calls[0].tool_name == "get_source_health"
        assert state.response is not None
        assert state.response.intent == IntentType.SOURCE_HEALTH

    def test_general_intent_fallback(self) -> None:
        graph = build_agent_graph()

        state = graph.run("Hello there")

        assert state.classified_intent is not None
        assert state.classified_intent.intent == IntentType.GENERAL
        assert len(state.tool_calls) == 0
        assert state.response is not None
        assert state.response.intent == IntentType.GENERAL
        assert "rephrase" in state.response.answer.lower()

    def test_empty_question_fallback(self) -> None:
        graph = build_agent_graph()

        state = graph.run("")

        assert state.classified_intent is not None
        assert state.classified_intent.intent == IntentType.GENERAL
        assert state.response is not None
        assert state.response.intent == IntentType.GENERAL


class TestGraphErrorHandling:
    def test_missing_provider_returns_error(self) -> None:
        ctx = GraphContext()
        graph = build_agent_graph(ctx)

        state = graph.run("What is the pipeline status?")

        assert len(state.tool_results) == 1
        assert state.tool_results[0].success is False
        assert state.tool_results[0].error is not None
        assert "not available" in state.tool_results[0].error.lower()
        assert state.response is not None
        assert "error" in state.response.answer.lower()

    def test_missing_db_for_sql_intent(self) -> None:
        ctx = GraphContext()
        graph = build_agent_graph(ctx)

        state = graph.run("Show me price trends")

        assert len(state.tool_results) == 1
        assert state.tool_results[0].success is False
        assert state.response is not None

    def test_errors_collected_in_state(self) -> None:
        ctx = GraphContext()
        graph = build_agent_graph(ctx)

        state = graph.run("What is the pipeline status?")

        assert len(state.errors) > 0


class TestGraphDeterminism:
    def test_same_input_same_output(self) -> None:
        provider = FakePipelineStatusProvider()
        ctx = GraphContext(pipeline_status_provider=provider)
        graph = build_agent_graph(ctx)

        state1 = graph.run("What is the pipeline status?")
        state2 = graph.run("What is the pipeline status?")

        assert state1.classified_intent == state2.classified_intent
        assert state1.tool_calls == state2.tool_calls
        assert state1.response == state2.response

    def test_different_intents_route_differently(self) -> None:
        pipeline_provider = FakePipelineStatusProvider()
        quality_provider = FakeDataQualityProvider()
        ctx = GraphContext(
            pipeline_status_provider=pipeline_provider,
            data_quality_provider=quality_provider,  # type: ignore[arg-type]
        )
        graph = build_agent_graph(ctx)

        state_pipeline = graph.run("What is the pipeline status?")
        state_quality = graph.run("Show me data quality results")

        assert state_pipeline.classified_intent != state_quality.classified_intent
        assert state_pipeline.tool_calls[0].tool_name != state_quality.tool_calls[0].tool_name


class TestComposeResponse:
    def _apply(self, state: AgentState, updates: dict) -> AgentState:
        return state.model_copy(update=updates)

    def test_compose_with_successful_results(self) -> None:
        state = AgentState(
            question="test",
            classified_intent=ClassifiedIntent(
                intent=IntentType.PIPELINE_STATUS, confidence=0.9, raw_question="test"
            ),
            tool_results=[
                ToolCallResult(
                    tool_name="get_pipeline_status",
                    success=True,
                    data={"total_pipelines": 5, "healthy_count": 3},
                )
            ],
        )
        ctx = GraphContext()

        result = self._apply(state, _compose_response_node(state, ctx))

        assert result.response is not None
        assert (
            "total_pipelines" in result.response.answer or "healthy_count" in result.response.answer
        )
        assert result.response.sources == ["get_pipeline_status"]

    def test_compose_with_no_intent(self) -> None:
        state = AgentState(question="test")
        ctx = GraphContext()

        result = self._apply(state, _compose_response_node(state, ctx))

        assert result.response is not None
        assert result.response.intent == IntentType.GENERAL
        assert result.response.confidence == 0.0

    def test_compose_with_all_errors(self) -> None:
        state = AgentState(
            question="test",
            classified_intent=ClassifiedIntent(
                intent=IntentType.PIPELINE_STATUS, confidence=0.8, raw_question="test"
            ),
            tool_results=[
                ToolCallResult(
                    tool_name="get_pipeline_status",
                    success=False,
                    error="provider down",
                )
            ],
        )
        ctx = GraphContext()

        result = self._apply(state, _compose_response_node(state, ctx))

        assert result.response is not None
        assert "error" in result.response.answer.lower()
        assert len(result.errors) == 1


class TestFormatHelpers:
    def test_format_tool_answer_with_dict(self) -> None:
        results = [
            ToolCallResult(
                tool_name="test",
                success=True,
                data={"total_sources": 10, "healthy_count": 8},
            )
        ]
        answer = _format_tool_answer(IntentType.SOURCE_HEALTH, results)
        assert "total_sources: 10" in answer
        assert "healthy_count: 8" in answer

    def test_format_tool_answer_with_list(self) -> None:
        results = [ToolCallResult(tool_name="test", success=True, data=[1, 2, 3])]
        answer = _format_tool_answer(IntentType.PIPELINE_STATUS, results)
        assert "3 result(s)" in answer

    def test_format_tool_answer_empty(self) -> None:
        results = [ToolCallResult(tool_name="test", success=True, data=None)]
        answer = _format_tool_answer(IntentType.GENERAL, results)
        assert "no results" in answer.lower()

    def test_summarize_dict_with_known_keys(self) -> None:
        result = _summarize_dict({"total_pipelines": 5, "other_key": "value"})
        assert "total_pipelines: 5" in result

    def test_summarize_dict_with_unknown_keys(self) -> None:
        result = _summarize_dict({"custom_key": "value"})
        assert "custom_key" in result


class TestBuildAgentGraph:
    def test_build_with_default_context(self) -> None:
        graph = build_agent_graph()
        assert isinstance(graph, AgentGraph)

    def test_build_with_custom_context(self) -> None:
        ctx = GraphContext(pipeline_status_provider=FakePipelineStatusProvider())
        graph = build_agent_graph(ctx)
        assert graph.context is ctx

    def test_build_with_none_uses_default(self) -> None:
        graph = build_agent_graph(None)
        assert isinstance(graph, AgentGraph)


class TestMessagesTracking:
    def test_user_message_added(self) -> None:
        graph = build_agent_graph()
        state = graph.run("Hello")
        assert state.messages[0].role == "user"
        assert state.messages[0].content == "Hello"

    def test_classification_message_added(self) -> None:
        graph = build_agent_graph()
        state = graph.run("What is the pipeline status?")
        system_msgs = [m for m in state.messages if m.role == "system"]
        assert len(system_msgs) >= 1
        assert "pipeline_status" in system_msgs[0].content

    def test_assistant_message_added_for_response(self) -> None:
        provider = FakePipelineStatusProvider()
        ctx = GraphContext(pipeline_status_provider=provider)
        graph = build_agent_graph(ctx)
        state = graph.run("What is the pipeline status?")
        assistant_msgs = [m for m in state.messages if m.role == "assistant"]
        assert len(assistant_msgs) >= 1
