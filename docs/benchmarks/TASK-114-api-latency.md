# TASK-114 — API Latency Runtime Benchmark

## Benchmark Environment

- Date: 2026-09-25
- Environment: Kubernetes / kind
- Platform: Linux 6.6.87.2 (WSL2)
- Python: 3.12.14
- Kafka: `kafka:29092`
- API: `http://api:8000`
- Duration: 60 seconds
- Target producer rate: 100 events/sec
- API probe interval: 5 seconds
- API endpoints: 4

## Pipeline Load Result

| Metric | Result |
|---|---:|
| Target rate | 100 events/sec |
| Actual throughput | 94.50 events/sec |
| Produced events | 5,671 |
| Producer errors | 0 |
| Duration | 60.01 sec |
| Peak RSS | 63.1 MB |
| CPU time | 9.1 sec |

## API Latency Results

| Endpoint | Samples | p50 | p95 | p99 | Max | HTTP |
|---|---:|---:|---:|---:|---:|---|
| `/api/v1/health` | 11 | 8.081 ms | 42.399 ms | 68.299 ms | 74.774 ms | 11 × 200 |
| `/api/v1/quality/summary` | 11 | 14.241 ms | 221.817 ms | 384.875 ms | 425.640 ms | 11 × 200 |
| `/api/v1/products` | 11 | 49.850 ms | 846.760 ms | 1462.073 ms | 1615.901 ms | 11 × 200 |
| `/api/v1/analytics/price-changes` | 11 | 290.856 ms | 1232.959 ms | 1951.586 ms | 2131.243 ms | 11 × 200 |

## Overall API Latency

| Metric | Result |
|---|---:|
| Total samples | 44 |
| Mean | 178.517 ms |
| p50 | 44.314 ms |
| p95 | 411.995 ms |
| p99 | 1909.646 ms |
| Max | 2131.243 ms |

All 44 API probe requests returned HTTP 200.

## Observations

Among the four measured endpoints,
`/api/v1/analytics/price-changes` had the highest measured latency under
the tested pipeline load.

Its median latency was 290.856 ms, while p95 reached 1232.959 ms and
p99 reached 1951.586 ms.

`/api/v1/products` had a substantially lower median latency of
49.850 ms but showed significant tail latency, with p95 of
846.760 ms and p99 of 1462.073 ms.

The health endpoint remained comparatively fast, with a median latency
of 8.081 ms.

No API errors were observed during the benchmark.

## Interpretation Limitations

The API probe measures client-side HTTP round-trip latency. It does not
isolate server-side processing time, PostgreSQL query execution time,
or network latency.

Only 11 samples were collected per endpoint during this 60-second run.
Therefore p95 and p99 values should be treated as indicative runtime
evidence rather than high-confidence production SLO measurements.

The benchmark does not establish the root cause of the observed tail
latency. Additional database/query profiling would be required before
attributing the latency to PostgreSQL or specific SQL queries.

## Run Identification

- Run ID: `3d21103f-c74f-4c77-810d-72af0756f19b`
- Timestamp: `2026-09-25T15:26:51.882745+00:00`