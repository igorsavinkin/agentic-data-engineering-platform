"""Agent endpoint — natural-language question answering via the LangGraph agent."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from services.agent.db_adapter import SQLAlchemyDatabaseConnection
from services.agent.graph import GraphContext, build_agent_graph
from services.agent.pipeline_status_adapter import RepositoryPipelineStatusProvider
from services.agent.quality_adapter import RepositoryDataQualityProvider
from services.agent.source_health_adapter import RepositorySourceHealthProvider
from services.api.dependencies import get_db
from services.api.errors import APIError
from services.api.repositories.pipeline_status import PipelineStatusRepository
from services.api.repositories.quality import DataQualityRepository
from services.api.schemas import AgentAskRequest, AgentAskResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/ask", response_model=AgentAskResponse)
def ask_agent(
    body: AgentAskRequest,
    db: Session = Depends(get_db),
) -> AgentAskResponse:
    """Accept a natural-language question and return the agent's response.

    The agent uses controlled read-only tools — it never writes to the database.
    """
    pipeline_repo = PipelineStatusRepository(db)
    quality_repo = DataQualityRepository(db)

    db_conn = SQLAlchemyDatabaseConnection(db)
    pipeline_provider = RepositoryPipelineStatusProvider(pipeline_repo)
    quality_provider = RepositoryDataQualityProvider(quality_repo)
    source_health_provider = RepositorySourceHealthProvider(pipeline_repo)

    context = GraphContext(
        db=db_conn,
        pipeline_status_provider=pipeline_provider,
        data_quality_provider=quality_provider,
        source_health_provider=source_health_provider,
    )
    graph = build_agent_graph(context)

    try:
        state = graph.run(body.question)
    except Exception:
        logger.exception("Agent execution failed for question: %s", body.question)
        raise APIError(
            status_code=500,
            error_code="AGENT_ERROR",
            message="Agent execution failed",
        )

    response = state.response
    if response is None:
        raise APIError(
            status_code=500,
            error_code="AGENT_NO_RESPONSE",
            message="Agent produced no response",
        )

    return AgentAskResponse(
        answer=response.answer,
        intent=response.intent.value,
        confidence=response.confidence,
        sources=response.sources,
    )
