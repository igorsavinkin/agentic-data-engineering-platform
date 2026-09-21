"""Intent types for the LangGraph Data Engineer Agent.

Intents map natural-language user questions to structured routing
categories. Each intent corresponds to a tool selection in the
routing layer.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """Classified intent categories the agent can route to.

    Each value maps to a distinct tool selection in the routing layer.
    """

    PRICE_ANALYTICS = "price_analytics"
    PIPELINE_STATUS = "pipeline_status"
    DATA_QUALITY = "data_quality"
    SOURCE_HEALTH = "source_health"
    PRODUCT_HISTORY = "product_history"
    GENERAL = "general"


class ClassifiedIntent(BaseModel):
    """Result of intent classification for a user question."""

    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    raw_question: str
