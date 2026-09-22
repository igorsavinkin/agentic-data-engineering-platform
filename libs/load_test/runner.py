"""Load-test runner: orchestrates event production and measurement (TASK-108).

The runner coordinates the event generator, a produce function (injected for
testability), and the metrics collector.  It supports both time-bounded and
count-bounded runs, with configurable target rates.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Callable

from libs.event_contracts import ProductObservationEvent
from libs.load_test.config import LoadTestSettings
from libs.load_test.event_generator import EventGenerator
from libs.load_test.metrics_collector import MetricsCollector
from libs.load_test.report import build_report, write_report

logger = logging.getLogger(__name__)

ProduceFn = Callable[[ProductObservationEvent], str]


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
    ) -> None:
        self._settings = settings
        self._produce_fn = produce_fn
        self._metrics = MetricsCollector()
        self._run_id = str(uuid.uuid4())

    @property
    def metrics(self) -> MetricsCollector:
        return self._metrics

    @property
    def run_id(self) -> str:
        return self._run_id

    def run(self) -> dict:
        """Execute the load test and return the structured report.

        The run respects both ``duration_sec`` and ``total_events`` limits;
        whichever is reached first stops the test.  If ``total_events`` is 0,
        only the time limit applies.
        """
        logger.info(
            "load_test_start",
            extra={
                "run_id": self._run_id,
                "target_events_per_sec": self._settings.target_events_per_sec,
                "duration_sec": self._settings.duration_sec,
                "total_events": self._settings.total_events,
                "worker_count": self._settings.worker_count,
            },
        )

        self._metrics.mark_start()
        stop_event = threading.Event()

        workers = self._start_workers(stop_event)
        resource_monitor = self._start_resource_monitor(stop_event)

        self._wait_for_completion(stop_event, workers)

        stop_event.set()
        self._metrics.mark_end()

        for w in workers:
            w.join(timeout=5)
        resource_monitor.join(timeout=5)

        summary = self._metrics.get_summary()
        report = build_report(
            settings_dict=self._settings.model_dump(),
            metrics_summary=summary,
            run_id=self._run_id,
        )

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

    def _start_workers(self, stop_event: threading.Event) -> list[threading.Thread]:
        """Start producer worker threads, each with its own event generator."""
        workers: list[threading.Thread] = []
        for i in range(self._settings.worker_count):
            generator = EventGenerator(
                source=self._settings.source_name,
                seed=self._settings.seed + i,
            )
            t = threading.Thread(
                target=self._worker_loop,
                args=(stop_event, i, generator),
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
    ) -> None:
        """Single worker loop: produce events at the target rate."""
        worker_count = self._settings.worker_count
        interval = worker_count / self._settings.target_events_per_sec
        while not stop_event.is_set():
            if self._settings.total_events > 0:
                if self._metrics.produced_count >= self._settings.total_events:
                    return

            event = generator.next_event()
            start = time.monotonic()
            try:
                self._produce_fn(event)
                latency_ms = (time.monotonic() - start) * 1000
                self._metrics.record_latency(event.event_id, latency_ms)
            except Exception:
                self._metrics.record_error()
                logger.warning(
                    "load_test_produce_error",
                    extra={"worker_id": worker_id, "event_id": event.event_id},
                )

            sleep_time = interval - (time.monotonic() - start)
            if sleep_time > 0:
                stop_event.wait(timeout=sleep_time)

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

    def _wait_for_completion(
        self,
        stop_event: threading.Event,
        workers: list[threading.Thread],
    ) -> None:
        """Wait until duration expires or total_events is reached."""
        deadline = time.monotonic() + self._settings.duration_sec
        while not stop_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                stop_event.set()
                return
            if (
                self._settings.total_events > 0
                and self._metrics.produced_count >= self._settings.total_events
            ):
                stop_event.set()
                return
            stop_event.wait(timeout=min(0.1, remaining))
