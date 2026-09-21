"""LangGraph graph construction and routing for the Data Engineer Agent.

Connects intent classification to tool selection and response generation.
The graph routes based on classified intent, invokes the appropriate tools,
and composes a final response from tool results.

Graph structure:
    classify → route → [tool_node | fallback] → compose_response
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from services.agent.classifier import classify_intent
from services.agent.intents import ClassifiedIntent, IntentType
from services.agent.state import (
    AgentResponse,
    AgentState,
    Message,
    ToolCallRequest,
    ToolCallResult,
)
from services.agent.tools import (
    DatabaseConnection,
    DataQualityProvider,
    PipelineStatusProvider,
    SourceHealthProvider,
)


@dataclass
class GraphContext:
    """Injected dependencies for graph execution."""

    db: Optional[DatabaseConnection] = None
    pipeline_status_provider: Optional[PipelineStatusProvider] = None
    data_quality_provider: Optional[DataQualityProvider] = None
    source_health_provider: Optional[SourceHealthProvider] = None


NodeFunction = Callable[[AgentState, GraphContext], AgentState]

_INTENT_TOOL_MAP: dict[IntentType, str] = {
    IntentType.PRICE_ANALYTICS: "execute_sql",
    IntentType.PIPELINE_STATUS: "pipeline_status",
    IntentType.DATA_QUALITY: "data_quality",
    IntentType.SOURCE_HEALTH: "source_health",
    IntentType.PRODUCT_HISTORY: "execute_sql",
}


def _classify_node(state: AgentState, ctx: GraphContext) -> AgentState:
    classified = classify_intent(state.question)
    return state.model_copy(
        update={
            "classified_intent": classified,
            "messages": state.messages
            + [
                Message(
                    role="system",
                    content=f"Classified intent: {classified.intent.value} (confidence: {classified.confidence})",
                )
            ],
        }
    )


def _route_intent(classified: ClassifiedIntent) -> str:
    if classified.intent == IntentType.GENERAL:
        return "fallback"
    return _INTENT_TOOL_MAP.get(classified.intent, "fallback")


def _execute_sql_node(state: AgentState, ctx: GraphContext) -> AgentState:
    tool_name = "get_dataset_metadata"
    request = ToolCallRequest(tool_name=tool_name, parameters={})
    try:
        if ctx.db is None:
            result = ToolCallResult(
                tool_name=tool_name,
                success=False,
                error="Database connection not available",
            )
        else:
            from services.agent.tools import get_dataset_metadata

            response = get_dataset_metadata(db=ctx.db)
            result = ToolCallResult(
                tool_name=tool_name,
                success=response.success,
                data=response.data,
                error=response.error,
            )
    except Exception as exc:
        result = ToolCallResult(tool_name=tool_name, success=False, error=str(exc))

    return state.model_copy(
        update={
            "tool_calls": state.tool_calls + [request],
            "tool_results": state.tool_results + [result],
        }
    )


def _pipeline_status_node(state: AgentState, ctx: GraphContext) -> AgentState:
    tool_name = "get_pipeline_status"
    request = ToolCallRequest(tool_name=tool_name, parameters={})
    try:
        if ctx.pipeline_status_provider is None:
            result = ToolCallResult(
                tool_name=tool_name,
                success=False,
                error="Pipeline status provider not available",
            )
        else:
            from services.agent.tools import get_pipeline_status

            response = get_pipeline_status(provider=ctx.pipeline_status_provider)
            result = ToolCallResult(
                tool_name=tool_name,
                success=response.success,
                data=response.data,
                error=response.error,
            )
    except Exception as exc:
        result = ToolCallResult(tool_name=tool_name, success=False, error=str(exc))

    return state.model_copy(
        update={
            "tool_calls": state.tool_calls + [request],
            "tool_results": state.tool_results + [result],
        }
    )


def _data_quality_node(state: AgentState, ctx: GraphContext) -> AgentState:
    tool_name = "get_data_quality"
    request = ToolCallRequest(tool_name=tool_name, parameters={})
    try:
        if ctx.data_quality_provider is None:
            result = ToolCallResult(
                tool_name=tool_name,
                success=False,
                error="Data quality provider not available",
            )
        else:
            from services.agent.tools import get_data_quality

            response = get_data_quality(provider=ctx.data_quality_provider)
            result = ToolCallResult(
                tool_name=tool_name,
                success=response.success,
                data=response.data,
                error=response.error,
            )
    except Exception as exc:
        result = ToolCallResult(tool_name=tool_name, success=False, error=str(exc))

    return state.model_copy(
        update={
            "tool_calls": state.tool_calls + [request],
            "tool_results": state.tool_results + [result],
        }
    )


def _source_health_node(state: AgentState, ctx: GraphContext) -> AgentState:
    tool_name = "get_source_health"
    request = ToolCallRequest(tool_name=tool_name, parameters={})
    try:
        if ctx.source_health_provider is None:
            result = ToolCallResult(
                tool_name=tool_name,
                success=False,
                error="Source health provider not available",
            )
        else:
            from services.agent.tools import get_source_health

            response = get_source_health(provider=ctx.source_health_provider)
            result = ToolCallResult(
                tool_name=tool_name,
                success=response.success,
                data=response.data,
                error=response.error,
            )
    except Exception as exc:
        result = ToolCallResult(tool_name=tool_name, success=False, error=str(exc))

    return state.model_copy(
        update={
            "tool_calls": state.tool_calls + [request],
            "tool_results": state.tool_results + [result],
        }
    )


def _fallback_node(state: AgentState, ctx: GraphContext) -> AgentState:
    return state.model_copy(
        update={
            "messages": state.messages
            + [
                Message(
                    role="assistant",
                    content="I can help with pipeline status, data quality, source health, and price analytics. Could you rephrase your question?",
                )
            ],
        }
    )


def _compose_response_node(state: AgentState, ctx: GraphContext) -> AgentState:
    classified = state.classified_intent
    if classified is None:
        response = AgentResponse(
            answer="Unable to process your question.",
            intent=IntentType.GENERAL,
            confidence=0.0,
        )
        return state.model_copy(update={"response": response})

    if classified.intent == IntentType.GENERAL:
        response = AgentResponse(
            answer="I can help with pipeline status, data quality, source health, and price analytics. Could you rephrase your question?",
            intent=IntentType.GENERAL,
            confidence=classified.confidence,
        )
        return state.model_copy(update={"response": response})

    tool_results = state.tool_results
    errors: list[str] = []
    sources: list[str] = []

    for tr in tool_results:
        if not tr.success:
            errors.append(f"{tr.tool_name}: {tr.error or 'unknown error'}")
        else:
            sources.append(tr.tool_name)

    if errors and not sources:
        answer = f"Encountered errors while processing your question: {'; '.join(errors)}"
    elif tool_results:
        answer = _format_tool_answer(classified.intent, tool_results)
    else:
        answer = "No data available for your question."

    response = AgentResponse(
        answer=answer,
        intent=classified.intent,
        sources=sources,
        confidence=classified.confidence,
    )
    return state.model_copy(
        update={
            "response": response,
            "errors": errors,
            "messages": state.messages + [Message(role="assistant", content=answer)],
        }
    )


def _format_tool_answer(intent: IntentType, results: list[ToolCallResult]) -> str:
    parts: list[str] = []
    for tr in results:
        if not tr.success or tr.data is None:
            continue
        if isinstance(tr.data, dict):
            summary = _summarize_dict(tr.data)
            parts.append(summary)
        elif isinstance(tr.data, list):
            parts.append(f"Found {len(tr.data)} result(s).")
        else:
            parts.append(str(tr.data))
    if not parts:
        return "Query completed but no results were returned."
    return " | ".join(parts)


def _summarize_dict(data: dict[str, Any]) -> str:
    highlights: list[str] = []
    for key in (
        "total_sources",
        "total_pipelines",
        "total_tables",
        "healthy_count",
        "degraded_count",
        "stale_count",
    ):
        if key in data:
            highlights.append(f"{key}: {data[key]}")
    if highlights:
        return ", ".join(highlights)
    return f"Result with keys: {', '.join(str(k) for k in data.keys())}"


_NODE_MAP: dict[str, NodeFunction] = {
    "execute_sql": _execute_sql_node,
    "pipeline_status": _pipeline_status_node,
    "data_quality": _data_quality_node,
    "source_health": _source_health_node,
    "fallback": _fallback_node,
}


@dataclass
class AgentGraph:
    """Compiled agent routing graph.

    Executes the pipeline: classify → route → tool → compose_response.
    """

    context: GraphContext = field(default_factory=GraphContext)

    def run(self, question: str) -> AgentState:
        state = AgentState(
            question=question,
            messages=[Message(role="user", content=question)],
        )

        state = _classify_node(state, self.context)

        if state.classified_intent is None:
            return _compose_response_node(state, self.context)

        route = _route_intent(state.classified_intent)

        tool_node = _NODE_MAP.get(route, _fallback_node)
        state = tool_node(state, self.context)

        state = _compose_response_node(state, self.context)

        return state


def build_agent_graph(context: Optional[GraphContext] = None) -> AgentGraph:
    """Construct a compiled agent graph with the given context."""
    return AgentGraph(context=context or GraphContext())
