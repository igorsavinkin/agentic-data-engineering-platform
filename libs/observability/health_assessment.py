"""Source degradation detection and health assessment.

Provides a configurable health assessor that classifies a source into
explicit degradation states based on fetch outcomes and measurable signals.
Designed for the difficult retailer adapter (TASK-053) but generic enough
for reuse across all source adapters.

Degradation detection does NOT mutate downstream data — it only observes
fetch outcomes and produces diagnostic assessments suitable for later
Airflow/data-quality checks.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class SourceDegradationState(StrEnum):
    """Explicit source health states.

    These states distinguish source *availability* from source *data quality*.
    A source can be reachable (HTTP 200) yet degraded (empty, structural
    change, partially parseable).
    """

    HEALTHY = "healthy"
    UNREACHABLE = "unreachable"
    RATE_LIMITED = "rate_limited"
    STRUCTURALLY_CHANGED = "structurally_changed"
    PARTIALLY_PARSEABLE = "partially_parseable"
    EMPTY_RESULT = "empty_result"
    STALE = "stale"


class FreshnessState(StrEnum):
    """Programmatic freshness classification.

    Distinguishes the freshness semantics needed by downstream consumers
    (e.g. Airflow ingestion_health DAGs) without requiring them to
    interpret raw timestamps or thresholds.
    """

    FRESH = "fresh"
    STALE = "stale"
    NEVER_COLLECTED = "never_collected"


@dataclass(frozen=True)
class SourceHealthConfig:
    """Configurable thresholds for health assessment.

    Avoids brittle hard-coded production thresholds by making all limits
    tunable per source.

    Attributes
    ----------
    min_success_ratio:
        Minimum ratio of successful fetches to total fetches before the
        source is considered degraded. Range (0, 1].
    max_malformed_ratio:
        Maximum ratio of malformed records to total records before the
        source is considered partially parseable. Range [0, 1].
    max_empty_fetches:
        Maximum number of consecutive empty-result fetches before the
        source is flagged as empty_result.
    max_freshness_age_seconds:
        Maximum age of last successful fetch before the source is
        considered stale. None disables this check.
    min_expected_records:
        Minimum expected records per fetch. Fetches below this threshold
        contribute to empty-result detection. None disables this check.
    """

    min_success_ratio: float = 0.5
    max_malformed_ratio: float = 0.5
    max_empty_fetches: int = 3
    max_freshness_age_seconds: float | None = None
    min_expected_records: int | None = None


@dataclass(frozen=True)
class SourceHealthAssessment:
    """Result of a source health assessment.

    Attributes
    ----------
    state:
        Current degradation state.
    reasons:
        Human-readable diagnostic reasons for the assessment.
    source:
        Source identifier.
    assessed_at:
        UTC timestamp of the assessment.
    signals:
        Measurable signals used for the assessment (fetch counts,
        malformed counts, success ratio, etc.).
    """

    state: SourceDegradationState
    reasons: list[str]
    source: str
    assessed_at: datetime
    signals: dict[str, Any]


@dataclass
class _FetchOutcome:
    """Internal record of a single fetch outcome."""

    success: bool
    events_emitted: int = 0
    total_records: int = 0
    malformed_count: int = 0
    failure_reason: str | None = None
    timestamp: datetime | None = None


class SourceHealthTracker:
    """Track per-fetch outcomes and produce health assessments.

    Maintains a bounded history of fetch outcomes and evaluates source
    health on demand. Thread-safe for concurrent outcome recording.

    The tracker is read-only with respect to the event pipeline — it
    observes outcomes but never mutates downstream data.

    The ``clock`` parameter allows deterministic testing by injecting a
    fixed or controlled time source.
    """

    def __init__(
        self,
        source_name: str,
        config: SourceHealthConfig | None = None,
        max_history: int = 100,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._source_name = source_name
        self._config = config or SourceHealthConfig()
        self._max_history = max_history
        self._outcomes: list[_FetchOutcome] = []
        self._consecutive_empty = 0
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._freshness_age_seconds: float | None = None

    @property
    def source_name(self) -> str:
        return self._source_name

    def update_freshness_age(self, age_seconds: float | None) -> None:
        """Update the freshness age for this source.

        Called by the runner or metrics layer to feed freshness data
        into the health tracker. None means no successful usable
        fetch has occurred.
        """
        self._freshness_age_seconds = age_seconds

    def get_freshness_state(self) -> FreshnessState:
        """Return the current programmatic freshness classification.

        Uses the configured ``max_freshness_age_seconds`` threshold.
        Returns NEVER_COLLECTED if no freshness age has been recorded,
        STALE if the age exceeds the threshold, FRESH otherwise.
        """
        if self._freshness_age_seconds is None:
            return FreshnessState.NEVER_COLLECTED
        threshold = self._config.max_freshness_age_seconds
        if threshold is not None and self._freshness_age_seconds > threshold:
            return FreshnessState.STALE
        return FreshnessState.FRESH

    def record_fetch_success(
        self,
        *,
        events_emitted: int,
        total_records: int,
        malformed_count: int = 0,
    ) -> None:
        """Record a successful fetch outcome."""
        outcome = _FetchOutcome(
            success=True,
            events_emitted=events_emitted,
            total_records=total_records,
            malformed_count=malformed_count,
            timestamp=self._clock(),
        )
        self._outcomes.append(outcome)
        self._trim_history()

        if events_emitted == 0:
            self._consecutive_empty += 1
        else:
            self._consecutive_empty = 0

    def record_fetch_failure(self, reason: str) -> None:
        """Record a failed fetch outcome."""
        outcome = _FetchOutcome(
            success=False,
            failure_reason=reason,
            timestamp=self._clock(),
        )
        self._outcomes.append(outcome)
        self._trim_history()

    def assess(self) -> SourceHealthAssessment:
        """Evaluate current source health from tracked outcomes."""
        return SourceHealthAssessor(self._config, clock=self._clock).assess(
            source_name=self._source_name,
            outcomes=list(self._outcomes),
            consecutive_empty=self._consecutive_empty,
            freshness_age_seconds=self._freshness_age_seconds,
        )

    def _trim_history(self) -> None:
        if len(self._outcomes) > self._max_history:
            self._outcomes = self._outcomes[-self._max_history :]


class SourceHealthAssessor:
    """Evaluate source health from fetch outcomes and measurable signals.

    The assessor is stateless — it takes outcomes as input and produces
    an assessment. Priority order for degradation detection:

    1. UNREACHABLE — recent fetches are mostly failing
    2. RATE_LIMITED — explicit rate-limit failure reason
    3. STRUCTURALLY_CHANGED — explicit structural-change failure reason
    4. STALE — freshness age exceeds configured threshold
    5. EMPTY_RESULT — consecutive empty results or below min_expected_records
    6. PARTIALLY_PARSEABLE — malformed ratio exceeds threshold
    7. HEALTHY — none of the above
    """

    def __init__(
        self,
        config: SourceHealthConfig | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config or SourceHealthConfig()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def assess(
        self,
        *,
        source_name: str,
        outcomes: list[_FetchOutcome],
        consecutive_empty: int = 0,
        freshness_age_seconds: float | None = None,
    ) -> SourceHealthAssessment:
        now = self._clock()

        if not outcomes:
            return SourceHealthAssessment(
                state=SourceDegradationState.HEALTHY,
                reasons=["no fetch history"],
                source=source_name,
                assessed_at=now,
                signals={"total_fetches": 0},
            )

        total = len(outcomes)
        successes = sum(1 for o in outcomes if o.success)
        failures = total - successes
        success_ratio = successes / total if total > 0 else 0.0

        total_records = sum(o.total_records for o in outcomes if o.success)
        total_malformed = sum(o.malformed_count for o in outcomes if o.success)
        total_events = sum(o.events_emitted for o in outcomes if o.success)
        malformed_ratio = total_malformed / total_records if total_records > 0 else 0.0

        signals: dict[str, Any] = {
            "total_fetches": total,
            "successful_fetches": successes,
            "failed_fetches": failures,
            "success_ratio": round(success_ratio, 4),
            "total_records": total_records,
            "total_malformed": total_malformed,
            "total_events": total_events,
            "malformed_ratio": round(malformed_ratio, 4),
            "consecutive_empty_fetches": consecutive_empty,
            "freshness_age_seconds": freshness_age_seconds,
            "max_freshness_age_seconds": self._config.max_freshness_age_seconds,
        }

        if success_ratio < self._config.min_success_ratio:
            recent_failures_for_reason = [o for o in outcomes if not o.success]
            if recent_failures_for_reason:
                last_failure = recent_failures_for_reason[-1]
                reason_lower = (last_failure.failure_reason or "").lower()
                if "rate" in reason_lower and "limit" in reason_lower:
                    return SourceHealthAssessment(
                        state=SourceDegradationState.RATE_LIMITED,
                        reasons=[
                            f"low success ratio + recent rate-limit: {last_failure.failure_reason}"
                        ],
                        source=source_name,
                        assessed_at=now,
                        signals=signals,
                    )
                if "structural" in reason_lower or "structure" in reason_lower:
                    return SourceHealthAssessment(
                        state=SourceDegradationState.STRUCTURALLY_CHANGED,
                        reasons=[
                            f"low success ratio + recent structural change: "
                            f"{last_failure.failure_reason}"
                        ],
                        source=source_name,
                        assessed_at=now,
                        signals=signals,
                    )
            return SourceHealthAssessment(
                state=SourceDegradationState.UNREACHABLE,
                reasons=[
                    f"success ratio {success_ratio:.2%} below threshold "
                    f"{self._config.min_success_ratio:.2%}"
                ],
                source=source_name,
                assessed_at=now,
                signals=signals,
            )

        recent_failures = [o for o in outcomes if not o.success]
        if recent_failures:
            last_failure = recent_failures[-1]
            reason_lower = (last_failure.failure_reason or "").lower()
            if "rate" in reason_lower and "limit" in reason_lower:
                return SourceHealthAssessment(
                    state=SourceDegradationState.RATE_LIMITED,
                    reasons=[f"recent rate-limit failure: {last_failure.failure_reason}"],
                    source=source_name,
                    assessed_at=now,
                    signals=signals,
                )
            if "structural" in reason_lower or "structure" in reason_lower:
                return SourceHealthAssessment(
                    state=SourceDegradationState.STRUCTURALLY_CHANGED,
                    reasons=[f"recent structural-change failure: {last_failure.failure_reason}"],
                    source=source_name,
                    assessed_at=now,
                    signals=signals,
                )

        if (
            self._config.max_freshness_age_seconds is not None
            and freshness_age_seconds is not None
            and freshness_age_seconds > self._config.max_freshness_age_seconds
        ):
            return SourceHealthAssessment(
                state=SourceDegradationState.STALE,
                reasons=[
                    f"freshness age {freshness_age_seconds:.0f}s exceeds threshold "
                    f"{self._config.max_freshness_age_seconds:.0f}s"
                ],
                source=source_name,
                assessed_at=now,
                signals=signals,
            )

        if consecutive_empty >= self._config.max_empty_fetches:
            return SourceHealthAssessment(
                state=SourceDegradationState.EMPTY_RESULT,
                reasons=[
                    f"{consecutive_empty} consecutive empty fetches "
                    f"(threshold: {self._config.max_empty_fetches})"
                ],
                source=source_name,
                assessed_at=now,
                signals=signals,
            )

        if (
            self._config.min_expected_records is not None
            and total_records > 0
            and total_records < self._config.min_expected_records
        ):
            return SourceHealthAssessment(
                state=SourceDegradationState.EMPTY_RESULT,
                reasons=[
                    f"total records {total_records} below minimum expected "
                    f"{self._config.min_expected_records}"
                ],
                source=source_name,
                assessed_at=now,
                signals=signals,
            )

        if total_records > 0 and malformed_ratio > self._config.max_malformed_ratio:
            return SourceHealthAssessment(
                state=SourceDegradationState.PARTIALLY_PARSEABLE,
                reasons=[
                    f"malformed ratio {malformed_ratio:.2%} exceeds threshold "
                    f"{self._config.max_malformed_ratio:.2%}"
                ],
                source=source_name,
                assessed_at=now,
                signals=signals,
            )

        return SourceHealthAssessment(
            state=SourceDegradationState.HEALTHY,
            reasons=[],
            source=source_name,
            assessed_at=now,
            signals=signals,
        )
