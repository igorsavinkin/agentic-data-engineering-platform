"""Tests for agent state model and intent types (TASK-092)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from services.agent.intents import ClassifiedIntent, IntentType
from services.agent.state import (
    AgentResponse,
    AgentState,
    Message,
    ToolCallRequest,
    ToolCallResult,
)


class TestIntentType:
    def test_all_intents_exist(self) -> None:
        expected = {
            "price_analytics",
            "pipeline_status",
            "data_quality",
            "source_health",
            "product_history",
            "general",
        }
        actual = {member.value for member in IntentType}
        assert actual == expected

    def test_intent_is_string_enum(self) -> None:
        assert isinstance(IntentType.GENERAL, str)
        assert IntentType.GENERAL == "general"


class TestClassifiedIntent:
    def test_valid_intent(self) -> None:
        ci = ClassifiedIntent(
            intent=IntentType.PRICE_ANALYTICS,
            confidence=0.95,
            raw_question="Which products had the largest price increase?",
        )
        assert ci.intent == IntentType.PRICE_ANALYTICS
        assert ci.confidence == 0.95

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ClassifiedIntent(intent=IntentType.GENERAL, confidence=1.5, raw_question="test")
        with pytest.raises(ValidationError):
            ClassifiedIntent(intent=IntentType.GENERAL, confidence=-0.1, raw_question="test")

    def test_serialization_roundtrip(self) -> None:
        ci = ClassifiedIntent(
            intent=IntentType.DATA_QUALITY,
            confidence=0.8,
            raw_question="Why did observations drop?",
        )
        data = ci.model_dump()
        restored = ClassifiedIntent.model_validate(data)
        assert restored == ci


class TestMessage:
    def test_valid_roles(self) -> None:
        for role in ("user", "assistant", "system", "tool"):
            msg = Message(role=role, content="hello")
            assert msg.role == role

    def test_invalid_role_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Message(role="invalid", content="hello")

    def test_default_metadata(self) -> None:
        msg = Message(role="user", content="test")
        assert msg.metadata == {}

    def test_custom_metadata(self) -> None:
        msg = Message(role="tool", content="result", metadata={"tool_name": "sql"})
        assert msg.metadata["tool_name"] == "sql"


class TestToolCallRequest:
    def test_basic_request(self) -> None:
        req = ToolCallRequest(tool_name="read_only_sql", parameters={"query": "SELECT 1"})
        assert req.tool_name == "read_only_sql"
        assert req.parameters["query"] == "SELECT 1"

    def test_default_empty_parameters(self) -> None:
        req = ToolCallRequest(tool_name="pipeline_status")
        assert req.parameters == {}


class TestToolCallResult:
    def test_success_result(self) -> None:
        result = ToolCallResult(tool_name="read_only_sql", success=True, data=[{"id": 1}])
        assert result.success is True
        assert result.error is None

    def test_failure_result(self) -> None:
        result = ToolCallResult(
            tool_name="read_only_sql", success=False, error="Connection refused"
        )
        assert result.success is False
        assert result.error == "Connection refused"


class TestAgentResponse:
    def test_basic_response(self) -> None:
        resp = AgentResponse(
            answer="The top product is X",
            intent=IntentType.PRICE_ANALYTICS,
            sources=["products table"],
            confidence=0.9,
        )
        assert resp.intent == IntentType.PRICE_ANALYTICS
        assert resp.confidence == 0.9

    def test_defaults(self) -> None:
        resp = AgentResponse(answer="ok", intent=IntentType.GENERAL)
        assert resp.sources == []
        assert resp.confidence == 1.0


class TestAgentState:
    def test_minimal_state(self) -> None:
        state = AgentState(question="What is the pipeline status?")
        assert state.question == "What is the pipeline status?"
        assert state.messages == []
        assert state.classified_intent is None
        assert state.tool_calls == []
        assert state.tool_results == []
        assert state.response is None
        assert state.errors == []

    def test_full_lifecycle(self) -> None:
        state = AgentState(
            question="Which products had the largest price increase?",
            messages=[
                Message(role="user", content="Which products had the largest price increase?"),
            ],
            classified_intent=ClassifiedIntent(
                intent=IntentType.PRICE_ANALYTICS,
                confidence=0.95,
                raw_question="Which products had the largest price increase?",
            ),
            tool_calls=[
                ToolCallRequest(
                    tool_name="read_only_sql",
                    parameters={"query": "SELECT * FROM products ORDER BY price DESC"},
                ),
            ],
            tool_results=[
                ToolCallResult(
                    tool_name="read_only_sql",
                    success=True,
                    data=[{"name": "Widget", "price": 99.99}],
                ),
            ],
            response=AgentResponse(
                answer="Widget had the largest price.",
                intent=IntentType.PRICE_ANALYTICS,
            ),
        )
        assert state.classified_intent is not None
        assert state.classified_intent.intent == IntentType.PRICE_ANALYTICS
        assert len(state.tool_calls) == 1
        assert len(state.tool_results) == 1
        assert state.response is not None

    def test_json_serialization_roundtrip(self) -> None:
        state = AgentState(
            question="test",
            messages=[Message(role="user", content="test")],
            classified_intent=ClassifiedIntent(
                intent=IntentType.GENERAL, confidence=0.5, raw_question="test"
            ),
            errors=["something went wrong"],
        )
        json_str = state.model_dump_json()
        restored = AgentState.model_validate_json(json_str)
        assert restored == state

    def test_json_compatible_with_stdlib(self) -> None:
        state = AgentState(question="test")
        data = state.model_dump()
        json_str = json.dumps(data)
        restored = json.loads(json_str)
        assert restored["question"] == "test"

    def test_state_independent_of_tool_impl(self) -> None:
        state = AgentState(
            question="test",
            tool_calls=[ToolCallRequest(tool_name="any_future_tool", parameters={"x": 1})],
            tool_results=[ToolCallResult(tool_name="any_future_tool", success=True, data={"y": 2})],
        )
        assert state.tool_calls[0].tool_name == "any_future_tool"
        assert state.tool_results[0].data == {"y": 2}

    def test_errors_tracking(self) -> None:
        state = AgentState(
            question="test",
            errors=["error 1", "error 2"],
        )
        assert len(state.errors) == 2
