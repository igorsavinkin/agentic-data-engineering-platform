# Benchmark: 1000 Events/sec Load Test (TASK-111)

Benchmark of the event pipeline at a target rate of 1000 events/second using
the TASK-108 load-test harness.

## Test Configuration

| Parameter              | Value                          |
|------------------------|--------------------------------|
| Target rate            | 1000 events/sec                |
| Duration               | 60 seconds                     |
| Configured workers     | 1                              |
| Effective workers      | 30 (auto-scaled)               |
| Kafka bootstrap        | `kafka:29092` (in-cluster)     |
| Kafka topic            | `products.raw.v1`              |
| Topic partitions       | 6                              |
| Kafka client ID        | `load-test-harness`            |
| Event source           | `load-test`                    |
| Random seed            | 42                             |
| Total events limit     | 0 (unlimited, duration-bound)  |

### Auto-Scaler Calculation

The runner estimates 50 eps per worker with a 1.5x safety factor:

```text
needed = ceil(1000 / 50 * 1.5) = ceil(30) = 30 effective workers
```

Per-worker pacing interval:

```text
30 / 1000 = 0.030 sec = 30 ms
```

## Environment

| Component              | Value                          |
|------------------------|--------------------------------|
| Platform               | Linux (WSL2 kernel 6.6.87.2)  |
| Python                 | 3.12.14                        |
| Kubernetes             | kind cluster `ai-data-platform` |
| Namespace              | `ai-data-platform`             |
| Kafka                  | Single broker, KRaft mode      |
| Kafka connection       | In-cluster `kafka:29092`       |
| Execution location     | Inside `ingestion` pod         |

### Pre-Benchmark Pod Status

```
api-ffc4d7bb5-zh45f                 1/1  Running   0   15h
ingestion-56d454ff6f-ql2vp          1/1  Running   0   2d15h
kafka-788b477c9c-27djg              1/1  Running   0   4h24m
kafka-topics-setup-5xtck            0/1  Completed 0   3d16h
lake-writer-6d8bc8c984-bcbmz        1/1  Running   0   2d6h
minio-0                             1/1  Running   0   3d1h
postgresql-0                        1/1  Running   0   3d
processor-7cd699cd54-4zrxg          1/1  Running   0   2d6h
raw-writer-7c67f889c8-sz6rz         1/1  Running   11  2d1h
warehouse-loader-6f7cfdd45b-hp5c9   1/1  Running   35  23h
warehouse-migration-9dk4b           0/1  Completed 0   23h
```

Pre-flight verification confirmed:
- Kafka broker responsive via Python admin client
- `products.raw.v1` topic exists with 6 partitions
- No topic creation or repair was needed

## Measured Results

| Metric                         | Value          |
|--------------------------------|----------------|
| **Target event rate**          | 1000.0 events/sec |
| **Actual throughput**          | **333.43 events/sec** |
| **Events produced**            | 20,040         |
| **Events failed/errored**      | 0              |
| **Test duration**              | 60.103 sec     |
| **Latency min**                | 1.001 ms       |
| **Latency max**                | 684.766 ms     |
| **Latency mean**               | 89.494 ms      |
| **Latency p50**                | 81.829 ms      |
| **Latency p90**                | 107.584 ms     |
| **Latency p95**                | 141.129 ms     |
| **Latency p99**                | 255.885 ms     |
| **Peak RSS**                   | 62.2 MB        |
| **Total CPU time**             | 27.55 sec      |

### Result: TARGET NOT SUSTAINED

The load-test harness achieved **333.43 events/sec** against a target of **1000 events/sec**.
Zero errors occurred; all 20,040 produced events were successfully acknowledged
by the Kafka broker.

## Analysis

### Throughput Observation

The achieved throughput of ~333 events/sec is approximately 33.3% of the
configured 1000 events/sec target.

The auto-scaler provisioned 30 effective workers with a per-worker pacing
interval of 30 ms. However, the measured mean producer-call duration was
89.494 ms — approximately 3x the pacing interval. When the producer-call
duration exceeds the pacing interval, workers are fully occupied and the
pacing wait becomes effectively zero. The throughput is then bounded by:

```text
30 workers / 89.494 ms mean producer-call duration ≈ 335 events/sec
```

This closely matches the observed 333.43 events/sec.

### Producer-Call Duration Profile

The producer-call duration includes event serialization, Kafka producer
synchronization, network round-trip to the broker, and delivery-callback
wait. It is not pure Kafka or network latency.

| Percentile | Duration   |
|------------|------------|
| min        | 1.001 ms   |
| p50        | 81.829 ms  |
| p90        | 107.584 ms |
| p95        | 141.129 ms |
| p99        | 255.885 ms |
| max        | 684.766 ms |
| mean       | 89.494 ms  |

The p50 of 81.829 ms indicates that half of all producer calls took at least
~82 ms. The tail latency increased substantially above p50: p99 reached
255.885 ms and max reached 684.766 ms. The cause of this tail-latency
increase was not isolated by TASK-111.

### Comparison with Lower-Rate Benchmarks

| Benchmark | Target | Actual | Effective Workers | Mean Producer-Call | p50      | p99      |
|-----------|--------|--------|-------------------|--------------------|----------|----------|
| TASK-109  | 100 eps | 95.55 eps | 3  | 5.142 ms  | 2.767 ms | 47.626 ms |
| TASK-110  | 500 eps | 305.88 eps | 15 | 48.383 ms | 45.138 ms | 141.851 ms |
| TASK-111  | 1000 eps | 333.43 eps | 30 | 89.494 ms | 81.829 ms | 255.885 ms |

The producer-call duration increases with target rate. At 100 eps with
3 workers, the mean producer-call was 5.1 ms. At 1000 eps with 30 workers,
it rose to 89.5 ms. Possible contributors include increased concurrent
access to the Kafka producer's internal serialization lock and broker-side
queueing under higher in-flight message volume, but TASK-111 did not
independently isolate the cause.

### Resource Utilization

| Metric     | TASK-109 (100 eps) | TASK-110 (500 eps) | TASK-111 (1000 eps) |
|------------|--------------------:|--------------------:|---------------------:|
| Peak RSS   | 59.8 MB            | 62.5 MB            | 62.2 MB             |
| Total CPU  | 8.85 sec           | 27.56 sec          | 27.55 sec           |

Peak RSS remained stable across all three benchmarks (~60-63 MB). Total CPU
time at 1000 eps (27.55 sec) was similar to 500 eps (27.56 sec) and higher
than at 100 eps (8.85 sec). No CPU bottleneck conclusion is drawn from this
comparison.

## Post-Benchmark Health

All pods remained in the same state before and after the benchmark. No new
restarts, OOMKills, or CrashLoopBackOff events were observed during or after
the 60-second test.

Pre-existing restart counts (raw-writer: 11, warehouse-loader: 35) were not
affected by the benchmark.

## Reproduction Command

```bash
kubectl exec -n ai-data-platform ingestion-56d454ff6f-ql2vp -- python -c "
import sys, json, logging
sys.path.insert(0, '/app')
logging.basicConfig(level=logging.WARNING)
from libs.load_test import LoadTestRunner, LoadTestSettings
from libs.common.kafka_producer import KafkaEventProducer, KafkaProducerSettings

settings = LoadTestSettings(
    target_events_per_sec=1000.0,
    duration_sec=60.0,
    worker_count=1,
    kafka_bootstrap_servers='kafka:29092',
    kafka_raw_topic='products.raw.v1',
    kafka_client_id='load-test-harness',
    output_path='/tmp/1000eps-incluster.json',
    source_name='load-test',
    seed=42,
)

ks = KafkaProducerSettings(
    kafka_bootstrap_servers='kafka:29092',
    kafka_raw_topic='products.raw.v1',
    kafka_client_id='load-test-harness',
)
producer = KafkaEventProducer(ks)
produce = lambda event: (producer.publish(event), event.event_id)[1]

runner = LoadTestRunner(settings=settings, produce_fn=produce)
report = runner.run()
producer.close()
print(json.dumps(report, indent=2, sort_keys=True))
"
```

Requires:
- kind cluster `kind-ai-data-platform` running
- All platform pods healthy in namespace `ai-data-platform`
- Kafka accessible at in-cluster `kafka:29092`

## Raw Results

The full JSON report is at `results/1000eps-linux-incluster.json`.

## Scope and Limitations

- **Producer-side only**: The harness measures producer-call duration
  (serialization + produce + delivery-callback wait). This is not pure
  Kafka or network latency. End-to-end pipeline latency (consumer
  processing, validation, Parquet writes, PostgreSQL loading) is not
  measured here.
- **Consumer lag** belongs to TASK-112.
- **Processing latency** belongs to TASK-113.
- **API latency** belongs to TASK-114.
- **Bottleneck conclusions** belong to TASK-115.
- **No downstream sustainability claim**: This benchmark does not establish
  that all 20,040 produced events were processed by every downstream
  component during the 60-second test.
- **Single broker**: The Kafka deployment uses a single broker. Broker-side
  saturation under concurrent produce from 30 workers was not independently
  measured.
- **kind cluster**: Performance characteristics differ from production
  Kubernetes or cloud deployments.
- **No downstream backpressure measurement**: The benchmark measures only
  the producer side. Consumer lag, processing queue depth, and write
  amplification are not captured.

## Throughput Progression Summary

| Benchmark | Target | Actual | % of Target | Result |
|-----------|--------|--------|-------------|--------|
| TASK-109  | 100 eps | 95.55 eps | 95.6% | Near target |
| TASK-110  | 500 eps | 305.88 eps | 61.2% | Below target |
| TASK-111  | 1000 eps | 333.43 eps | 33.3% | Below target |

The gap between configured target and actual throughput widens at higher
rates. This benchmark records the measured result. Root-cause analysis and
optimization recommendations are scoped to subsequent tasks.
