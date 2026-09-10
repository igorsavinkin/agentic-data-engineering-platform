"""Instance-local, bounded Kafka counters for a future Prometheus collector."""

from enum import StrEnum
from threading import Lock


class KafkaMetric(StrEnum):
    PRODUCED = "ingestion_events_total"
    PRODUCER_ERRORS = "ingestion_errors_total"
    CONSUMED = "kafka_events_consumed_total"
    PROCESSED = "kafka_events_processed_total"
    INVALID = "events_invalid_total"
    CONSUMER_ERRORS = "kafka_consumer_errors_total"
    PROCESSING_ERRORS = "kafka_processing_errors_total"
    DEAD_LETTERED = "kafka_dead_letter_events_total"
    LAG_ERRORS = "kafka_lag_errors_total"


class KafkaMetrics:
    """Thread-safe counters with no payload, exception, or configuration labels.

    Snapshots are detached copies. Counters reset on instance restart and count
    attempts/deliveries, not unique event IDs. No exporter runs in the data path.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._counts = dict.fromkeys(KafkaMetric, 0)

    def increment(self, metric: KafkaMetric) -> None:
        with self._lock:
            self._counts[metric] += 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {metric.value: count for metric, count in self._counts.items()}
