"""Tests for source-level metrics and freshness tracking (TASK-040).

Validates:
- Success/failure metrics recording
- Record count tracking
- Latency observation
- Freshness calculation
- Zero-record success detection
- Metrics failure isolation (metrics errors don't break ingestion)
"""

import time
from datetime import datetime, timedelta, timezone

import pytest

from libs.observability.source_metrics import (
    SourceFreshness,
    SourceMetric,
    SourceMetrics,
)


class TestSourceMetrics:
    """Test source metrics counter operations."""

    def test_initial_state(self) -> None:
        """Metrics start at zero."""
        metrics = SourceMetrics(source_name="test_source")
        snapshot = metrics.snapshot()

        assert snapshot["source"] == "test_source"
        assert snapshot[SourceMetric.FETCH_ATTEMPTS] == 0
        assert snapshot[SourceMetric.FETCH_SUCCESS] == 0
        assert snapshot[SourceMetric.FETCH_FAILURE] == 0
        assert snapshot[SourceMetric.RECORDS_COLLECTED] == 0
        assert snapshot[SourceMetric.RECORDS_EMITTED] == 0
        assert snapshot[SourceMetric.ZERO_RECORD_FETCHES] == 0

    def test_increment_fetch_attempts(self) -> None:
        """Fetch attempts counter increments correctly."""
        metrics = SourceMetrics(source_name="test_source")

        metrics.increment(SourceMetric.FETCH_ATTEMPTS)
        metrics.increment(SourceMetric.FETCH_ATTEMPTS)
        metrics.increment(SourceMetric.FETCH_ATTEMPTS)

        assert metrics.snapshot()[SourceMetric.FETCH_ATTEMPTS] == 3

    def test_record_success_with_records(self) -> None:
        """Successful fetch with records updates all relevant counters."""
        metrics = SourceMetrics(source_name="fake_store")

        metrics.record_fetch_success(records_collected=10, records_emitted=8)

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.FETCH_SUCCESS] == 1
        assert snapshot[SourceMetric.RECORDS_COLLECTED] == 10
        assert snapshot[SourceMetric.RECORDS_EMITTED] == 8
        # Should NOT increment zero-record fetches
        assert snapshot[SourceMetric.ZERO_RECORD_FETCHES] == 0

    def test_record_success_zero_records(self) -> None:
        """Zero-record success is tracked separately."""
        metrics = SourceMetrics(source_name="best_buy")

        metrics.record_fetch_success(records_collected=0, records_emitted=0)

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.FETCH_SUCCESS] == 1
        assert snapshot[SourceMetric.RECORDS_COLLECTED] == 0
        assert snapshot[SourceMetric.RECORDS_EMITTED] == 0
        # SHOULD increment zero-record fetches
        assert snapshot[SourceMetric.ZERO_RECORD_FETCHES] == 1

    def test_record_failure(self) -> None:
        """Failed fetch increments failure counter."""
        metrics = SourceMetrics(source_name="test_source")

        metrics.record_fetch_failure()
        metrics.record_fetch_failure()

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.FETCH_FAILURE] == 2

    def test_latency_observation(self) -> None:
        """Latency tracker records observations correctly."""
        metrics = SourceMetrics(source_name="test_source")

        metrics.observe_latency(0.5)
        metrics.observe_latency(1.0)
        metrics.observe_latency(0.3)

        snapshot = metrics.snapshot()
        count = snapshot["source_fetch_latency_seconds_count"]
        total = snapshot["source_fetch_latency_seconds_sum"]
        min_val = snapshot["source_fetch_latency_seconds_min"]
        max_val = snapshot["source_fetch_latency_seconds_max"]
        assert isinstance(count, int) and count == 3
        assert isinstance(total, (int, float)) and abs(total - 1.8) < 0.01
        assert isinstance(min_val, (int, float)) and min_val == 0.3
        assert isinstance(max_val, (int, float)) and max_val == 1.0

    def test_time_fetch_context_manager(self) -> None:
        """Context manager records latency even on exception."""
        metrics = SourceMetrics(source_name="test_source")

        with pytest.raises(ValueError):
            with metrics.time_fetch():
                time.sleep(0.05)
                raise ValueError("test error")

        snapshot = metrics.snapshot()
        count = snapshot["source_fetch_latency_seconds_count"]
        total = snapshot["source_fetch_latency_seconds_sum"]
        assert isinstance(count, int) and count == 1
        assert isinstance(total, (int, float)) and total > 0

    def test_multiple_operations_accumulate(self) -> None:
        """Multiple fetch cycles accumulate correctly."""
        metrics = SourceMetrics(source_name="fake_store")

        # First successful fetch
        metrics.increment(SourceMetric.FETCH_ATTEMPTS)
        metrics.record_fetch_success(records_collected=10, records_emitted=9)

        # Second successful fetch with zero records
        metrics.increment(SourceMetric.FETCH_ATTEMPTS)
        metrics.record_fetch_success(records_collected=0, records_emitted=0)

        # Third failed fetch
        metrics.increment(SourceMetric.FETCH_ATTEMPTS)
        metrics.record_fetch_failure()

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.FETCH_ATTEMPTS] == 3
        assert snapshot[SourceMetric.FETCH_SUCCESS] == 2
        assert snapshot[SourceMetric.FETCH_FAILURE] == 1
        assert snapshot[SourceMetric.RECORDS_COLLECTED] == 10
        assert snapshot[SourceMetric.RECORDS_EMITTED] == 9
        assert snapshot[SourceMetric.ZERO_RECORD_FETCHES] == 1

    def test_snapshot_is_detached(self) -> None:
        """Snapshot returns a copy, not a live reference."""
        metrics = SourceMetrics(source_name="test_source")
        snapshot1 = metrics.snapshot()

        metrics.increment(SourceMetric.FETCH_ATTEMPTS)
        snapshot2 = metrics.snapshot()

        assert snapshot1[SourceMetric.FETCH_ATTEMPTS] == 0
        assert snapshot2[SourceMetric.FETCH_ATTEMPTS] == 1

    def test_metrics_exception_isolation(self) -> None:
        """Internal exceptions in metrics do not propagate."""
        metrics = SourceMetrics(source_name="test_source")

        # These should never raise even if internals fail
        try:
            metrics.increment(SourceMetric.FETCH_ATTEMPTS)
            metrics.record_fetch_success(10, 8)
            metrics.record_fetch_failure()
            metrics.observe_latency(0.5)
        except Exception as e:
            pytest.fail(f"Metrics should not raise: {e}")


class TestSourceFreshness:
    """Test freshness tracking."""

    def test_initial_state_no_fetch(self) -> None:
        """Freshness starts with no successful fetch."""
        freshness = SourceFreshness()

        assert freshness.get_last_successful_fetch() is None
        assert freshness.calculate_freshness_age_seconds() is None

    def test_record_success_updates_timestamp(self) -> None:
        """Recording success updates the timestamp."""
        freshness = SourceFreshness()
        now = datetime.now(timezone.utc)

        freshness.record_success(now)

        last = freshness.get_last_successful_fetch()
        assert last is not None
        assert abs((last - now).total_seconds()) < 1

    def test_record_success_defaults_to_now(self) -> None:
        """Recording without timestamp uses current time."""
        freshness = SourceFreshness()
        before = datetime.now(timezone.utc)

        freshness.record_success()

        after = datetime.now(timezone.utc)
        last = freshness.get_last_successful_fetch()
        assert last is not None
        assert before <= last <= after

    def test_freshness_age_calculation(self) -> None:
        """Age is calculated correctly from reference time."""
        freshness = SourceFreshness()
        past = datetime.now(timezone.utc) - timedelta(minutes=5)

        freshness.record_success(past)

        age = freshness.calculate_freshness_age_seconds(datetime.now(timezone.utc))
        assert age is not None
        assert 290 <= age <= 310  # ~5 minutes with tolerance

    def test_multiple_successes_keep_latest(self) -> None:
        """Multiple successes keep the most recent timestamp."""
        freshness = SourceFreshness()
        old = datetime.now(timezone.utc) - timedelta(hours=1)
        new = datetime.now(timezone.utc)

        freshness.record_success(old)
        freshness.record_success(new)

        last = freshness.get_last_successful_fetch()
        assert last is not None
        assert abs((last - new).total_seconds()) < 1

    def test_freshness_exception_isolation(self) -> None:
        """Freshness operations catch internal exceptions."""
        freshness = SourceFreshness()

        try:
            freshness.record_success()
            freshness.get_last_successful_fetch()
            freshness.calculate_freshness_age_seconds()
        except Exception as e:
            pytest.fail(f"Freshness should not raise: {e}")

    def test_snapshot_format(self) -> None:
        """Snapshot returns ISO-formatted timestamp or None."""
        freshness = SourceFreshness()

        # Before any success
        snap1 = freshness.snapshot()
        assert snap1["source_last_successful_fetch"] is None

        # After success
        now = datetime.now(timezone.utc)
        freshness.record_success(now)
        snap2 = freshness.snapshot()
        assert snap2["source_last_successful_fetch"] is not None
        assert "T" in snap2["source_last_successful_fetch"]  # ISO format


class TestSourceMetricsIntegration:
    """Integration tests for complete fetch cycle metrics."""

    def test_complete_fetch_cycle_success(self) -> None:
        """Simulate a complete successful fetch cycle."""
        metrics = SourceMetrics(source_name="fake_store")

        # Start fetch
        metrics.increment(SourceMetric.FETCH_ATTEMPTS)
        with metrics.time_fetch():
            time.sleep(0.01)  # Simulate work
            # Fetch succeeded with records
            metrics.record_fetch_success(records_collected=20, records_emitted=18)

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.FETCH_ATTEMPTS] == 1
        assert snapshot[SourceMetric.FETCH_SUCCESS] == 1
        assert snapshot[SourceMetric.RECORDS_COLLECTED] == 20
        assert snapshot[SourceMetric.RECORDS_EMITTED] == 18
        assert snapshot["source_fetch_latency_seconds_count"] == 1
        assert snapshot["source_last_successful_fetch"] is not None

    def test_complete_fetch_cycle_failure(self) -> None:
        """Simulate a complete failed fetch cycle."""
        metrics = SourceMetrics(source_name="best_buy")

        # Start fetch
        metrics.increment(SourceMetric.FETCH_ATTEMPTS)
        with metrics.time_fetch():
            time.sleep(0.01)
            # Fetch failed
            metrics.record_fetch_failure()

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.FETCH_ATTEMPTS] == 1
        assert snapshot[SourceMetric.FETCH_SUCCESS] == 0
        assert snapshot[SourceMetric.FETCH_FAILURE] == 1
        assert snapshot["source_fetch_latency_seconds_count"] == 1
        assert snapshot["source_last_successful_fetch"] is None

    def test_distinguish_zero_records_vs_failure(self) -> None:
        """Zero-record success is distinct from failure."""
        metrics = SourceMetrics(source_name="test_source")

        # Scenario 1: Source reachable but returned zero records
        metrics.increment(SourceMetric.FETCH_ATTEMPTS)
        metrics.record_fetch_success(records_collected=0, records_emitted=0)

        # Scenario 2: Source failed completely
        metrics.increment(SourceMetric.FETCH_ATTEMPTS)
        metrics.record_fetch_failure()

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.FETCH_SUCCESS] == 1  # Zero-record counts as success
        assert snapshot[SourceMetric.FETCH_FAILURE] == 1
        assert snapshot[SourceMetric.ZERO_RECORD_FETCHES] == 1

    def test_stale_detection_via_freshness(self) -> None:
        """Staleness can be detected by checking freshness age."""
        metrics = SourceMetrics(source_name="fake_store")

        # Simulate a fetch that happened 1 hour ago
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        metrics._freshness.record_success(one_hour_ago)

        age = metrics.get_freshness_age_seconds()
        assert age is not None
        assert 3500 <= age <= 3700  # ~1 hour

        # Stale threshold check (e.g., 30 minutes)
        is_stale = age > 1800
        assert is_stale is True


class TestTask049HealthMetrics:
    """TASK-049: health metrics for pages, retries, malformed, partial failures."""

    def test_initial_state_new_counters(self) -> None:
        """New counters start at zero."""
        metrics = SourceMetrics(source_name="test_source")
        snapshot = metrics.snapshot()

        assert snapshot[SourceMetric.PAGES_FETCHED] == 0
        assert snapshot[SourceMetric.RETRY_ATTEMPTS] == 0
        assert snapshot[SourceMetric.MALFORMED_RECORDS] == 0
        assert snapshot[SourceMetric.PARTIAL_FAILURES] == 0

    def test_record_pages_fetched(self) -> None:
        """Pages fetched counter increments correctly."""
        metrics = SourceMetrics(source_name="web_retailer")

        metrics.record_pages_fetched(3)

        assert metrics.snapshot()[SourceMetric.PAGES_FETCHED] == 3

    def test_record_pages_fetched_default(self) -> None:
        """Pages fetched defaults to incrementing by 1."""
        metrics = SourceMetrics(source_name="web_retailer")

        metrics.record_pages_fetched()
        metrics.record_pages_fetched()

        assert metrics.snapshot()[SourceMetric.PAGES_FETCHED] == 2

    def test_record_retry(self) -> None:
        """Retry attempts counter increments correctly."""
        metrics = SourceMetrics(source_name="web_retailer")

        metrics.record_retry()
        metrics.record_retry()
        metrics.record_retry()

        assert metrics.snapshot()[SourceMetric.RETRY_ATTEMPTS] == 3

    def test_record_malformed(self) -> None:
        """Malformed records counter increments correctly."""
        metrics = SourceMetrics(source_name="web_retailer")

        metrics.record_malformed(5)

        assert metrics.snapshot()[SourceMetric.MALFORMED_RECORDS] == 5

    def test_record_malformed_default(self) -> None:
        """Malformed records defaults to incrementing by 1."""
        metrics = SourceMetrics(source_name="web_retailer")

        metrics.record_malformed()

        assert metrics.snapshot()[SourceMetric.MALFORMED_RECORDS] == 1

    def test_record_partial_failure(self) -> None:
        """Partial failure counter increments correctly."""
        metrics = SourceMetrics(source_name="web_retailer")

        metrics.record_partial_failure()
        metrics.record_partial_failure()

        assert metrics.snapshot()[SourceMetric.PARTIAL_FAILURES] == 2

    def test_new_methods_exception_isolation(self) -> None:
        """New metric methods never raise even if internals fail."""
        metrics = SourceMetrics(source_name="test_source")

        try:
            metrics.record_pages_fetched(3)
            metrics.record_retry()
            metrics.record_malformed(5)
            metrics.record_partial_failure()
        except Exception as e:
            pytest.fail(f"New metric methods should not raise: {e}")

    def test_no_high_cardinality_labels(self) -> None:
        """Snapshot contains only low-cardinality keys — no URLs, IDs, or error text."""
        metrics = SourceMetrics(source_name="web_retailer")
        metrics.increment(SourceMetric.FETCH_ATTEMPTS)
        metrics.record_fetch_success(records_collected=10, records_emitted=8)
        metrics.record_pages_fetched(3)
        metrics.record_retry()
        metrics.record_malformed(2)
        metrics.record_partial_failure()

        snapshot = metrics.snapshot()
        snapshot_values = " ".join(str(v) for v in snapshot.values())

        forbidden_patterns = ["http", "html", "product_", "error", "exception", "traceback"]
        for pattern in forbidden_patterns:
            assert pattern not in snapshot_values.lower(), (
                f"Snapshot may contain high-cardinality data: '{pattern}'"
            )

    def test_freshness_state_after_success(self) -> None:
        """Freshness timestamp is set after a successful fetch."""
        metrics = SourceMetrics(source_name="web_retailer")

        assert metrics.get_last_successful_fetch() is None

        metrics.record_fetch_success(records_collected=5, records_emitted=5)

        assert metrics.get_last_successful_fetch() is not None
        assert metrics.get_freshness_age_seconds() is not None
        assert metrics.get_freshness_age_seconds() >= 0

    def test_freshness_not_updated_on_failure(self) -> None:
        """Freshness is NOT updated on failed fetches."""
        metrics = SourceMetrics(source_name="web_retailer")

        metrics.record_fetch_failure()

        assert metrics.get_last_successful_fetch() is None
        assert metrics.get_freshness_age_seconds() is None

    def test_degraded_run_snapshot(self) -> None:
        """Snapshot captures full health picture for a degraded run."""
        metrics = SourceMetrics(source_name="web_retailer")

        metrics.increment(SourceMetric.FETCH_ATTEMPTS)
        metrics.record_pages_fetched(2)
        metrics.record_retry()
        metrics.record_malformed(3)
        metrics.record_partial_failure()
        metrics.record_fetch_success(records_collected=15, records_emitted=12)

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.FETCH_ATTEMPTS] == 1
        assert snapshot[SourceMetric.FETCH_SUCCESS] == 1
        assert snapshot[SourceMetric.PAGES_FETCHED] == 2
        assert snapshot[SourceMetric.RETRY_ATTEMPTS] == 1
        assert snapshot[SourceMetric.MALFORMED_RECORDS] == 3
        assert snapshot[SourceMetric.PARTIAL_FAILURES] == 1
        assert snapshot[SourceMetric.RECORDS_COLLECTED] == 15
        assert snapshot[SourceMetric.RECORDS_EMITTED] == 12
        assert snapshot["source_last_successful_fetch"] is not None
