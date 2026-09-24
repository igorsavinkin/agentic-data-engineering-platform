"""Source freshness failure integration test (TASK-106).

Demonstrates the full lifecycle when a source adapter stops producing events:

    Failure → Detection → Metric/log → Alert → Recovery → No silent data loss

Uses deterministic clock injection throughout. Exercises the complete
monitoring stack: SourceMetrics → SourceHealthTracker → SourceHealthAssessor
→ _derive_alerts → _derive_overall_status.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from libs.observability.health_assessment import (
    FreshnessState,
    SourceDegradationState,
    SourceHealthConfig,
    SourceHealthTracker,
)
from libs.observability.source_metrics import SourceMetrics
from services.agent.tools import _derive_alerts
from services.api.repositories.pipeline_status import _derive_overall_status

FROZEN_TIME = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
FRESHNESS_THRESHOLD_SECONDS = 3600.0


def _make_clock(at: datetime | None = None) -> list:
    base = at or FROZEN_TIME
    return [base]


def _advance(clock_list: list, seconds: float) -> None:
    clock_list[0] = clock_list[0] + timedelta(seconds=seconds)


def _simulate_adapter_cycle(
    *,
    metrics: SourceMetrics,
    tracker: SourceHealthTracker,
    events_produced: int,
    clock_list: list,
    step_seconds: float = 900.0,
) -> None:
    """Simulate one adapter fetch-publish cycle.

    Advances the clock, records the fetch outcome in both metrics and
    tracker layers, and feeds freshness age into the tracker.
    """
    _advance(clock_list, step_seconds)
    if events_produced > 0:
        metrics.record_fetch_success(
            records_collected=events_produced,
            records_emitted=events_produced,
        )
        tracker.record_fetch_success(
            events_emitted=events_produced,
            total_records=events_produced,
        )
    else:
        metrics.record_fetch_success(records_collected=0, records_emitted=0)
        tracker.record_fetch_success(events_emitted=0, total_records=0)
    tracker.update_freshness_age(metrics.get_freshness_age_seconds())


def _build_source_health_dict(
    tracker: SourceHealthTracker,
) -> dict[str, object]:
    """Build a source health dict matching what _derive_alerts expects."""
    assessment = tracker.assess()
    freshness_state = tracker.get_freshness_state()
    overall = _derive_overall_status(
        state=assessment.state.value,
        freshness_state=freshness_state.value,
    )
    return {
        "source_name": assessment.source,
        "overall_status": overall,
        "degradation_state": assessment.state.value,
        "freshness_state": freshness_state.value,
        "freshness_age_seconds": assessment.signals.get("freshness_age_seconds"),
        "assessed_at": assessment.assessed_at.isoformat(),
        "reasons": assessment.reasons,
        "signals": assessment.signals,
    }


class TestSourceStopsProducing:
    """Failure: adapter stops producing events, freshness detects it."""

    def test_source_staleness_detected_after_producer_stops(self) -> None:
        """When a source stops, freshness age exceeds threshold → STALE."""
        clock_list = _make_clock()
        config = SourceHealthConfig(max_freshness_age_seconds=FRESHNESS_THRESHOLD_SECONDS)
        metrics = SourceMetrics(source_name="test_retailer", clock=lambda: clock_list[0])
        tracker = SourceHealthTracker(
            source_name="test_retailer",
            config=config,
            clock=lambda: clock_list[0],
        )

        for _ in range(3):
            _simulate_adapter_cycle(
                metrics=metrics,
                tracker=tracker,
                events_produced=10,
                clock_list=clock_list,
            )

        assessment = tracker.assess()
        assert assessment.state == SourceDegradationState.HEALTHY
        assert tracker.get_freshness_state() == FreshnessState.FRESH

        for _ in range(5):
            _simulate_adapter_cycle(
                metrics=metrics,
                tracker=tracker,
                events_produced=0,
                clock_list=clock_list,
            )

        assessment = tracker.assess()
        assert assessment.state == SourceDegradationState.STALE
        assert tracker.get_freshness_state() == FreshnessState.STALE

        age = metrics.get_freshness_age_seconds()
        assert age is not None
        assert age > FRESHNESS_THRESHOLD_SECONDS


class TestStaleAlerts:
    """Detection: stale source generates a source_stale alert."""

    def test_stale_source_produces_alert(self) -> None:
        """_derive_alerts emits source_stale when overall_status is stale."""
        clock_list = _make_clock()
        config = SourceHealthConfig(max_freshness_age_seconds=FRESHNESS_THRESHOLD_SECONDS)
        metrics = SourceMetrics(source_name="test_retailer", clock=lambda: clock_list[0])
        tracker = SourceHealthTracker(
            source_name="test_retailer",
            config=config,
            clock=lambda: clock_list[0],
        )

        _simulate_adapter_cycle(
            metrics=metrics,
            tracker=tracker,
            events_produced=10,
            clock_list=clock_list,
        )

        _advance(clock_list, 7200)
        tracker.update_freshness_age(metrics.get_freshness_age_seconds())
        tracker.record_fetch_success(events_emitted=0, total_records=0)

        source_health = _build_source_health_dict(tracker)
        assert source_health["overall_status"] == "stale"

        alerts = _derive_alerts(runs=[], sources=[source_health])
        stale_alerts = [a for a in alerts if a.alert_type == "source_stale"]
        assert len(stale_alerts) == 1
        assert stale_alerts[0].severity == "medium"
        assert "test_retailer" in stale_alerts[0].message
        assert "stale" in stale_alerts[0].message

    def test_fresh_source_produces_no_stale_alert(self) -> None:
        """A fresh source does not generate a source_stale alert."""
        clock_list = _make_clock()
        config = SourceHealthConfig(max_freshness_age_seconds=FRESHNESS_THRESHOLD_SECONDS)
        metrics = SourceMetrics(source_name="test_retailer", clock=lambda: clock_list[0])
        tracker = SourceHealthTracker(
            source_name="test_retailer",
            config=config,
            clock=lambda: clock_list[0],
        )

        _simulate_adapter_cycle(
            metrics=metrics,
            tracker=tracker,
            events_produced=10,
            clock_list=clock_list,
        )

        source_health = _build_source_health_dict(tracker)
        assert source_health["overall_status"] == "healthy"

        alerts = _derive_alerts(runs=[], sources=[source_health])
        stale_alerts = [a for a in alerts if a.alert_type == "source_stale"]
        assert len(stale_alerts) == 0


class TestDownstreamProtection:
    """No silent data loss: stale sources are not reported as healthy."""

    def test_stale_freshness_maps_to_stale_status(self) -> None:
        """_derive_overall_status returns 'stale' when freshness_state is stale."""
        assert _derive_overall_status(state="healthy", freshness_state="stale") == "stale"

    def test_healthy_state_with_fresh_freshness_is_healthy(self) -> None:
        """Healthy state + fresh freshness → overall healthy."""
        result = _derive_overall_status(state="healthy", freshness_state="fresh")
        assert result == "healthy"

    def test_stale_assessment_maps_to_stale_status(self) -> None:
        """STALE degradation state → overall stale regardless of freshness."""
        assert _derive_overall_status(state="stale", freshness_state="fresh") == "stale"
        assert _derive_overall_status(state="stale", freshness_state="stale") == "stale"

    def test_degraded_states_map_to_degraded_status(self) -> None:
        """Degraded states (unreachable, etc.) → overall degraded."""
        for state in ("unreachable", "rate_limited", "structurally_changed"):
            assert _derive_overall_status(state=state, freshness_state="fresh") == "degraded"


class TestRecovery:
    """Recovery: adapter resumes producing, freshness refreshes, state recovers."""

    def test_recovery_after_staleness(self) -> None:
        """Source resumes → freshness refreshes → HEALTHY restored."""
        clock_list = _make_clock()
        config = SourceHealthConfig(max_freshness_age_seconds=FRESHNESS_THRESHOLD_SECONDS)
        metrics = SourceMetrics(source_name="test_retailer", clock=lambda: clock_list[0])
        tracker = SourceHealthTracker(
            source_name="test_retailer",
            config=config,
            clock=lambda: clock_list[0],
        )

        _simulate_adapter_cycle(
            metrics=metrics,
            tracker=tracker,
            events_produced=10,
            clock_list=clock_list,
        )

        _advance(clock_list, 7200)
        tracker.update_freshness_age(metrics.get_freshness_age_seconds())
        tracker.record_fetch_success(events_emitted=0, total_records=0)

        assert tracker.assess().state == SourceDegradationState.STALE
        assert tracker.get_freshness_state() == FreshnessState.STALE

        source_health_stale = _build_source_health_dict(tracker)
        alerts_stale = _derive_alerts(runs=[], sources=[source_health_stale])
        assert any(a.alert_type == "source_stale" for a in alerts_stale)

        _simulate_adapter_cycle(
            metrics=metrics,
            tracker=tracker,
            events_produced=8,
            clock_list=clock_list,
        )

        assessment = tracker.assess()
        assert assessment.state == SourceDegradationState.HEALTHY
        assert tracker.get_freshness_state() == FreshnessState.FRESH

        source_health_recovered = _build_source_health_dict(tracker)
        assert source_health_recovered["overall_status"] == "healthy"

        alerts_recovered = _derive_alerts(runs=[], sources=[source_health_recovered])
        assert not any(a.alert_type == "source_stale" for a in alerts_recovered)


class TestZeroResultsDoNotMaskStaleness:
    """Zero-result fetches must not refresh freshness and hide staleness."""

    def test_zero_results_keep_freshness_aging(self) -> None:
        """Adapter returning zero results does not reset the freshness clock."""
        clock_list = _make_clock()
        config = SourceHealthConfig(max_freshness_age_seconds=FRESHNESS_THRESHOLD_SECONDS)
        metrics = SourceMetrics(source_name="test_retailer", clock=lambda: clock_list[0])
        tracker = SourceHealthTracker(
            source_name="test_retailer",
            config=config,
            clock=lambda: clock_list[0],
        )

        _simulate_adapter_cycle(
            metrics=metrics,
            tracker=tracker,
            events_produced=10,
            clock_list=clock_list,
        )
        original_fetch = metrics.get_last_successful_fetch()
        assert original_fetch is not None

        for _ in range(5):
            _simulate_adapter_cycle(
                metrics=metrics,
                tracker=tracker,
                events_produced=0,
                clock_list=clock_list,
            )

        assert metrics.get_last_successful_fetch() == original_fetch

        age = metrics.get_freshness_age_seconds()
        assert age is not None
        assert age > FRESHNESS_THRESHOLD_SECONDS
        assert tracker.get_freshness_state() == FreshnessState.STALE
        assert tracker.assess().state == SourceDegradationState.STALE
