# Benchmark: 100 Events/sec Load Test (TASK-109)

Benchmark of the event pipeline at a target rate of 100 events/second using
the TASK-108 load-test harness.

## Test Configuration

| Parameter              | Value                          |
|------------------------|--------------------------------|
| Target rate            | 100 events/sec                 |
| Duration               | 60 seconds                     |
| Workers                | 1                              |
| Kafka bootstrap        | `localhost:9092`               |
| Kafka topic            | `products.raw.v1`              |
| Topic partitions       | 3                              |
| Topic replication      | 1                              |
| Kafka client ID        | `load-test-harness`            |
| Event source           | `load-test`                    |
| Random seed            | 42                             |
| Total events limit     | 0 (unlimited, duration-bound)  |

## Environment

| Component              | Value                          |
|------------------------|--------------------------------|
| Platform               | Windows 11 (10.0.26200)        |
| Python                 | 3.14.0                         |
| Kubernetes             | kind cluster `kind-ai-data-platform` |
| Namespace              | `ai-data-platform`             |
| Kafka                  | Single broker, KRaft mode, 512MB heap |
| Kafka advertised       | `PLAINTEXT_HOST://localhost:9092` |

### Pod Status (Pre-Benchmark)

All workloads healthy:

```
api-ffc4d7bb5-zh45f                 1/1  Running
ingestion-56d454ff6f-ql2vp          1/1  Running
kafka-798c456747-wvlmz              1/1  Running
lake-writer-6d8bc8c984-bcbmz        1/1  Running
minio-0                             1/1  Running
postgresql-0                        1/1  Running
processor-7cd699cd54-4zrxg          1/1  Running
raw-writer-7c67f889c8-sz6rz         1/1  Running
warehouse-loader-6f7cfdd45b-hp5c9   1/1  Running
```

## Measured Results

| Metric                         | Value          |
|--------------------------------|----------------|
| **Target event rate**          | 100.0 events/sec |
| **Actual throughput**          | **18.86 events/sec** |
| **Events produced**            | 1,132          |
| **Events failed/errored**      | 0              |
| **Test duration**              | 60.014 sec     |
| **Latency min**                | 2.742 ms       |
| **Latency max**                | 7,234.084 ms   |
| **Latency mean**               | 52.802 ms      |
| **Latency p50**                | 46.611 ms      |
| **Latency p90**                | 50.594 ms      |
| **Latency p95**                | 51.596 ms      |
| **Latency p99**                | 53.801 ms      |
| **Peak RSS**                   | N/A (Windows)  |
| **Total CPU time**             | 1.969 sec      |

### Result: TARGET NOT SUSTAINED

The pipeline achieved **18.86 events/sec** against a target of **100 events/sec**.
Zero errors occurred; all 1,132 produced events were successfully acknowledged
by the Kafka broker.

## Analysis

### Throughput Gap

The achieved throughput of ~19 events/sec is bounded by the synchronous
produce-to-ack latency. With a p50 latency of ~47ms per event and a single
worker thread, the theoretical maximum is approximately `1000ms / 47ms ≈ 21
events/sec`, which aligns with the measured 18.86 events/sec.

### Latency Profile

- **Steady-state produce latency**: ~45-54ms (p50 through p99). The tight
  p50-p99 range (47-54ms) indicates consistent broker response times.
- **Max latency (7,234ms)**: Caused by initial IPv6 connection attempt failure
  (`Connect to ipv6#[::1]:9092 failed`). The librdkafka client retried and
  fell back to IPv4. This is a one-time startup cost, not representative of
  steady-state behavior.
- **Min latency (2.7ms)**: Represents the fastest broker ack under light load.

### Root Cause

The bottleneck is the **synchronous produce-wait loop** in the single-worker
configuration. Each event is produced and the harness waits for the broker
acknowledgement before dispatching the next event. At ~50ms per ack, a single
worker cannot exceed ~20 events/sec regardless of the target rate.

This is a **harness configuration limitation**, not a pipeline processing
bottleneck. The Kafka broker, processor, and downstream services are not
saturated at this throughput.

### Potential Mitigations (for later tasks)

1. **Multiple workers**: The harness supports `--workers N`. With N=5 workers,
   the global rate controller would distribute 100 events/sec across 5 threads,
   each requiring only ~100ms per event cycle.
2. **Async produce**: Switching from synchronous produce-wait to batch/async
   production would allow higher throughput per worker.
3. These are configuration changes, not pipeline code changes.

## Post-Benchmark Health

All pods remained healthy throughout and after the benchmark. No restarts,
OOMKills, or CrashLoopBackOff events were observed.

## Reproduction Command

```bash
APP_ENVIRONMENT=production \
  python scripts/run_load_test.py \
    --rate 100 \
    --duration 60 \
    --output results/100eps.json \
    --verbose
```

Requires:
- kind cluster `kind-ai-data-platform` running
- All platform pods healthy in namespace `ai-data-platform`
- Kafka accessible at `localhost:9092`

## Raw Results

The full JSON report is at `results/100eps.json`.

## Limitations

- **Producer-side only**: The harness measures produce-to-ack latency.
  End-to-end pipeline latency (consumer processing, validation, Parquet writes,
  PostgreSQL loading) is not measured. See TASK-112, TASK-113, TASK-114.
- **Resource metrics unavailable**: `peak_rss_mb` reports 0.0 on Windows.
  Linux `/proc/<pid>/status` is required for resource measurement.
- **Single worker**: The test used 1 worker thread. Multi-worker tests at the
  same target rate may yield different results.
- **kind cluster**: Performance characteristics differ from production
  Kubernetes or cloud deployments.
- **No downstream backpressure measurement**: The benchmark measures only the
  producer side. Consumer lag, processing queue depth, and write amplification
  are not captured.
