# Benchmark: 500 Events/sec Load Test (TASK-110)

Benchmark of the event pipeline at a target rate of 500 events/second using
the TASK-108 load-test harness.

## Test Configuration

| Parameter              | Value                          |
|------------------------|--------------------------------|
| Target rate            | 500 events/sec                 |
| Duration               | 60 seconds                     |
| Configured workers     | 1                              |
| Effective workers      | 15 (auto-scaled)               |
| Kafka bootstrap (Run A)| `localhost:9092`               |
| Kafka bootstrap (Run B)| `kafka:29092` (in-cluster)     |
| Kafka topic            | `products.raw.v1`              |
| Topic partitions       | 3                              |
| Topic replication      | 1                              |
| Kafka client ID        | `load-test-harness`            |
| Event source           | `load-test`                    |
| Random seed            | 42                             |
| Total events limit     | 0 (unlimited, duration-bound)  |

The auto-scaler computed effective workers as
`ceil(500 / 50 * 1.5) = 15`, where 50 is the estimated events/sec per
worker and 1.5 is the headroom multiplier.

## Environment

| Component              | Value                          |
|------------------------|--------------------------------|
| Platform (Run A)       | Windows 11 (10.0.26200)        |
| Platform (Run B)       | Linux 6.6.87.2 (in-cluster)    |
| Python (Run A)         | 3.14.0                         |
| Python (Run B)         | 3.12.14                        |
| Kubernetes             | kind cluster `ai-data-platform` (context `kind-ai-data-platform`) |
| Namespace              | `ai-data-platform`             |
| Kafka                  | Single broker, KRaft mode, 512MB heap |

### Pod Status (Pre-Benchmark)

```
api-ffc4d7bb5-zh45f                 1/1  Running   0
ingestion-56d454ff6f-ql2vp          1/1  Running   0
kafka-788b477c9c-27djg              1/1  Running   0
lake-writer-6d8bc8c984-bcbmz        1/1  Running   0
minio-0                             1/1  Running   0
postgresql-0                        1/1  Running   0
processor-7cd699cd54-4zrxg          1/1  Running   0
raw-writer-7c67f889c8-sz6rz         1/1  Running   11 (3h21m ago)
warehouse-loader-6f7cfdd45b-hp5c9   1/1  Running   30 (3m ago)
```

### Pod Status (Post-Benchmark)

All pods remained Running with no new restarts during either benchmark run.

### Downstream Stability Observations

- **raw-writer**: 11 restarts total, last restart 3h21m before benchmark.
  The service was Running and stable during the benchmark window.
- **warehouse-loader**: 30 restarts total, last restart 3m before benchmark.
  The service has a pattern of frequent restarts but was Running during
  the benchmark window.

These observations are recorded as facts. No downstream sustainability claim
is made based on this benchmark. Consumer lag measurement belongs to TASK-112.

## Run A: Windows / localhost

### Configuration

| Parameter         | Value                     |
|-------------------|---------------------------|
| Kafka bootstrap   | `localhost:9092`          |
| Execution context | Windows host, port-forwarded Kafka |

### Results

| Metric                         | Value          |
|--------------------------------|----------------|
| **Configured target rate**     | 500.0 events/sec |
| **Actual throughput**          | **18.73 events/sec** |
| **Events produced**            | 1,125          |
| **Events failed/errored**      | 0              |
| **Effective workers**          | 15             |
| **Test duration**              | 60.051 sec     |
| **Latency min**                | 641.450 ms     |
| **Latency max**                | 8,383.980 ms   |
| **Latency mean**               | 804.493 ms     |
| **Latency p50**                | 706.518 ms     |
| **Latency p90**                | 728.296 ms     |
| **Latency p95**                | 740.698 ms     |
| **Latency p99**                | 7,854.116 ms   |
| **Peak RSS**                   | N/A (Windows)  |
| **Total CPU time**             | 1.641 sec      |

### Run A Analysis

The mean measured producer-call duration of 804ms over the Windows/localhost
connection severely limits throughput. With 15 effective workers each
blocked on ~800ms ack times, the theoretical maximum is approximately
`15 * 1000 / 804 ~ 18.7 events/sec`, which matches the measured 18.73 eps.

This result is an environment limitation, not a pipeline capacity
measurement. The same pattern was observed in TASK-109 at 100 eps target.

## Run B: Linux / Kubernetes In-Cluster

### Configuration

| Parameter         | Value                              |
|-------------------|------------------------------------|
| Kafka bootstrap   | `kafka:29092` (in-cluster service) |
| Execution context | Ingestion pod, Linux container     |
| Harness components | `LoadTestRunner`, `KafkaEventProducer`, `EventGenerator`, `MetricsCollector` |

### Results

| Metric                         | Value          |
|--------------------------------|----------------|
| **Configured target rate**     | 500.0 events/sec |
| **Actual throughput**          | **305.88 events/sec** |
| **Events produced**            | 18,382         |
| **Events failed/errored**      | 0              |
| **Effective workers**          | 15             |
| **Test duration**              | 60.095 sec     |
| **Latency min**                | 1.061 ms       |
| **Latency max**                | 557.504 ms     |
| **Latency mean**               | 48.383 ms      |
| **Latency p50**                | 45.138 ms      |
| **Latency p90**                | 59.997 ms      |
| **Latency p95**                | 72.537 ms      |
| **Latency p99**                | 141.851 ms     |
| **Peak RSS**                   | 62.5 MB        |
| **Total CPU time**             | 27.56 sec      |

### Run B Analysis

The per-worker pacing interval is:

```text
effective_workers / target_rate = 15 / 500 = 0.030 sec = 30 ms
```

The measured mean producer-call duration is 48.383 ms, which exceeds
the 30 ms per-worker budget. Each worker spends more time waiting for
the broker ack than the pacing interval allows, so every worker is
fully occupied.

An approximate throughput implied by the observed mean producer-call
duration is:

```text
15 * 1000 / 48.383 = 310.0 events/sec
```

This closely matches the measured throughput of 305.88 events/sec.

The configured 500 events/sec target was **not reached**. The measured
producer-side result was approximately 61.2% of the target.

### Latency Profile

- **Producer-call distribution**: p50 45ms, p90 60ms, p95 73ms.
  Most measured producer-call durations were concentrated within this range.
- **p99 (142ms) and max (558ms)**: Tail-latency spikes were observed.
  Their cause was not isolated in TASK-110.
- **Min (1.06ms)**: Fastest ack under light load.

### Resource Utilization

- **Peak RSS**: 62.5 MB — modest memory footprint for 15 concurrent
  producer threads.
- **Total CPU time**: 27.56 sec over 60.095 sec duration.
  Average CPU utilization: `27.56 / 60.095 = 0.46 CPU cores`.

## Throughput Summary

| Run | Environment         | Effective Workers | Actual Throughput | % of Target |
|-----|---------------------|-------------------:|------------------:|------------:|
| A   | Windows / localhost | 15                | 18.73 events/sec  | 3.7%        |
| B   | Linux / in-cluster  | 15                | 305.88 events/sec | 61.2%       |

## Result

The configured target of 500 events/sec was **not sustained** in either
environment.

Run B (Linux in-cluster) achieved **305.88 events/sec for 60 seconds
with 0 producer errors**, using 15 effective worker threads.

The measured throughput gap is consistent with producer-call duration
exceeding the 30 ms per-worker pacing interval. The observed mean
producer-call duration and aggregate throughput closely agree with this
explanation.

This identifies a load-generator-side constraint in this benchmark run;
it does not establish the maximum capacity of Kafka or of the downstream
pipeline.

## Scope and Deferrals

This benchmark measures **producer-side** load generation only.

The following measurements are explicitly out of scope for TASK-110
and belong to subsequent performance tasks:

| Measurement              | Task   |
|--------------------------|--------|
| Kafka consumer lag       | TASK-112 |
| End-to-end processing latency | TASK-113 |
| API latency              | TASK-114 |
| Bottleneck conclusions and remediation | TASK-115 |

No claim is made that the complete downstream pipeline sustained
500 events/sec. Consumer lag may grow if downstream consumption
throughput is lower than the generated rate; this is measured in
TASK-112.

## Reproduction Commands

### Run A (Windows / localhost)

```bash
APP_ENVIRONMENT=production \
  python scripts/run_load_test.py \
    --rate 500 \
    --duration 60 \
    --output results/500eps.json \
    --verbose
```

### Run B (Linux / in-cluster)

```bash
kubectl exec -n ai-data-platform ingestion-<pod> -- sh -c '
  cd /app && APP_ENVIRONMENT=production python -c "
import sys, json
sys.path.insert(0, \"/app\")
from libs.load_test import LoadTestRunner, LoadTestSettings
from libs.common.kafka_producer import KafkaEventProducer, KafkaProducerSettings

settings = LoadTestSettings(
    target_events_per_sec=500.0,
    duration_sec=60.0,
    worker_count=1,
    kafka_bootstrap_servers=\"kafka:29092\",
    kafka_raw_topic=\"products.raw.v1\",
    kafka_client_id=\"load-test-harness\",
    source_name=\"load-test\",
    seed=42,
    total_events=0,
    output_path=\"/tmp/500eps-incluster.json\",
)

class _KS(KafkaProducerSettings):
    kafka_bootstrap_servers: str = settings.kafka_bootstrap_servers
    kafka_raw_topic: str = settings.kafka_raw_topic
    kafka_client_id: str = settings.kafka_client_id

producer = KafkaEventProducer(_KS())
def produce_fn(event):
    producer.publish(event)
    return event.event_id

runner = LoadTestRunner(settings=settings, produce_fn=produce_fn)
report = runner.run()
producer.close()
print(json.dumps(report, indent=2, sort_keys=True))
"'
```

## Raw Results

- `results/500eps.json` — Run A (Windows / localhost)
- `results/500eps-linux-incluster.json` — Run B (Linux / in-cluster)

## Limitations

- **Producer-call timing**: The reported producer latency measures the
  duration of the harness `produce_fn(event)` call. With concurrent workers,   this may include producer lock contention, serialization, Kafka produce,  flush, and delivery acknowledgement. It must not be interpreted as pure Kafka broker or network latency.
- **No consumer lag measurement**: Consumer lag is not captured by the
  harness. TASK-112 addresses this.
- **No downstream reconciliation**: The benchmark does not establish
  that all 18,382 produced events were processed by every downstream
  component.
- **Downstream instability**: raw-writer and warehouse-loader have
  histories of restarts. Their state during the benchmark was Running
  but no sustainability claim is made.
- **kind cluster**: Performance characteristics differ from production
  Kubernetes or cloud deployments.
- **Single broker**: The Kafka broker is a single instance with 512MB
  heap and 3 partitions. Broker-side saturation is not evaluated.
