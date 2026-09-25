# Processing Latency Measurement (TASK-113)

## Overview

End-to-end processing latency measures the time from when an event is
produced to Kafka until it becomes queryable in PostgreSQL.  This covers
the full pipeline:

```
Ingestion → Kafka → Processor → Lake Writer → Warehouse Loader → PostgreSQL
```

The measurement uses a probe-based approach: the load test harness records
the wall-clock produce time for each event, then a background thread
periodically queries PostgreSQL for those event IDs.  The latency for each
event is `query_time - produce_time`.

## Architecture

### Components

| Component | File | Role |
|---|---|---|
| `LatencyCollector` | `libs/load_test/latency_collector.py` | Thread-safe collection of produce timestamps and arrival times |
| `PostgreSQLProbe` | `libs/load_test/pg_latency_probe.py` | Factory for PostgreSQL query functions |
| `LoadTestRunner` | `libs/load_test/runner.py` | Orchestrates workers, probe threads, and report generation |
| `LoadTestSettings` | `libs/load_test/config.py` | Configuration for PG connection and poll interval |

### Data Flow

```
Worker produces event
    │
    ├─→ MetricsCollector.record_latency()     (produce-to-ack, existing)
    │
    └─→ LatencyCollector.record_produce()     (wall-clock UTC)
              │
              ▼
    Background PG probe thread (every 10s default)
              │
              ├─→ get_pending_event_ids()
              ├─→ pg_query_fn(pending_ids) → found_ids
              └─→ LatencyCollector.record_pg_arrivals(found_ids, query_time)
              │
              ▼
    End-to-end latency = query_time - produce_time
```

### Pipeline Stage Breakdown

The total end-to-end latency spans these stages.  The ranges below are
**illustrative estimates**, not measured values — actual latency depends
on network conditions, batch timing, and system load:

| Stage | Expected Latency | Description |
|---|---|---|
| Produce → Kafka ack | 1–50 ms | Network + broker fsync |
| Kafka → Processor | 0–100 ms | Consumer poll interval + processing |
| Processor → validated topic | 1–10 ms | Polars validation + produce |
| Validated → Silver Parquet | 1–100 ms | Lake Writer consume + write |
| Silver → Warehouse batch | 0–300 s | **Dominant factor**: warehouse loader runs on a schedule |
| Warehouse → PostgreSQL | 10–500 ms | Parquet read + batch insert |

The warehouse loader batch interval (default 300 seconds) is the dominant
factor in end-to-end latency.  Events produced just after a batch completes
must wait for the next batch cycle.

## Configuration

### CLI

```bash
python scripts/run_load_test.py \
  --rate 100 --duration 60 \
  --pg-url "postgresql://user:pass@localhost:5432/warehouse" \
  --latency-interval 10.0
```

### Environment Variables

```
APP_PG_DB_URL=postgresql://user:pass@localhost:5432/warehouse
APP_PG_LATENCY_POLL_INTERVAL_SEC=10.0
APP_PG_LATENCY_SOURCE=load-test
```

### Settings

| Setting | Default | Description |
|---|---|---|
| `pg_db_url` | `""` (disabled) | PostgreSQL connection URL |
| `pg_latency_poll_interval_sec` | `10.0` | Seconds between PG arrival checks |
| `pg_latency_source` | `"load-test"` | Source label to filter events |

## Report Format

When PG probing is enabled, the JSON report includes a `processing_latency`
section:

```json
{
  "processing_latency": {
    "total_produced": 6000,
    "total_resolved": 5980,
    "unresolved": 20,
    "sample_count": 5980,
    "latency_ms": {
      "min": 1523.456,
      "p50": 152345.678,
      "p95": 302100.123,
      "p99": 305000.456,
      "max": 310234.789,
      "mean": 160456.789
    }
  }
}
```

### Fields

- `total_produced`: events produced during the load test
- `total_resolved`: events found in PostgreSQL before the test ended
- `unresolved`: events not yet in PostgreSQL (still in pipeline)
- `sample_count`: number of latency measurements
- `latency_ms`: distribution with min, p50, p95, p99, max, mean

## Measurement Imprecision

The probe-based approach introduces measurement imprecision:

1. **Polling interval**: events are detected at the next poll cycle, adding
   up to `poll_interval` milliseconds of overcounting.
2. **Clock skew**: produce time and query time use the same machine clock,
   so there is no cross-machine skew.  However, the wall-clock resolution
   depends on the OS.
3. **Warehouse batch cycle**: the dominant latency component is the warehouse
   loader's batch interval.  Events produced just after a batch will show
   latency close to the full interval; events produced just before a batch
   will show much lower latency.

For precise per-stage breakdown, use OpenTelemetry traces across service
boundaries (see `libs/observability/otel_config.py`).

## Limitations

- Requires PostgreSQL to be running and accessible from the load test machine
- The warehouse loader must have processed the Silver Parquet data before
  events appear in PostgreSQL
- Events from other sources with the same source label may be matched
- The probe adds read load to PostgreSQL proportional to the pending event
  count and poll frequency

## See Also

- `docs/load-test-harness.md` — load test harness usage
- `docs/kafka-lag-measurement.md` — consumer lag measurement (TASK-112)
- `docs/benchmark-100-eps.md` — 100 eps benchmark results
- `libs/observability/otel_config.py` — OpenTelemetry distributed tracing
