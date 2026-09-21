"""LangGraph graph construction and routing for the Data Engineer Agent.

Uses the ``langgraph`` library to build a compiled ``StateGraph`` that
routes based on classified intent, invokes the appropriate tools, and
composes a final response from tool results.

Graph structure::

    START → classify → [conditional edges] → compose → END
                           │
              ┌────────────┼────────────────┬──────────────┐
              ▼            ▼                ▼              ▼
         execute_sql  pipeline_status  data_quality  source_health
              │                                              │
              └──────────────────────────────────────────────┘
                           │
                      fallback
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from langgraph.graph import END, START, StateGraph

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


_INTENT_TOOL_MAP: dict[IntentType, str] = {
    IntentType.PRICE_ANALYTICS: "execute_sql",
    IntentType.PIPELINE_STATUS: "pipeline_status",
    IntentType.DATA_QUALITY: "data_quality",
    IntentType.SOURCE_HEALTH: "source_health",
    IntentType.PRODUCT_HISTORY: "execute_sql",
}


# ---------------------------------------------------------------------------
# Node logic (module-level for testability)
# ---------------------------------------------------------------------------


def _classify_node_fn(state: AgentState, ctx: GraphContext) -> dict[str, Any]:
    classified = classify_intent(state.question)
    msg = Message(
        role="system",
        content=f"Classified intent: {classified.intent.value} (confidence: {classified.confidence})",
    )
    return {
        "classified_intent": classified,
        "messages": state.messages + [msg],
    }


def _execute_sql_node_fn(state: AgentState, ctx: GraphContext) -> dict[str, Any]:
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

    return {
        "tool_calls": state.tool_calls + [request],
        "tool_results": state.tool_results + [result],
    }


def _pipeline_status_node_fn(state: AgentState, ctx: GraphContext) -> dict[str, Any]:
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

    return {
        "tool_calls": state.tool_calls + [request],
        "tool_results": state.tool_results + [result],
    }


def _data_quality_node_fn(state: AgentState, ctx: GraphContext) -> dict[str, Any]:
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

    return {
        "tool_calls": state.tool_calls + [request],
        "tool_results": state.tool_results + [result],
    }


def _source_health_node_fn(state: AgentState, ctx: GraphContext) -> dict[str, Any]:
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

    return {
        "tool_calls": state.tool_calls + [request],
        "tool_results": state.tool_results + [result],
    }


def _fallback_node_fn(state: AgentState, ctx: GraphContext) -> dict[str, Any]:
    msg = Message(
        role="assistant",
        content="I can help with pipeline status, data quality, source health, and price analytics. Could you rephrase your question?",
    )
    return {"messages": state.messages + [msg]}


def _route_intent(classified: ClassifiedIntent) -> str:
    """Map a classified intent to a graph node name."""
    if classified.intent == IntentType.GENERAL:
        return "fallback"
    return _INTENT_TOOL_MAP.get(classified.intent, "fallback")


def _compose_response_node(state: AgentState, ctx: GraphContext) -> dict[str, Any]:
    """Compose the final agent response from tool results."""
    existing_assistant = [m for m in state.messages if m.role == "assistant"]
    if existing_assistant:
        answer = existing_assistant[-1].content
        classified = state.classified_intent
        if classified is not None:
            response = AgentResponse(
                answer=answer,
                intent=classified.intent,
                confidence=classified.confidence,
            )
            return {"response": response}
        response = AgentResponse(answer=answer, intent=IntentType.GENERAL, confidence=0.0)
        return {"response": response}

    classified = state.classified_intent
    if classified is None:
        response = AgentResponse(
            answer="Unable to process your question.",
            intent=IntentType.GENERAL,
            confidence=0.0,
        )
        return {"response": response}

    if classified.intent == IntentType.GENERAL:
        response = AgentResponse(
            answer="I can help with pipeline status, data quality, source health, and price analytics. Could you rephrase your question?",
            intent=IntentType.GENERAL,
            confidence=classified.confidence,
        )
        return {"response": response}

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
    return {
        "response": response,
        "errors": errors,
        "messages": state.messages + [Message(role="assistant", content=answer)],
    }


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


# ---------------------------------------------------------------------------
# Graph construction using LangGraph StateGraph
# ---------------------------------------------------------------------------


def _build_graph(ctx: GraphContext) -> Any:
    """Build and compile the LangGraph StateGraph."""

    graph = StateGraph(AgentState)

    graph.add_node("classify", lambda state: _classify_node_fn(state, ctx))
    graph.add_node("execute_sql", lambda state: _execute_sql_node_fn(state, ctx))
    graph.add_node("pipeline_status", lambda state: _pipeline_status_node_fn(state, ctx))
    graph.add_node("data_quality", lambda state: _data_quality_node_fn(state, ctx))
    graph.add_node("source_health", lambda state: _source_health_node_fn(state, ctx))
    graph.add_node("fallback", lambda state: _fallback_node_fn(state, ctx))
    graph.add_node("compose", lambda state: _compose_response_node(state, ctx))

    graph.add_edge(START, "classify")
    graph.add_conditional_edges(
        "classify",
        lambda state: (
            _route_intent(state.classified_intent) if state.classified_intent else "fallback"
        ),
        {
            "execute_sql": "execute_sql",
            "pipeline_status": "pipeline_status",
            "data_quality": "data_quality",
            "source_health": "source_health",
            "fallback": "fallback",
        },
    )
    graph.add_edge("execute_sql", "compose")
    graph.add_edge("pipeline_status", "compose")
    graph.add_edge("data_quality", "compose")
    graph.add_edge("source_health", "compose")
    graph.add_edge("fallback", "compose")
    graph.add_edge("compose", END)

    return graph.compile()


@dataclass
class AgentGraph:
    """Compiled LangGraph agent routing graph.

    Wraps a compiled ``StateGraph`` from the ``langgraph`` library.
    Executes the pipeline: classify -> route -> tool -> compose.
    """

    context: GraphContext = field(default_factory=GraphContext)
    _compiled: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self._compiled is None:
            self._compiled = _build_graph(self.context)

    def run(self, question: str) -> AgentState:
        initial = {
            "question": question,
            "messages": [Message(role="user", content=question)],
        }
        result = self._compiled.invoke(initial)
        if isinstance(result, AgentState):
            return result
        return AgentState(**result)


def build_agent_graph(context: Optional[GraphContext] = None) -> AgentGraph:
    """Construct a compiled LangGraph agent graph with the given context."""
    return AgentGraph(context=context or GraphContext())
