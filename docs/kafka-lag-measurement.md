# Kafka Consumer Lag Measurement (TASK-112)

Systematic consumer-lag monitoring integrated into the load-test harness.
Lag is measured per partition and consumer group, with growth-pattern
detection and operational threshold reporting.

## Overview

Consumer lag is the difference between the log-end offset (high watermark)
and the last committed offset for a consumer group partition.  Growing lag
indicates that consumers cannot keep up with producer throughput.

The load-test harness now collects lag samples periodically during a run
and includes a `consumer_lag` section in the JSON report.

## Architecture

```
LoadTestRunner
    │
    ├── LagQueryFn (injected callable)
    │       │
    │       └── kafka_lag_probe.create_lag_query_fn()
    │               ├── AdminClient  → committed offsets per group
    │               └── Consumer     → high-watermark offsets
    │
    └── LagCollector (thread-safe)
            ├── record(samples)      ← called by background monitor thread
            ├── get_summary()        → LagSummary with per-partition stats
            └── to_report_dict()     → JSON-serializable report section
```

### Components

| Module | Responsibility |
|---|---|
| `libs/load_test/lag_collector.py` | Core collection, analysis, and growth classification |
| `libs/load_test/kafka_lag_probe.py` | Kafka-specific lag query using AdminClient + Consumer |
| `libs/load_test/config.py` | Configuration fields for lag monitoring |
| `libs/load_test/runner.py` | Background monitor thread integration |

### Design Decisions

1. **Dependency injection**: `LagCollector` accepts `LagSample` objects via
   `record()`.  The Kafka query mechanism (`kafka_lag_probe`) is a separate
   module.  This allows unit testing without a Kafka broker.

2. **No consumer-group membership**: The probe uses `AdminClient` for
   committed offsets and `Consumer.assign()` (not `subscribe()`) for
   watermark queries.  This avoids triggering consumer-group rebalances
   and does not interfere with real consumers.

3. **Background thread**: Lag polling runs in a daemon thread started by
   `LoadTestRunner.run()`.  The thread polls at `lag_poll_interval_sec`
   (default 5 seconds) and stops when the test completes.

## Configuration

| Setting | Env Variable | Default | Description |
|---|---|---|---|
| `lag_consumer_groups` | `APP_LAG_CONSUMER_GROUPS` | `[]` (disabled) | Consumer group IDs to monitor |
| `lag_topics` | `APP_LAG_TOPICS` | `["products.raw.v1"]` | Topics to include in lag queries |
| `lag_poll_interval_sec` | `APP_LAG_POLL_INTERVAL_SEC` | `5.0` | Seconds between lag queries |
| `lag_partition_count` | `APP_LAG_PARTITION_COUNT` | `3` | Partitions per monitored topic |

### CLI Usage

```bash
python scripts/run_load_test.py \
  --rate 100 --duration 60 \
  --monitor-group processor \
  --monitor-group raw-writer \
  --lag-interval 5.0 \
  --lag-partitions 3
```

`--monitor-group` can be specified multiple times to monitor several
consumer groups.  Lag monitoring is automatically disabled in `--dry-run`
mode.

## Operational Thresholds

| Threshold | Value | Meaning |
|---|---:|---|
| **WARNING** | 1,000 messages | Consumer is falling behind; investigate processing rate |
| **CRITICAL** | 10,000 messages | Consumer cannot keep up; risk of data retention expiry |

These thresholds are included in the JSON report under
`consumer_lag.thresholds` and should be interpreted in the context of
the test duration and produce rate.

## Growth Pattern Classification

The collector classifies lag trends per partition using quarter-average
comparison:

| Pattern | Condition | Interpretation |
|---|---|---|
| `stable` | Max-min spread ≤ 20% of max, or quarter averages within 50% | Consumer keeping pace |
| `increasing` | Last-quarter average > 150% of first-quarter average | Consumer falling behind |
| `decreasing` | Last-quarter average < 70% of first-quarter average | Consumer catching up |
| `insufficient_data` | Fewer than 4 samples | Not enough data to classify |

The `any_growing_lag` flag in the report is `true` if any partition
shows an `increasing` pattern.

## Report Format

The `consumer_lag` section in the JSON report:

```json
{
  "consumer_lag": {
    "total_samples": 72,
    "max_observed_lag": 450,
    "any_growing_lag": false,
    "per_partition": [
      {
        "consumer_group": "processor",
        "topic": "products.raw.v1",
        "partition": 0,
        "samples": 12,
        "min": 0,
        "max": 150,
        "mean": 45.2,
        "final": 10,
        "growth": "stable"
      }
    ],
    "thresholds": {
      "warning": 1000,
      "critical": 10000
    }
  }
}
```

## Limitations

- **Polling interval**: Lag is sampled at discrete intervals (default 5s).
  Short-lived lag spikes between polls are not captured.
- **No end-to-end latency**: Lag measurement does not track individual
  message latency from produce to consume.  It measures queue depth only.
- **Committed offset staleness**: Consumer groups that commit offsets
  infrequently will show artificially high lag.  The measurement reflects
  committed offsets, not processed offsets.
- **Probe overhead**: The AdminClient query adds a small amount of load
  to the Kafka broker.  At the default 5-second interval this is
  negligible compared to produce/consume traffic.
