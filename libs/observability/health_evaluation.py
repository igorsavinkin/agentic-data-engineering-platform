"""Source health evaluation for scheduled Airflow checks (TASK-059).

Provides a stateless evaluator that assesses configured source health from
observable warehouse data. Uses existing ``SourceHealthAssessor`` and
``SourceHealthConfig`` semantics so that DAG orchestration stays separate
from assessment logic.

The evaluator does not talk to external sources directly. It inspects
warehouse observation timestamps and optional fetch outcome data to
produce ``SourceHealthAssessment`` results suitable for persistence.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from libs.observability.health_assessment import (
    FreshnessState,
    SourceDegradationState,
    SourceHealthAssessment,
    SourceHealthAssessor,
    SourceHealthConfig,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceObservation:
    """Observable data about a source at evaluation time.

    All fields are optional — the evaluator produces a valid assessment
    even when no observation data is available (reporting HEALTHY with
    a "no data" note, or NEVER_COLLECTED for freshness).
    """

    source_name: str
    last_observation_at: datetime | None = None
    total_observations: int = 0
    recent_fetch_outcomes: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class IngestionHealthEvaluation:
    """Complete health evaluation result for one source.

    Combines the degradation assessment from ``SourceHealthAssessor``
    with the programmatic freshness state.
    """

    source_name: str
    assessment: SourceHealthAssessment
    freshness_state: FreshnessState
    freshness_age_seconds: float | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict suitable for persistence or XCom."""
        return {
            "source_name": self.source_name,
            "state": self.assessment.state.value,
            "freshness_state": self.freshness_state.value,
            "reasons": list(self.assessment.reasons),
            "signals": dict(self.assessment.signals),
            "freshness_age_seconds": self.freshness_age_seconds,
            "assessed_at": self.assessment.assessed_at.isoformat(),
        }


@dataclass(frozen=True)
class SourceHealthEvaluationConfig:
    """Per-source health evaluation configuration.

    Maps each configured source name to its ``SourceHealthConfig``
    thresholds. Sources not in this mapping use ``default_config``.
    """

    source_configs: Mapping[str, SourceHealthConfig] = field(default_factory=dict)
    default_config: SourceHealthConfig = field(default_factory=SourceHealthConfig)

    def config_for(self, source_name: str) -> SourceHealthConfig:
        """Return the health config for a specific source."""
        return self.source_configs.get(source_name, self.default_config)


class IngestionHealthEvaluator:
    """Evaluate health of configured sources from observable data.

    The evaluator is stateless and deterministic — given the same inputs
    and clock, it produces the same outputs. This makes DAG reruns for
    the same logical interval idempotent.

    Parameters
    ----------
    evaluation_config:
        Per-source health thresholds. Sources not explicitly configured
        use the default thresholds.
    clock:
        Injectable clock for deterministic testing.
    """

    def __init__(
        self,
        evaluation_config: SourceHealthEvaluationConfig | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = evaluation_config or SourceHealthEvaluationConfig()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def evaluate_source(
        self,
        observation: SourceObservation,
    ) -> IngestionHealthEvaluation:
        """Evaluate health for a single source.

        Uses the source-specific ``SourceHealthConfig`` to build a
        ``SourceHealthAssessor``, then derives freshness state from
        the observation's last-observation timestamp.
        """
        source_name = observation.source_name
        health_config = self._config.config_for(source_name)
        assessor = SourceHealthAssessor(config=health_config, clock=self._clock)

        freshness_age = self._compute_freshness_age(observation)
        freshness_state = self._compute_freshness_state(freshness_age, health_config)

        outcomes = self._build_outcomes(observation)
        consecutive_empty = self._count_consecutive_empty(observation)

        assessment = assessor.assess(
            source_name=source_name,
            outcomes=outcomes,
            consecutive_empty=consecutive_empty,
            freshness_age_seconds=freshness_age,
        )

        if (
            freshness_state == FreshnessState.NEVER_COLLECTED
            and assessment.state == SourceDegradationState.HEALTHY
        ):
            if not outcomes:
                assessment = SourceHealthAssessment(
                    state=SourceDegradationState.HEALTHY,
                    reasons=["no observation data available"],
                    source=source_name,
                    assessed_at=assessment.assessed_at,
                    signals=assessment.signals,
                )

        return IngestionHealthEvaluation(
            source_name=source_name,
            assessment=assessment,
            freshness_state=freshness_state,
            freshness_age_seconds=freshness_age,
        )

    def evaluate_all(
        self,
        observations: list[SourceObservation],
    ) -> list[IngestionHealthEvaluation]:
        """Evaluate health for all provided source observations."""
        return [self.evaluate_source(obs) for obs in observations]

    def _compute_freshness_age(self, observation: SourceObservation) -> float | None:
        """Compute freshness age in seconds from last observation time."""
        if observation.last_observation_at is None:
            return None
        now = self._clock()
        age = (now - observation.last_observation_at).total_seconds()
        return max(0.0, age)

    def _compute_freshness_state(
        self,
        freshness_age: float | None,
        config: SourceHealthConfig,
    ) -> FreshnessState:
        """Derive programmatic freshness state from age and threshold."""
        if freshness_age is None:
            return FreshnessState.NEVER_COLLECTED
        threshold = config.max_freshness_age_seconds
        if threshold is not None and freshness_age > threshold:
            return FreshnessState.STALE
        return FreshnessState.FRESH

    def _build_outcomes(self, observation: SourceObservation) -> list[Any]:
        """Build _FetchOutcome-compatible objects from observation data.

        The ``SourceHealthAssessor`` expects ``_FetchOutcome`` instances.
        We construct them from the observation's recent_fetch_outcomes
        dicts, which have keys: success, events_emitted, total_records,
        malformed_count, failure_reason.
        """
        from libs.observability.health_assessment import _FetchOutcome

        outcomes: list[Any] = []
        for raw in observation.recent_fetch_outcomes:
            outcomes.append(
                _FetchOutcome(
                    success=raw.get("success", True),
                    events_emitted=raw.get("events_emitted", 0),
                    total_records=raw.get("total_records", 0),
                    malformed_count=raw.get("malformed_count", 0),
                    failure_reason=raw.get("failure_reason"),
                )
            )
        return outcomes

    def _count_consecutive_empty(self, observation: SourceObservation) -> int:
        """Count consecutive empty-result fetches from the tail."""
        count = 0
        for raw in reversed(observation.recent_fetch_outcomes):
            if raw.get("success", True) and raw.get("events_emitted", 0) == 0:
                count += 1
            else:
                break
        return count
