# Processor metrics

TASK-018 exposes `ProcessorMetrics` as instance-local, bounded, thread-safe
counters and a latency summary. The design follows the TASK-011 `KafkaMetrics`
conventions: no `prometheus_client` dependency, no exporter in the data path,
and snapshots are detached copies.

## Counters

| Counter | Increment boundary |
| --- | --- |
| `processor_events_processed_total` | Each batch that completes the processing chain without exception. Counts all records in the batch, including valid, invalid, and duplicate. |
| `processor_events_valid_total` | Each record published to `products.validated.v1`. |
| `processor_events_invalid_total` | Each record published to `products.invalid.v1`, including validation failures and deduplication conflicts. |
| `processor_events_duplicate_total` | Each exact duplicate skipped within or across batches. |
| `processor_events_failed_total` | Each record in a batch where the processing chain raised an exception. The batch is not counted in `processed`. |
| `processor_batches_total` | Each non-empty batch entering the pipeline. |
| `processor_batch_records_total` | Cumulative record count across all non-empty batches. |

## Latency summary

| Metric | Description |
| --- | --- |
| `processor_processing_seconds_count` | Number of batch latency observations. |
| `processor_processing_seconds_sum` | Cumulative batch processing duration in seconds. |
| `processor_processing_seconds_min` | Minimum observed batch processing duration. |
| `processor_processing_seconds_max` | Maximum observed batch processing duration. |

Latency is measured with `time.monotonic()` around the processing chain
(`events_to_polars` → `normalize` → `validate` → `deduplicate` → publish).
It does not include time spent waiting for Kafka messages.

## Cardinality

All metric names are fixed. No labels are used. The snapshot contains only
the keys listed above. No event ID, product ID, URL, source name, or raw
error message appears in any metric value.

## Failure isolation

Metrics operations catch and suppress all exceptions internally. A metrics
failure cannot alter processor pipeline semantics. The pipeline works
identically with or without a `ProcessorMetrics` instance.

## Later Prometheus integration

A collector can read `metrics.snapshot()` without executing exporter
callbacks in the processing path. Map existing `_total` names to cumulative
counter samples. Keep instance identity distinct to avoid merging independent
counter resets. The latency summary fields map to a Prometheus Summary.

## Verification

```powershell
python -m pytest tests/test_processor_metrics.py -v
```
