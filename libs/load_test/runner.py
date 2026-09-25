"""Load-test runner: orchestrates event production and measurement (TASK-108).

The runner coordinates the event generator, a produce function (injected for
testability), and the metrics collector.  It supports both time-bounded and
count-bounded runs, with configurable target rates.

The runner auto-scales the effective worker count when the configured value
is too low for the target rate.  Each thread handles ~50-100 eps of CPU-bound
event generation (GIL-limited); for I/O-bound Kafka produce calls, fewer
workers are needed since threads block on network I/O.
"""

from __future__ import annotations

import logging
import math
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

from libs.event_contracts import ProductObservationEvent
from libs.load_test.config import LoadTestSettings
from libs.load_test.event_generator import EventGenerator
from libs.load_test.lag_collector import LagCollector, LagQueryFn
from libs.load_test.latency_collector import LatencyCollector, PgQueryFn
from libs.load_test.metrics_collector import MetricsCollector
from libs.load_test.report import build_report, write_report

logger = logging.getLogger(__name__)

ProduceFn = Callable[[ProductObservationEvent], str]

_ESTIMATED_EPS_PER_WORKER = 50


class LoadTestRunner:
    """Orchestrate a load-test run.

    The runner is independent of specific source adapters: it generates
    synthetic canonical events and passes them to an injected produce
    function.  This allows testing against a real Kafka producer, a mock,
    or any other transport.

    Parameters
    ----------
    settings:
        Load-test configuration.
    produce_fn:
        Callable that publishes one event.  Should raise on failure.
    """

    def __init__(
        self,
        settings: LoadTestSettings,
        produce_fn: ProduceFn,
        diagnostic: bool = False,
        lag_query_fn: LagQueryFn | None = None,
        latency_collector: LatencyCollector | None = None,
        pg_query_fn: PgQueryFn | None = None,
    ) -> None:
        self._settings = settings
        self._produce_fn = produce_fn
        self._metrics = MetricsCollector(diagnostic=diagnostic)
        self._diagnostic = diagnostic
        self._run_id = str(uuid.uuid4())
        self._run_id_short = self._run_id.replace("-", "")
        self._lag_collector = LagCollector()
        self._lag_query_fn = lag_query_fn
        self._latency_collector = latency_collector
        self._pg_query_fn = pg_query_fn

    @property
    def metrics(self) -> MetricsCollector:
        return self._metrics

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def lag_collector(self) -> LagCollector:
        return self._lag_collector

    @property
    def latency_collector(self) -> LatencyCollector | None:
        return self._latency_collector

    def run(self) -> dict:
        """Execute the load test and return the structured report.

        The run respects both ``duration_sec`` and ``total_events`` limits;
        whichever is reached first stops the test.  If ``total_events`` is 0,
        only the time limit applies.
        """
        self._metrics.mark_start()
        stop_event = threading.Event()
        effective_workers = self._effective_worker_count()

        logger.info(
            "load_test_start",
            extra={
                "run_id": self._run_id,
                "target_events_per_sec": self._settings.target_events_per_sec,
                "duration_sec": self._settings.duration_sec,
                "total_events": self._settings.total_events,
                "worker_count": effective_workers,
            },
        )

        workers = self._start_workers(stop_event, effective_workers)
        resource_monitor = self._start_resource_monitor(stop_event)
        lag_monitor = self._start_lag_monitor(stop_event)
        pg_monitor = self._start_pg_latency_monitor(stop_event)

        self._wait_for_completion(stop_event, workers)

        stop_event.set()
        self._metrics.mark_end()

        for w in workers:
            w.join(timeout=5)
        resource_monitor.join(timeout=5)
        if lag_monitor is not None:
            lag_monitor.join(timeout=5)
        if pg_monitor is not None:
            pg_monitor.join(timeout=5)

        summary = self._metrics.get_summary()
        report = build_report(
            settings_dict=self._settings.model_dump(),
            metrics_summary=summary,
            run_id=self._run_id,
        )

        timing_breakdown = self._metrics.get_timing_breakdown()
        if timing_breakdown is not None:
            report["diagnostic_timing"] = timing_breakdown

        lag_report = self._lag_collector.to_report_dict()
        if lag_report is not None:
            report["consumer_lag"] = lag_report

        if self._latency_collector is not None:
            latency_report = self._latency_collector.to_report_dict()
            if latency_report is not None:
                report["processing_latency"] = latency_report

        output_path = write_report(report, self._settings.output_path)
        logger.info(
            "load_test_complete",
            extra={
                "run_id": self._run_id,
                "produced": summary["produced_count"],
                "errors": summary["error_count"],
                "throughput": summary["throughput_events_per_sec"],
                "output": str(output_path),
            },
        )

        return report

    def _effective_worker_count(self) -> int:
        """Scale workers up when the configured count can't sustain the rate."""
        configured = self._settings.worker_count
        if self._settings.disable_auto_scaling:
            return configured
        needed = math.ceil(self._settings.target_events_per_sec / _ESTIMATED_EPS_PER_WORKER * 1.5)
        effective = max(configured, min(needed, 64))
        total_events = self._settings.total_events
        if total_events > 0:
            effective = min(effective, max(total_events, 1))
        return effective

    def _start_workers(
        self,
        stop_event: threading.Event,
        effective_workers: int,
    ) -> list[threading.Thread]:
        """Start producer worker threads, each with its own event generator."""
        workers: list[threading.Thread] = []
        run_id_short = self._run_id_short
        source = self._settings.source_name
        base_seed = self._settings.seed
        for i in range(effective_workers):
            generator = EventGenerator(
                source=source,
                seed=base_seed + i,
                worker_id=i,
                run_id=run_id_short,
            )
            t = threading.Thread(
                target=self._worker_loop,
                args=(stop_event, i, generator, effective_workers),
                daemon=True,
                name=f"load-test-worker-{i}",
            )
            t.start()
            workers.append(t)
        return workers

    def _worker_loop(
        self,
        stop_event: threading.Event,
        worker_id: int,
        generator: EventGenerator,
        effective_workers: int,
    ) -> None:
        """Single worker loop: produce events at the target rate."""
        interval = effective_workers / self._settings.target_events_per_sec
        total_events_limit = self._settings.total_events
        produce_fn = self._produce_fn
        metrics = self._metrics
        monotonic = time.monotonic
        stop_is_set = stop_event.is_set
        warn = logger.warning
        diagnostic = self._diagnostic
        latency_collector = self._latency_collector

        iteration_start = monotonic()

        while not stop_is_set():
            if total_events_limit > 0 and metrics.produced_count >= total_events_limit:
                return

            t_gen_start = monotonic()
            event = generator.next_event()
            t_gen_ms = (monotonic() - t_gen_start) * 1000

            t0 = monotonic()
            try:
                produce_fn(event)
                t_produce_ms = (monotonic() - t0) * 1000
                metrics.record_latency(event.event_id, t_produce_ms)
                if latency_collector is not None:
                    latency_collector.record_produce(event.event_id, datetime.now(timezone.utc))
            except Exception:
                t_produce_ms = (monotonic() - t0) * 1000
                metrics.record_error()
                warn(
                    "load_test_produce_error",
                    extra={"worker_id": worker_id, "event_id": event.event_id},
                )

            elapsed = monotonic() - t0
            sleep_time = interval - elapsed

            t_requested_wait_ms = 0.0
            t_actual_wait_ms = 0.0
            t_overshoot_ms = 0.0

            if sleep_time > 0:
                t_requested_wait_ms = sleep_time * 1000
                wait_start = monotonic()
                stop_event.wait(timeout=sleep_time)
                t_actual_wait_ms = (monotonic() - wait_start) * 1000
                t_overshoot_ms = t_actual_wait_ms - t_requested_wait_ms

            if diagnostic:
                t_total_ms = (monotonic() - iteration_start) * 1000
                metrics.record_iteration_timing(
                    worker_id=worker_id,
                    t_gen_ms=t_gen_ms,
                    t_produce_ms=t_produce_ms,
                    t_requested_wait_ms=t_requested_wait_ms,
                    t_actual_wait_ms=t_actual_wait_ms,
                    t_overshoot_ms=t_overshoot_ms,
                    t_total_ms=t_total_ms,
                )

            iteration_start = monotonic()

    def _start_resource_monitor(self, stop_event: threading.Event) -> threading.Thread:
        """Start a background thread that snapshots resource usage."""

        def _monitor() -> None:
            while not stop_event.is_set():
                self._metrics.record_resource_snapshot()
                stop_event.wait(timeout=1.0)

        t = threading.Thread(
            target=_monitor,
            daemon=True,
            name="load-test-resource-monitor",
        )
        t.start()
        return t

    def _start_lag_monitor(self, stop_event: threading.Event) -> threading.Thread | None:
        """Start a background thread that polls consumer lag, or None if disabled."""
        if self._lag_query_fn is None:
            return None

        query_fn = self._lag_query_fn
        collector = self._lag_collector
        poll_interval = self._settings.lag_poll_interval_sec
        start_time = time.monotonic()

        def _monitor() -> None:
            while not stop_event.is_set():
                elapsed = time.monotonic() - start_time
                try:
                    samples = query_fn(elapsed)
                    collector.record(samples)
                except Exception:
                    logger.debug("lag_monitor_query_failed", exc_info=True)
                stop_event.wait(timeout=poll_interval)

        t = threading.Thread(
            target=_monitor,
            daemon=True,
            name="load-test-lag-monitor",
        )
        t.start()
        return t

    def _start_pg_latency_monitor(self, stop_event: threading.Event) -> threading.Thread | None:
        """Start a background thread that polls PostgreSQL for event arrivals."""
        if self._pg_query_fn is None or self._latency_collector is None:
            return None

        query_fn = self._pg_query_fn
        collector = self._latency_collector
        poll_interval = self._settings.pg_latency_poll_interval_sec

        def _monitor() -> None:
            while not stop_event.is_set():
                try:
                    pending = collector.get_pending_event_ids()
                    if pending:
                        found = query_fn(pending)
                        if found:
                            collector.record_pg_arrivals(found, datetime.now(timezone.utc))
                except Exception:
                    logger.debug("pg_latency_probe_failed", exc_info=True)
                stop_event.wait(timeout=poll_interval)

            final_pending = collector.get_pending_event_ids()
            if final_pending:
                try:
                    found = query_fn(final_pending)
                    if found:
                        collector.record_pg_arrivals(found, datetime.now(timezone.utc))
                except Exception:
                    logger.debug("pg_latency_final_probe_failed", exc_info=True)

        t = threading.Thread(
            target=_monitor,
            daemon=True,
            name="load-test-pg-latency-monitor",
        )
        t.start()
        return t

    def _wait_for_completion(
        self,
        stop_event: threading.Event,
        workers: list[threading.Thread],
    ) -> None:
        """Wait until duration expires or total_events is reached."""
        deadline = time.monotonic() + self._settings.duration_sec
        total_events_limit = self._settings.total_events
        metrics = self._metrics
        while not stop_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                stop_event.set()
                return
            if total_events_limit > 0 and metrics.produced_count >= total_events_limit:
                stop_event.set()
                return
            stop_event.wait(timeout=min(0.1, remaining))
