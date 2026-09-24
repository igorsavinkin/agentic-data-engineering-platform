# Load Test Harness (TASK-108)

Reusable load-test harness that produces canonical product-observation events
at configurable rates and measures producer-side latency, ingestion throughput,
and resource utilization.

## Overview

The harness is source-adapter independent: it generates synthetic events
conforming to the canonical `ProductObservationEvent` contract and publishes
them to `products.raw.v1`.  This isolates load-test behavior from any
specific adapter implementation.

## Quick Start

```bash
# Dry run (no Kafka needed) — measures generator throughput
python scripts/run_load_test.py --dry-run --rate 100 --duration 10

# Real run against local Kafka
python scripts/run_load_test.py --rate 100 --duration 30

# Fixed event count
python scripts/run_load_test.py --rate 500 --total-events 5000

# Multi-threaded production
python scripts/run_load_test.py --rate 1000 --duration 60 --workers 4
```

## CLI Reference

| Flag             | Description                                         | Default            |
|------------------|-----------------------------------------------------|--------------------|
| `--rate`         | Target events per second                            | 100                |
| `--duration`     | Test duration in seconds                            | 30                 |
| `--total-events` | Stop after this many events (overrides duration)    | 0 (unlimited)      |
| `--workers`      | Parallel producer threads                           | 1                  |
| `--output`       | Path for JSON result report                         | `load_test_results.json` |
| `--source`       | Source label in generated events                    | `load-test`        |
| `--seed`         | Random seed for deterministic generation            | 42                 |
| `--dry-run`      | Skip Kafka; measure generator throughput only       | false              |
| `--verbose`      | Enable debug logging                                | false              |

All defaults can also be set via `APP_`-prefixed environment variables
(e.g. `APP_TARGET_EVENTS_PER_SEC=200`).

## Output Format

The harness writes a structured JSON report to the configured output path:

```json
{
  "configuration": {
    "target_events_per_sec": 100.0,
    "duration_sec": 30.0,
    "total_events": 0,
    "worker_count": 1,
    "source_name": "load-test",
    "seed": 42
  },
  "environment": {
    "platform": "Linux-6.x...",
    "python_version": "3.12.x"
  },
  "results": {
    "duration_sec": 30.123,
    "error_count": 0,
    "latency_ms": {
      "max": 45.2,
      "mean": 3.1,
      "min": 0.8,
      "p50": 2.5,
      "p90": 5.1,
      "p95": 8.3,
      "p99": 22.1
    },
    "produced_count": 3012,
    "resource": {
      "peak_rss_mb": 85.3,
      "total_cpu_sec": 12.456
    },
    "throughput_events_per_sec": 99.98
  },
  "run_id": "uuid",
  "timestamp": "2026-09-22T..."
}
```

## Interpreting Results

- **throughput_events_per_sec**: Actual sustained production rate.  Compare
  with the target rate to identify bottlenecks.
- **latency_ms.p50/p90/p95/p99**: Produce-to-ack latency distribution.
  High p99 values indicate tail latency issues (broker pressure, GC pauses).
  **Scope note:** this measures producer-side latency only (from submit to
  broker ack).  End-to-end pipeline latency — including consumer processing,
  deduplication, and silver writes — is not measured by this harness and is
  out of scope for the current milestone.
- **error_count**: Number of failed produce attempts.  Non-zero values
  indicate infrastructure issues.
- **resource.peak_rss_mb**: Peak resident set size.  Useful for sizing
  container memory limits.
- **resource.total_cpu_sec**: Total CPU time consumed.  Divide by
  duration_sec to get average CPU utilization.

> **Platform note:** Resource metrics (`peak_rss_mb`, `total_cpu_sec`) are
> Linux-only — they read from `/proc/<pid>/status`.  On other platforms
> (macOS, Windows) these values report `0.0`.

## Reuse Across Load Levels

The harness is designed for repeated use at different scales:

```bash
# Milestone 13 reference scenarios (SPECIFICATION.md §23)
python scripts/run_load_test.py --rate 100 --duration 60 --output results/100eps.json
python scripts/run_load_test.py --rate 500 --duration 60 --output results/500eps.json
python scripts/run_load_test.py --rate 1000 --duration 60 --output results/1000eps.json
```

## Prerequisites

- Docker Compose stack running (Kafka at `localhost:9092`)
- Python 3.12+
- `APP_ENVIRONMENT` set (e.g. `APP_ENVIRONMENT=production`); required by the
  platform configuration layer
- No changes to production-like infrastructure; the harness only produces
  events to the raw topic

## Architecture

```
scripts/run_load_test.py          CLI entry point
         │
         ▼
libs/load_test/runner.py          Orchestrator (rate control, workers)
         │
    ┌────┼────┐
    ▼    ▼    ▼
  worker worker worker           Parallel producer threads
    │    │    │
    ▼    ▼    ▼
libs/load_test/event_generator.py  Synthetic event creation
    │
    ▼
  produce_fn (injected)           Kafka producer or dry-run no-op
    │
    ▼
libs/load_test/metrics_collector.py  Latency + throughput + resource tracking
    │
    ▼
libs/load_test/report.py          Structured JSON output
```
