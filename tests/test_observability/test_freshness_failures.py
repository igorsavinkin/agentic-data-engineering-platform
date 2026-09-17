"""Tests for freshness failure scenarios (TASK-054).

Covers:
- fresh source (within threshold)
- threshold boundary (exactly at threshold)
- stale source (exceeded threshold)
- never-successful source (no usable data ever)
- failed run after prior success (within freshness threshold)
- zero-result semantics (does not refresh freshness)
- recovery refreshes state (after stale/degraded)
- retry without usable data does not refresh freshness

All tests use deterministic clock injection for reproducibility.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from libs.observability.health_assessment import (
    FreshnessState,
    SourceDegradationState,
    SourceHealthAssessor,
    SourceHealthConfig,
    SourceHealthTracker,
    _FetchOutcome,
)
from libs.observability.source_metrics import SourceFreshness, SourceMetrics

FROZEN_TIME = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)


def _make_clock(at: datetime | None = None) -> list:
    """Return a mutable clock list usable as a deterministic time source.

    The list holds a single datetime element. Pass ``lambda: clock_list[0]``
    as the ``clock`` parameter. Mutate ``clock_list[0]`` to advance time.
    """
    base = at or FROZEN_TIME
    return [base]


def _advance(clock_list: list, seconds: float) -> None:
    """Advance the mutable clock by the given number of seconds."""
    clock_list[0] = clock_list[0] + timedelta(seconds=seconds)


# ---------------------------------------------------------------------------
# SourceFreshness with clock injection
# ---------------------------------------------------------------------------


class TestSourceFreshnessClockInjection:
    """Verify SourceFreshness works with injected clocks."""

    def test_freshness_uses_injected_clock(self) -> None:
        clock_list = _make_clock()
        freshness = SourceFreshness(clock=lambda: clock_list[0])

        freshness.record_success()
        assert freshness.get_last_successful_fetch() == FROZEN_TIME

    def test_freshness_age_with_frozen_clock(self) -> None:
        clock_list = _make_clock()
        freshness = SourceFreshness(clock=lambda: clock_list[0])

        freshness.record_success()
        _advance(clock_list, 3600)

        age = freshness.calculate_freshness_age_seconds()
        assert age is not None
        assert abs(age - 3600.0) < 0.001

    def test_explicit_timestamp_overrides_clock(self) -> None:
        clock_list = _make_clock()
        freshness = SourceFreshness(clock=lambda: clock_list[0])

        explicit_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        freshness.record_success(explicit_ts)
        assert freshness.get_last_successful_fetch() == explicit_ts


# ---------------------------------------------------------------------------
# SourceMetrics: zero-result does not refresh freshness
# ---------------------------------------------------------------------------


class TestZeroResultFreshnessSemantics:
    """TASK-054: zero-result fetches must NOT refresh freshness."""

    def test_zero_result_does_not_set_freshness(self) -> None:
        """A zero-result fetch never sets the freshness timestamp."""
        clock_list = _make_clock()
        metrics = SourceMetrics(source_name="test", clock=lambda: clock_list[0])

        metrics.record_fetch_success(records_collected=0, records_emitted=0)

        assert metrics.get_last_successful_fetch() is None
        assert metrics.get_freshness_age_seconds() is None

    def test_zero_result_does_not_refresh_existing_freshness(self) -> None:
        """A zero-result fetch does not update an existing freshness timestamp."""
        clock_list = _make_clock()
        metrics = SourceMetrics(source_name="test", clock=lambda: clock_list[0])

        metrics.record_fetch_success(records_collected=5, records_emitted=5)
        original_ts = metrics.get_last_successful_fetch()
        assert original_ts == FROZEN_TIME

        _advance(clock_list, 1800)
        metrics.record_fetch_success(records_collected=0, records_emitted=0)

        assert metrics.get_last_successful_fetch() == original_ts

    def test_records_emitted_refreshes_freshness(self) -> None:
        """A fetch with records_emitted > 0 does refresh freshness."""
        clock_list = _make_clock()
        metrics = SourceMetrics(source_name="test", clock=lambda: clock_list[0])

        metrics.record_fetch_success(records_collected=5, records_emitted=5)
        assert metrics.get_last_successful_fetch() == FROZEN_TIME

        _advance(clock_list, 600)
        metrics.record_fetch_success(records_collected=3, records_emitted=3)

        expected = FROZEN_TIME + timedelta(seconds=600)
        assert metrics.get_last_successful_fetch() == expected


# ---------------------------------------------------------------------------
# SourceHealthAssessor: STALE state detection
# ---------------------------------------------------------------------------


class TestStaleStateDetection:
    """TASK-054: assessor detects STALE state from freshness age."""

    def test_fresh_source_within_threshold(self) -> None:
        """Source with freshness age below threshold is not STALE."""
        clock_list = _make_clock()
        config = SourceHealthConfig(max_freshness_age_seconds=3600)
        assessor = SourceHealthAssessor(config, clock=lambda: clock_list[0])

        outcomes = [
            _FetchOutcome(success=True, events_emitted=5, total_records=5),
        ]
        result = assessor.assess(
            source_name="test",
            outcomes=outcomes,
            freshness_age_seconds=1800.0,
        )
        assert result.state == SourceDegradationState.HEALTHY
        assert result.signals["freshness_age_seconds"] == 1800.0

    def test_threshold_boundary_exactly_at_threshold(self) -> None:
        """Freshness age exactly at threshold is still FRESH (not exceeded)."""
        clock_list = _make_clock()
        config = SourceHealthConfig(max_freshness_age_seconds=3600)
        assessor = SourceHealthAssessor(config, clock=lambda: clock_list[0])

        outcomes = [
            _FetchOutcome(success=True, events_emitted=5, total_records=5),
        ]
        result = assessor.assess(
            source_name="test",
            outcomes=outcomes,
            freshness_age_seconds=3600.0,
        )
        assert result.state == SourceDegradationState.HEALTHY

    def test_stale_source_exceeds_threshold(self) -> None:
        """Source with freshness age above threshold is STALE."""
        clock_list = _make_clock()
        config = SourceHealthConfig(max_freshness_age_seconds=3600)
        assessor = SourceHealthAssessor(config, clock=lambda: clock_list[0])

        outcomes = [
            _FetchOutcome(success=True, events_emitted=5, total_records=5),
        ]
        result = assessor.assess(
            source_name="test",
            outcomes=outcomes,
            freshness_age_seconds=3601.0,
        )
        assert result.state == SourceDegradationState.STALE
        assert any("freshness age" in r for r in result.reasons)

    def test_stale_not_checked_when_threshold_disabled(self) -> None:
        """STALE is not detected when max_freshness_age_seconds is None."""
        clock_list = _make_clock()
        config = SourceHealthConfig(max_freshness_age_seconds=None)
        assessor = SourceHealthAssessor(config, clock=lambda: clock_list[0])

        outcomes = [
            _FetchOutcome(success=True, events_emitted=5, total_records=5),
        ]
        result = assessor.assess(
            source_name="test",
            outcomes=outcomes,
            freshness_age_seconds=999999.0,
        )
        assert result.state == SourceDegradationState.HEALTHY

    def test_stale_not_checked_when_no_freshness_data(self) -> None:
        """STALE is not detected when freshness_age_seconds is None."""
        clock_list = _make_clock()
        config = SourceHealthConfig(max_freshness_age_seconds=3600)
        assessor = SourceHealthAssessor(config, clock=lambda: clock_list[0])

        outcomes = [
            _FetchOutcome(success=True, events_emitted=5, total_records=5),
        ]
        result = assessor.assess(
            source_name="test",
            outcomes=outcomes,
            freshness_age_seconds=None,
        )
        assert result.state == SourceDegradationState.HEALTHY

    def test_stale_signals_include_freshness(self) -> None:
        """STALE assessment includes freshness signals."""
        clock_list = _make_clock()
        config = SourceHealthConfig(max_freshness_age_seconds=3600)
        assessor = SourceHealthAssessor(config, clock=lambda: clock_list[0])

        outcomes = [
            _FetchOutcome(success=True, events_emitted=5, total_records=5),
        ]
        result = assessor.assess(
            source_name="test",
            outcomes=outcomes,
            freshness_age_seconds=7200.0,
        )
        assert result.signals["freshness_age_seconds"] == 7200.0
        assert result.signals["max_freshness_age_seconds"] == 3600.0

    def test_active_failure_takes_priority_over_stale(self) -> None:
        """UNREACHABLE takes priority over STALE when both apply."""
        clock_list = _make_clock()
        config = SourceHealthConfig(
            min_success_ratio=0.5,
            max_freshness_age_seconds=3600,
        )
        assessor = SourceHealthAssessor(config, clock=lambda: clock_list[0])

        outcomes = [
            _FetchOutcome(success=False, failure_reason="timeout"),
            _FetchOutcome(success=False, failure_reason="connection refused"),
            _FetchOutcome(success=True, events_emitted=5, total_records=5),
        ]
        result = assessor.assess(
            source_name="test",
            outcomes=outcomes,
            freshness_age_seconds=99999.0,
        )
        assert result.state == SourceDegradationState.UNREACHABLE


# ---------------------------------------------------------------------------
# SourceHealthTracker: freshness state and integration
# ---------------------------------------------------------------------------


class TestHealthTrackerFreshness:
    """TASK-054: tracker integrates freshness into health assessment."""

    def test_never_collected_freshness_state(self) -> None:
        """Tracker with no freshness data returns NEVER_COLLECTED."""
        tracker = SourceHealthTracker(
            source_name="test",
            config=SourceHealthConfig(max_freshness_age_seconds=3600),
        )
        assert tracker.get_freshness_state() == FreshnessState.NEVER_COLLECTED

    def test_fresh_state_within_threshold(self) -> None:
        """Tracker with freshness within threshold returns FRESH."""
        tracker = SourceHealthTracker(
            source_name="test",
            config=SourceHealthConfig(max_freshness_age_seconds=3600),
        )
        tracker.update_freshness_age(1800.0)
        assert tracker.get_freshness_state() == FreshnessState.FRESH

    def test_stale_state_exceeds_threshold(self) -> None:
        """Tracker with freshness exceeding threshold returns STALE."""
        tracker = SourceHealthTracker(
            source_name="test",
            config=SourceHealthConfig(max_freshness_age_seconds=3600),
        )
        tracker.update_freshness_age(3601.0)
        assert tracker.get_freshness_state() == FreshnessState.STALE

    def test_fresh_state_when_threshold_disabled(self) -> None:
        """Tracker returns FRESH when no threshold is configured."""
        tracker = SourceHealthTracker(
            source_name="test",
            config=SourceHealthConfig(max_freshness_age_seconds=None),
        )
        tracker.update_freshness_age(999999.0)
        assert tracker.get_freshness_state() == FreshnessState.FRESH

    def test_assess_with_stale_freshness(self) -> None:
        """Tracker.assess() returns STALE when freshness is exceeded."""
        clock_list = _make_clock()
        tracker = SourceHealthTracker(
            source_name="test",
            config=SourceHealthConfig(max_freshness_age_seconds=3600),
            clock=lambda: clock_list[0],
        )
        tracker.record_fetch_success(events_emitted=5, total_records=5)
        tracker.update_freshness_age(7200.0)

        assessment = tracker.assess()
        assert assessment.state == SourceDegradationState.STALE

    def test_clock_injection_in_tracker(self) -> None:
        """Tracker uses injected clock for outcome timestamps."""
        clock_list = _make_clock()
        tracker = SourceHealthTracker(
            source_name="test",
            clock=lambda: clock_list[0],
        )
        tracker.record_fetch_success(events_emitted=5, total_records=5)
        _advance(clock_list, 100)
        tracker.record_fetch_failure("timeout")

        assessment = tracker.assess()
        assert assessment.signals["total_fetches"] == 2


# ---------------------------------------------------------------------------
# Scenario tests: end-to-end freshness failure scenarios
# ---------------------------------------------------------------------------


class TestFreshnessFailureScenarios:
    """TASK-054: complete freshness failure scenarios.

    These tests simulate realistic freshness lifecycle scenarios using
    deterministic clocks and the full tracker + metrics stack.
    """

    def test_scenario_fresh_source(self) -> None:
        """Source with recent usable data is fresh and healthy."""
        clock_list = _make_clock()
        config = SourceHealthConfig(max_freshness_age_seconds=3600)
        tracker = SourceHealthTracker(
            source_name="premium_retailer",
            config=config,
            clock=lambda: clock_list[0],
        )
        metrics = SourceMetrics(
            source_name="premium_retailer",
            clock=lambda: clock_list[0],
        )

        metrics.record_fetch_success(records_collected=10, records_emitted=10)
        tracker.record_fetch_success(events_emitted=10, total_records=10)
        tracker.update_freshness_age(metrics.get_freshness_age_seconds())

        _advance(clock_list, 1800)

        assessment = tracker.assess()
        assert assessment.state == SourceDegradationState.HEALTHY
        assert tracker.get_freshness_state() == FreshnessState.FRESH
        age = metrics.get_freshness_age_seconds()
        assert age is not None
        assert 1799 < age < 1801

    def test_scenario_threshold_boundary(self) -> None:
        """Source exactly at threshold boundary is still fresh."""
        clock_list = _make_clock()
        config = SourceHealthConfig(max_freshness_age_seconds=3600)
        tracker = SourceHealthTracker(
            source_name="premium_retailer",
            config=config,
            clock=lambda: clock_list[0],
        )
        metrics = SourceMetrics(
            source_name="premium_retailer",
            clock=lambda: clock_list[0],
        )

        metrics.record_fetch_success(records_collected=10, records_emitted=10)
        tracker.record_fetch_success(events_emitted=10, total_records=10)

        _advance(clock_list, 3600)
        tracker.update_freshness_age(metrics.get_freshness_age_seconds())

        assessment = tracker.assess()
        assert assessment.state == SourceDegradationState.HEALTHY
        assert tracker.get_freshness_state() == FreshnessState.FRESH

    def test_scenario_stale_source(self) -> None:
        """Source that has not produced usable data for too long is STALE."""
        clock_list = _make_clock()
        config = SourceHealthConfig(max_freshness_age_seconds=3600)
        tracker = SourceHealthTracker(
            source_name="premium_retailer",
            config=config,
            clock=lambda: clock_list[0],
        )
        metrics = SourceMetrics(
            source_name="premium_retailer",
            clock=lambda: clock_list[0],
        )

        metrics.record_fetch_success(records_collected=10, records_emitted=10)
        tracker.record_fetch_success(events_emitted=10, total_records=10)

        _advance(clock_list, 7200)
        tracker.update_freshness_age(metrics.get_freshness_age_seconds())

        assessment = tracker.assess()
        assert assessment.state == SourceDegradationState.STALE
        assert tracker.get_freshness_state() == FreshnessState.STALE
        age = metrics.get_freshness_age_seconds()
        assert age is not None
        assert age > 3600

    def test_scenario_never_successful(self) -> None:
        """Source that has never produced usable data is NEVER_COLLECTED."""
        clock_list = _make_clock()
        config = SourceHealthConfig(max_freshness_age_seconds=3600)
        tracker = SourceHealthTracker(
            source_name="premium_retailer",
            config=config,
            clock=lambda: clock_list[0],
        )
        metrics = SourceMetrics(
            source_name="premium_retailer",
            clock=lambda: clock_list[0],
        )

        tracker.record_fetch_failure("connection refused")
        metrics.record_fetch_failure()

        _advance(clock_list, 7200)
        tracker.update_freshness_age(metrics.get_freshness_age_seconds())

        assert tracker.get_freshness_state() == FreshnessState.NEVER_COLLECTED
        assert metrics.get_last_successful_fetch() is None
        assert metrics.get_freshness_age_seconds() is None

    def test_scenario_failed_run_after_prior_success(self) -> None:
        """Source failing after prior success: still fresh if within threshold."""
        clock_list = _make_clock()
        config = SourceHealthConfig(
            min_success_ratio=0.3,
            max_freshness_age_seconds=3600,
        )
        tracker = SourceHealthTracker(
            source_name="premium_retailer",
            config=config,
            clock=lambda: clock_list[0],
        )
        metrics = SourceMetrics(
            source_name="premium_retailer",
            clock=lambda: clock_list[0],
        )

        metrics.record_fetch_success(records_collected=10, records_emitted=10)
        tracker.record_fetch_success(events_emitted=10, total_records=10)

        _advance(clock_list, 600)
        tracker.record_fetch_failure("timeout")
        metrics.record_fetch_failure()

        _advance(clock_list, 600)
        tracker.record_fetch_failure("connection refused")
        metrics.record_fetch_failure()

        tracker.update_freshness_age(metrics.get_freshness_age_seconds())

        assert tracker.get_freshness_state() == FreshnessState.FRESH
        age = metrics.get_freshness_age_seconds()
        assert age is not None
        assert age < 3600

    def test_scenario_zero_result_semantics(self) -> None:
        """Zero-result fetches do not refresh freshness."""
        clock_list = _make_clock()
        config = SourceHealthConfig(max_freshness_age_seconds=3600)
        tracker = SourceHealthTracker(
            source_name="premium_retailer",
            config=config,
            clock=lambda: clock_list[0],
        )
        metrics = SourceMetrics(
            source_name="premium_retailer",
            clock=lambda: clock_list[0],
        )

        metrics.record_fetch_success(records_collected=10, records_emitted=10)
        tracker.record_fetch_success(events_emitted=10, total_records=10)
        original_ts = metrics.get_last_successful_fetch()

        _advance(clock_list, 1800)
        metrics.record_fetch_success(records_collected=0, records_emitted=0)
        tracker.record_fetch_success(events_emitted=0, total_records=0)

        assert metrics.get_last_successful_fetch() == original_ts
        tracker.update_freshness_age(metrics.get_freshness_age_seconds())

        age = metrics.get_freshness_age_seconds()
        assert age is not None
        assert 1799 < age < 1801

    def test_scenario_recovery_refreshes_state(self) -> None:
        """Recovery after stale state refreshes freshness."""
        clock_list = _make_clock()
        config = SourceHealthConfig(max_freshness_age_seconds=3600)
        tracker = SourceHealthTracker(
            source_name="premium_retailer",
            config=config,
            clock=lambda: clock_list[0],
        )
        metrics = SourceMetrics(
            source_name="premium_retailer",
            clock=lambda: clock_list[0],
        )

        metrics.record_fetch_success(records_collected=10, records_emitted=10)
        tracker.record_fetch_success(events_emitted=10, total_records=10)

        _advance(clock_list, 7200)
        tracker.update_freshness_age(metrics.get_freshness_age_seconds())
        assert tracker.get_freshness_state() == FreshnessState.STALE

        metrics.record_fetch_success(records_collected=5, records_emitted=5)
        tracker.record_fetch_success(events_emitted=5, total_records=5)
        tracker.update_freshness_age(metrics.get_freshness_age_seconds())

        assert tracker.get_freshness_state() == FreshnessState.FRESH
        assessment = tracker.assess()
        assert assessment.state == SourceDegradationState.HEALTHY
        age = metrics.get_freshness_age_seconds()
        assert age is not None
        assert age < 1

    def test_scenario_retry_without_usable_data(self) -> None:
        """Retry that succeeds with zero data does NOT refresh freshness."""
        clock_list = _make_clock()
        config = SourceHealthConfig(max_freshness_age_seconds=3600)
        tracker = SourceHealthTracker(
            source_name="premium_retailer",
            config=config,
            clock=lambda: clock_list[0],
        )
        metrics = SourceMetrics(
            source_name="premium_retailer",
            clock=lambda: clock_list[0],
        )

        metrics.record_fetch_success(records_collected=10, records_emitted=10)
        tracker.record_fetch_success(events_emitted=10, total_records=10)
        original_ts = metrics.get_last_successful_fetch()

        _advance(clock_list, 3000)

        tracker.record_fetch_failure("timeout")
        metrics.record_fetch_failure()

        _advance(clock_list, 301)
        metrics.record_fetch_success(records_collected=0, records_emitted=0)
        tracker.record_fetch_success(events_emitted=0, total_records=0)

        _advance(clock_list, 300)
        metrics.record_fetch_success(records_collected=0, records_emitted=0)
        tracker.record_fetch_success(events_emitted=0, total_records=0)

        assert metrics.get_last_successful_fetch() == original_ts
        tracker.update_freshness_age(metrics.get_freshness_age_seconds())

        age = metrics.get_freshness_age_seconds()
        assert age is not None
        assert age > 3600
        assert tracker.get_freshness_state() == FreshnessState.STALE
