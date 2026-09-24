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
| Kubernetes             | kind cluster `ai-data-platform` (context `kind-ai-data-platform`) |
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
produce-to-ack latency. With a mean latency of ~52.8ms per event and a single
worker thread, the theoretical maximum is approximately `1000ms / 52.8ms ≈ 18.9
events/sec`, which aligns almost exactly with the measured 18.86 events/sec.

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
   each with a per-worker budget of ~50ms. This is marginal given the ~47ms
   produce latency; N=6 or higher would provide more headroom.
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

  



## Follow-up Verification

The original TASK-109 benchmark achieved 18.86 events/sec against the
configured target of 100 events/sec. The initial run identified the
single-worker synchronous producer as a load-generator limitation.

After PERF-FIX-001 introduced concurrent load generation and automatic
effective-worker scaling, additional verification and diagnostic runs
were performed.

### Verification History

| Run | Environment | Effective Workers | Actual Throughput | Result |
|---|---|---:|---:|---|
| Original TASK-109 | Windows / kind / localhost Kafka | 1 | 18.86 events/sec | Target not reached |
| Windows verification | Windows / kind / localhost Kafka | 3 | ~79 events/sec | Target not reached |
| Linux in-cluster verification | Kubernetes / Linux / `kafka:29092` | 3 | **95.55 events/sec** | Target not fully reached |

The Windows diagnostic runs were useful for identifying limitations in
the load-generation environment, but they should not be interpreted as
measurements of the maximum processing capacity of the platform.

### Linux / Kubernetes In-Cluster Verification

The final follow-up run used the real load-test harness inside the
Kubernetes cluster:

- `LoadTestRunner`
- `KafkaEventProducer`
- `EventGenerator`
- diagnostic `MetricsCollector`
- Kafka service `kafka:29092`

Configuration:

| Parameter | Value |
|---|---:|
| Target rate | 100 events/sec |
| Duration | 60 seconds |
| Configured workers | 1 |
| Effective workers | 3 |
| Kafka topic | `products.raw.v1` |
| Execution environment | Linux / Kubernetes |
| Kafka connection | In-cluster `kafka:29092` |

### Linux Verification Results

| Metric | Value |
|---|---:|
| **Target throughput** | **100 events/sec** |
| **Actual throughput** | **95.55 events/sec** |
| **Events produced** | **5,734** |
| **Producer errors** | **0** |
| Duration | 60.008 sec |
| Mean produce latency | 5.142 ms |
| Produce latency p50 | 2.767 ms |
| Produce latency p90 | 7.195 ms |
| Produce latency p95 | 14.384 ms |
| Produce latency p99 | 47.626 ms |
| Mean iteration cycle | 31.360 ms |
| Mean pacing wait overshoot | 0.404 ms |
| Peak RSS | 59.8 MB |
| Total CPU time | 8.85 sec |

Worker activity was evenly distributed:

| Worker | Iterations |
|---|---:|
| `worker_0` | 1,910 |
| `worker_1` | 1,912 |
| `worker_2` | 1,912 |

### Remaining Throughput Gap

With three effective workers and a target rate of 100 events/sec, the
intended per-worker cycle interval is:

```text
3 / 100 = 0.03 sec = 30 ms
```

The measured mean iteration cycle was 31.360 ms.

Using the measured cycle time:

```text
3 × 1000 / 31.360 ≈ 95.66 events/sec
```

This closely matches the observed throughput of 95.55 events/sec.

The remaining approximately 4.45% gap therefore corresponds closely to
the measured difference between the intended 30 ms worker interval and
the observed 31.36 ms mean iteration cycle.

No additional worker or pacing optimization was introduced as part of
TASK-109.

### Diagnostic Findings

The diagnostic investigation also showed that benchmark results were
sensitive to the execution environment.

Earlier Windows/localhost runs showed substantially higher producer
latency and pacing overhead than the Linux in-cluster verification.

A separate controlled in-cluster producer experiment measured much
lower synchronous producer operation latency than the corresponding
Windows/localhost experiment.

Because those experiments differed in multiple environmental variables,
the difference must not be attributed to a single cause such as
port-forward latency or Windows timer behavior without further isolated
testing.

For this reason, no Windows-specific performance optimization was
introduced.

### Downstream Observations

The Linux verification directly proves producer-side load generation
only.

During the pre-flight and post-test inspection:

- Kafka was running and the `products.raw.v1` topic existed.
- Processor and lake-writer were running.
- Raw-writer had a history of restarts and consumer connectivity issues.
- Warehouse-loader also had a history of restarts.

No consumer-lag measurement or complete produced-to-consumed event
reconciliation was performed.

Therefore this benchmark does **not** establish that all 5,734 produced
events were processed by every downstream component during the
60-second test.

### Final TASK-109 Conclusion

TASK-109 configured a target of 100 events/sec.

The original benchmark generated 18.86 events/sec. After improving the
load-test harness and repeating the experiment in a Linux/Kubernetes
in-cluster environment, the real harness generated:

**95.55 events/sec for 60 seconds with 0 producer errors.**

The configured 100 events/sec target was therefore **not fully reached**;
the measured producer-side result was approximately 95.6% of the target.

The experiment demonstrates that the load generator can produce close
to 100 events/sec in the Linux/Kubernetes environment, but it does not
establish end-to-end pipeline sustainability at 100 events/sec.

Consumer lag, downstream processing throughput, and end-to-end latency
remain separate measurements for subsequent performance tasks.

### Follow-up Result Artifacts

Relevant diagnostic and verification artifacts:

- `results/100eps-verification.json`
- `results/100eps-diagnostic.json`
- `results/diagnostic-dryrun.json`
- `results/diagnostic-report.json`
- `results/100eps-diagnostic-single-worker.json`
- `results/100eps-diagnostic-single-worker-after-kafka-restart.json`
- `results/100eps-linux-incluster-verification.json`