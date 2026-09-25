# Performance Bottleneck Analysis

**Task:** TASK-115
**Date:** 2026-09-25
**Scope:** Evidence-based analysis of performance measurements collected during
TASK-108 through TASK-114.

This report synthesizes benchmark evidence from the performance milestone
(TASK-108 through TASK-114) into a unified bottleneck analysis. Every
significant finding is classified as a confirmed bottleneck, observed
limitation, or hypothesis. Measured throughput is distinguished from
configured target rates throughout. No runtime behavior is modified as
part of this task.


## Executive Summary

The performance milestone measured producer throughput at three target rates
(100, 500, and 1000 events/sec), integrated consumer lag monitoring,
processing latency measurement, and API latency benchmarking into the
load-test harness, and observed runtime failures in the Warehouse Loader.

Key findings:

- The producer-side load generator achieved 95.55 events/sec at a 100 eps
  target (95.6% of target), 305.88 events/sec at a 500 eps target (61.2%),
  and 333.43 events/sec at a 1000 eps target (33.3%). The throughput gap
  widens at higher target rates.

- The measured throughput plateau between 500 eps and 1000 eps targets
  (305.88 vs 333.43 events/sec) indicates a producer-side saturation
  boundary in the load generator configuration, not a demonstrated
  pipeline processing capacity limit.

- API latency measurements under 100 eps pipeline load showed significant
  tail latency on data-serving endpoints: `/api/v1/analytics/price-changes`
  had a p95 of 1232.959 ms and p99 of 1951.586 ms with only 11 samples
  per endpoint.

- The Warehouse Loader showed a pattern of frequent restarts: 30 restarts
  as of TASK-110 and 35 restarts as of TASK-111. The E2E report recorded
  18,880 to 20,140 Silver Parquet files in the lake layer. The task
  specification reports an OOMKilled termination with exit code 137 and
  higher restart and file counts from a separate runtime inspection, but
  these figures are not present in committed benchmark artifacts. The root
  cause of the restart pattern is not established.

- No end-to-end downstream sustainability claim is supported by the
  collected evidence. Consumer lag monitoring was implemented but no
  sustained lag measurement under load is available in the benchmark
  artifacts.

No single component has been demonstrated through profiling or isolated
benchmarking to be the definitive root cause of the observed throughput
limitations. The findings in this report identify measurable behaviors and
frame the evidence gaps that further investigation must address.


## Benchmark Environment

All benchmarks in this analysis used the following common environment
unless otherwise noted:

| Component | Value |
|---|---|
| Platform | Linux 6.6.87.2 (WSL2) unless noted |
| Python | 3.12.14 |
| Kubernetes | kind cluster `ai-data-platform` |
| Namespace | `ai-data-platform` |
| Kafka | Single broker, KRaft mode, 512MB heap |
| Kafka topic | `products.raw.v1` |
| Topic partitions | 3 (TASK-109, TASK-110) / 6 (TASK-111) |
| Topic replication | 1 |
| Load-test harness | TASK-108 `LoadTestRunner` with `KafkaEventProducer` |
| Execution location | Inside `ingestion` pod (in-cluster) |
| Kafka connection | In-cluster `kafka:29092` |

### Environment Sensitivity

Earlier benchmark runs on Windows/localhost showed substantially lower
throughput due to higher producer-call latency. The Windows results are
documented in the individual benchmark reports but are not used as the
authoritative measurements in this analysis. The Linux in-cluster results
are used throughout unless explicitly stated otherwise.

The benchmark documents note that environmental variables (OS, network
path, port-forward vs in-cluster) differ across runs, and no single
variable has been independently isolated as the cause of the performance
difference.


## Evidence Summary

### Source Tasks and Artifacts

| Task | Deliverable | Key Artifact |
|---|---|---|
| TASK-108 | Load-test harness | `libs/load_test/`, `docs/load-test-harness.md` |
| TASK-109 | 100 eps benchmark | `docs/benchmark-100-eps.md` |
| TASK-110 | 500 eps benchmark | `docs/benchmark-500-eps.md` |
| TASK-111 | 1000 eps benchmark | `docs/benchmark-1000-eps.md` |
| TASK-112 | Kafka consumer lag measurement | `docs/kafka-lag-measurement.md` |
| TASK-113 | Processing latency measurement | `docs/processing-latency-measurement.md` |
| TASK-114 | API latency benchmark | `docs/benchmarks/TASK-114-api-latency.md`, `docs/benchmarks/task-114-api-latency-100eps.json` |


## Throughput Analysis

### Producer Throughput Scaling

The load-test harness was run at three configured target rates. All results
below are from Linux in-cluster runs unless noted.

| Benchmark | Target Rate | Actual Throughput | % of Target | Effective Workers |
|---|---:|---:|---:|---:|
| TASK-109 | 100 eps | 95.55 eps | 95.6% | 3 |
| TASK-110 | 500 eps | 305.88 eps | 61.2% | 15 |
| TASK-111 | 1000 eps | 333.43 eps | 33.3% | 30 |

The configured target rate was not sustained at any level. The gap between
target and actual throughput widens as the target rate increases.

### Throughput Plateau

The measured throughput increase from TASK-110 (305.88 eps) to TASK-111
(333.43 eps) was approximately 27.55 events/sec, a 9.0% increase, despite
a 2x increase in target rate (500 to 1000 eps) and a 2x increase in
effective workers (15 to 30).

This plateau is a measured fact. The cause has not been independently
isolated.

### Producer-Call Duration Analysis

Each benchmark recorded the producer-call duration, which includes event
serialization, Kafka producer synchronization, network round-trip to the
broker, and delivery-callback wait. It is not pure Kafka or network
latency.

| Benchmark | Effective Workers | Mean Producer-Call | p50 | p99 |
|---|---:|---:|---:|---:|
| TASK-109 | 3 | 5.142 ms | 2.767 ms | 47.626 ms |
| TASK-110 | 15 | 48.383 ms | 45.138 ms | 141.851 ms |
| TASK-111 | 30 | 89.494 ms | 81.829 ms | 255.885 ms |

The per-worker pacing interval is computed as
`effective_workers / target_rate = 30 ms` in all three configurations.

When the mean producer-call duration exceeds the 30 ms pacing interval,
workers are fully occupied and the pacing wait becomes effectively zero.
The throughput is then bounded by:

```
effective_workers / mean_producer_call_duration
```

| Benchmark | Implied Throughput | Measured Throughput |
|---|---:|---:|
| TASK-109 | 3 x 1000 / 5.142 = 583 eps | 95.55 eps |
| TASK-110 | 15 x 1000 / 48.383 = 310 eps | 305.88 eps |
| TASK-111 | 30 x 1000 / 89.494 = 335 eps | 333.43 eps |

At TASK-109, the implied throughput (583 eps) greatly exceeds the measured
throughput (95.55 eps) because the producer-call duration (5.1 ms) is well
below the pacing interval (30 ms). The pacing controller, not the producer,
limits throughput at this level.

At TASK-110 and TASK-111, the implied throughput closely matches the
measured throughput, indicating that producer-call duration is the binding
constraint on the load generator.

### Resource Utilization

| Benchmark | Peak RSS | Total CPU Time | Avg CPU Cores |
|---|---:|---:|---:|
| TASK-109 | 59.8 MB | 8.85 sec | 0.15 |
| TASK-110 | 62.5 MB | 27.56 sec | 0.46 |
| TASK-111 | 62.2 MB | 27.55 sec | 0.46 |

Peak RSS remained stable at approximately 60-63 MB across all benchmarks.
Total CPU time at 1000 eps (27.55 sec) was similar to 500 eps (27.56 sec).
No CPU bottleneck conclusion is drawn from this comparison.

### Target vs Throughput Distinction

Throughout this report, the configured target rate (e.g., "100 events/sec")
is the input to the load generator's rate controller. The actual throughput
is the measured number of events successfully produced and acknowledged by
Kafka divided by the test duration. These values differ in every benchmark.
The target rate is a configuration parameter, not a measurement result.


## Kafka Lag Analysis

### Measurement Capability

TASK-112 integrated systematic consumer lag monitoring into the load-test
harness. The `LagCollector` measures per-partition lag using `AdminClient`
for committed offsets and `Consumer.assign()` for high-watermark offsets.
Lag samples are collected in a background thread at a configurable polling
interval (default 5 seconds).

The implementation classifies lag growth patterns as stable, increasing,
decreasing, or insufficient_data based on quarter-average comparison.

### Operational Thresholds

| Threshold | Value | Meaning |
|---|---:|---|
| WARNING | 1,000 messages | Consumer is falling behind |
| CRITICAL | 10,000 messages | Consumer cannot keep up; risk of retention expiry |

### Available Evidence

The TASK-114 benchmark JSON report shows that lag monitoring was configured
with `lag_consumer_groups: []` (disabled) and `lag_topics: ["products.raw.v1"]`.
No consumer groups were actively monitored during the TASK-114 benchmark run.

The TASK-109, TASK-110, and TASK-111 benchmark documents do not include
consumer lag measurements. Each explicitly states that consumer lag
measurement was out of scope and deferred to TASK-112.

TASK-112 implemented the lag measurement capability but the benchmark
artifacts do not contain a run with active consumer group monitoring
enabled.

### Downstream Sustainability

No evidence in the collected benchmarks demonstrates that the complete
downstream pipeline sustainably processes events at any of the tested
rates. The benchmark documents consistently note this limitation:

- TASK-109: "this benchmark does not establish that all 5,734 produced
  events were processed by every downstream component"
- TASK-110: "No claim is made that the complete downstream pipeline
  sustained 500 events/sec"
- TASK-111: "This benchmark does not establish that all 20,040 produced
  events were processed by every downstream component"

### Pod Stability Observations

During benchmark runs, the following pre-existing instability was observed:

- **raw-writer**: 11 restarts total as of TASK-110 pre-benchmark check.
  Was Running and stable during the benchmark window.
- **warehouse-loader**: 30 restarts total as of TASK-110, 35 restarts as
  of TASK-111. Last restart 3 minutes before TASK-110 benchmark.

These restart counts are recorded as observations. Their relationship to
the benchmark load has not been established.


## Processing Latency Analysis

### Measurement Architecture

TASK-113 integrated end-to-end processing latency measurement into the
load-test harness. The approach records the wall-clock produce time for
each event, then a background thread periodically queries PostgreSQL for
those event IDs. The latency for each event is `query_time - produce_time`.

The full pipeline path measured is:

```
Ingestion -> Kafka -> Processor -> Lake Writer -> Warehouse Loader -> PostgreSQL
```

### Illustrative Stage Estimates

The TASK-113 documentation provides illustrative estimates for each
pipeline stage. These are design expectations, not measured values:

| Stage | Expected Latency | Notes |
|---|---|---|
| Produce -> Kafka ack | 1-50 ms | Network + broker fsync |
| Kafka -> Processor | 0-100 ms | Consumer poll interval + processing |
| Processor -> validated topic | 1-10 ms | Polars validation + produce |
| Validated -> Silver Parquet | 1-100 ms | Lake Writer consume + write |
| Silver -> Warehouse batch | 0-300 s | Dominant factor: batch schedule |
| Warehouse -> PostgreSQL | 10-500 ms | Parquet read + batch insert |

The warehouse loader batch interval (default 300 seconds) is identified
in the TASK-113 documentation as the dominant factor in end-to-end
latency. Events produced just after a batch completes must wait for the
next batch cycle.

### Available Measurements

The TASK-114 benchmark JSON report shows that PostgreSQL probing was
configured but the `pg_db_url` was empty (`""`), meaning PG latency
probing was disabled during the TASK-114 run.

No end-to-end processing latency measurements from a completed load test
run are present in the committed benchmark artifacts. The measurement
capability exists (TASK-113), but the benchmark evidence does not include
a run with PG probing enabled and completed.

### Measurement Imprecision

The TASK-113 documentation notes three sources of imprecision:

1. **Polling interval**: events are detected at the next poll cycle, adding
   up to `poll_interval` milliseconds of overcounting.
2. **Clock resolution**: wall-clock resolution depends on the OS.
3. **Warehouse batch cycle**: the dominant latency component is the
   warehouse loader's batch interval, which introduces a bimodal
   distribution depending on when in the batch cycle the event was
   produced.


## API Latency Analysis

### Benchmark Configuration

TASK-114 measured API latency concurrently with a 100 eps load test run.

| Parameter | Value |
|---|---|
| Target producer rate | 100 events/sec |
| Actual throughput | 94.50 events/sec |
| Produced events | 5,671 |
| Producer errors | 0 |
| Duration | 60.01 sec |
| API probe interval | 5 seconds |
| API endpoints probed | 4 |
| Total API samples | 44 (11 per endpoint) |

Source: `docs/benchmarks/task-114-api-latency-100eps.json`

### Measured API Latency

| Endpoint | Samples | p50 | p95 | p99 | Max | HTTP |
|---|---:|---:|---:|---:|---:|---|
| `/api/v1/health` | 11 | 8.081 ms | 42.399 ms | 68.299 ms | 74.774 ms | 11 x 200 |
| `/api/v1/quality/summary` | 11 | 14.241 ms | 221.817 ms | 384.875 ms | 425.640 ms | 11 x 200 |
| `/api/v1/products` | 11 | 49.850 ms | 846.760 ms | 1462.073 ms | 1615.901 ms | 11 x 200 |
| `/api/v1/analytics/price-changes` | 11 | 290.856 ms | 1232.959 ms | 1951.586 ms | 2131.243 ms | 11 x 200 |

### Overall API Latency

| Metric | Result |
|---|---:|
| Total samples | 44 |
| Mean | 178.517 ms |
| p50 | 44.314 ms |
| p95 | 411.995 ms |
| p99 | 1909.646 ms |
| Max | 2131.243 ms |

All 44 API probe requests returned HTTP 200.

### Observations

Among the four measured endpoints, `/api/v1/analytics/price-changes` had
the highest measured latency under the tested pipeline load. Its median
latency was 290.856 ms, while p95 reached 1232.959 ms and p99 reached
1951.586 ms.

`/api/v1/products` had a substantially lower median latency of 49.850 ms
but showed significant tail latency, with p95 of 846.760 ms and p99 of
1462.073 ms.

The health endpoint remained comparatively fast, with a median latency of
8.081 ms.

### Interpretation Limitations

The API probe measures client-side HTTP round-trip latency. It does not
isolate server-side processing time, PostgreSQL query execution time, or
network latency.

Only 11 samples were collected per endpoint during this 60-second run.
Therefore p95 and p99 values represent indicative runtime evidence rather
than high-confidence production SLO measurements.

The benchmark does not establish the root cause of the observed tail
latency. No profiling evidence is available that attributes the latency to
PostgreSQL, specific SQL queries, networking, or application code.


## Resource / Failure Analysis

### Warehouse Loader Restart Pattern

Committed benchmark evidence records the following warehouse-loader
restart counts:

| Observation Point | Restart Count | Source |
|---|---:|---|
| TASK-110 pre-benchmark | 30 | `docs/benchmark-500-eps.md` |
| TASK-111 pre-benchmark | 35 | `docs/benchmark-1000-eps.md` |

The warehouse-loader memory limit is 512Mi per the Kubernetes
troubleshooting guide (`docs/kubernetes-troubleshooting.md`).

The E2E source-to-PostgreSQL report (`docs/e2e/E2E-SOURCE-TO-POSTGRESQL-2026-09-24.md`)
recorded the following Silver Parquet file counts in the lake layer:

| Checkpoint | File Count | Source |
|---|---:|---|
| Initial discovery | 18,880 | E2E report, section 8 |
| After migration fix | 20,140 | E2E report, section 11 |

The E2E report also documents that the warehouse loader encountered an
error before processing the initial 18,880 files, and that a successful
load cycle subsequently processed all 20,140 files
(`read=20140 loaded=20140 failed=0`).

### Task Specification Runtime Observations

The TASK-115 task specification reports additional runtime observations
from a separate inspection:

- Termination reason: OOMKilled
- Exit code: 137
- Approximately 55,361 Silver Parquet files discovered before processing
- 134 pod restarts observed at the inspection point

These figures are not present in any committed benchmark artifact, E2E
report, or troubleshooting document in the repository. The committed
evidence shows 30-35 restarts and 18,880-20,140 files. The discrepancy
may reflect a later inspection point or additional pipeline activity after
the benchmark runs, but no committed artifact documents the higher values.

This report uses the committed evidence as the authoritative source for
quantitative claims, per the task constraint "Do not invent benchmark
numbers."

### Root Cause Status

The root cause of the warehouse-loader restart pattern is NOT established.

The `kubernetes-troubleshooting.md` guide lists OOMKilled as a possible
cause of pod termination and notes "Large batch processing in
warehouse-loader" as a common cause. However, no committed artifact
records an actual OOMKilled termination or exit code 137 for the
warehouse-loader.

The following potential contributors are noted as hypotheses only. None
has been demonstrated through profiling or isolated testing:

- The Silver Parquet file count (18,880-20,140 in committed evidence) may
  contribute to memory pressure during file discovery and scanning, but no
  profiling data establishes the memory cost.
- Polars lazy scanning behavior under large file counts has not been
  profiled.
- The 512Mi memory limit may be insufficient for the workload, but no
  memory profiling of the warehouse loader under representative load is
  available.
- MinIO network behavior, PostgreSQL batch insert sizing, and other
  factors have not been independently evaluated.

### Other Pod Instability

- **raw-writer**: 11 restarts observed as of TASK-110. The service was
  Running and stable during benchmark windows. The cause of restarts has
  not been investigated as part of this analysis.
- All other pods (api, ingestion, kafka, lake-writer, minio, postgresql,
  processor) showed 0 restarts during benchmark observation windows.


## Confirmed Bottlenecks

### 1. Load Generator Producer-Call Duration

**Classification: Confirmed bottleneck**

**Evidence:** The producer-call duration exceeds the per-worker pacing
interval at target rates of 500 eps and above. This directly limits the
load generator's ability to reach the configured target rate.

| Benchmark | Pacing Interval | Mean Producer-Call | Ratio |
|---|---:|---:|---:|
| TASK-109 | 30 ms | 5.142 ms | 0.17x |
| TASK-110 | 30 ms | 48.383 ms | 1.61x |
| TASK-111 | 30 ms | 89.494 ms | 2.98x |

At TASK-110 and TASK-111, the implied throughput calculated from
`effective_workers / mean_producer_call_duration` matches the measured
throughput within 2%, confirming that producer-call duration is the binding
constraint on the load generator.

**Scope:** This is a load-generator-side constraint. It does not establish
the maximum capacity of Kafka or the downstream pipeline.


## Observed Limitations

### 1. Throughput Plateau Between 500 and 1000 eps Targets

**Classification: Observed limitation**

The measured throughput increased by only 27.55 events/sec (from 305.88 to
333.43) when the target rate doubled from 500 to 1000 eps and the number
of effective workers doubled from 15 to 30.

The mean producer-call duration also increased from 48.383 ms to 89.494 ms
across this range. The cause of this increase has not been isolated.
Possible contributors include increased concurrent access to the Kafka
producer's internal serialization lock and broker-side queueing under
higher in-flight message volume, but TASK-111 did not independently
isolate the cause.

### 2. API Tail Latency Under Load

**Classification: Observed limitation**

The `/api/v1/analytics/price-changes` endpoint showed p95 latency of
1232.959 ms and `/api/v1/products` showed p95 latency of 846.760 ms during
a 100 eps load test. No API errors were observed (all 44 samples returned
HTTP 200).

The root cause of the tail latency has not been determined. The API probe
measures client-side HTTP round-trip latency and does not isolate
server-side processing, PostgreSQL query execution, or network latency.
Only 11 samples per endpoint were collected, limiting statistical
confidence.

### 3. No End-to-End Downstream Sustainability Demonstrated

**Classification: Observed limitation**

None of the benchmark runs (TASK-109, TASK-110, TASK-111, TASK-114)
measured whether all produced events were processed by every downstream
component during the test window. Consumer lag monitoring was implemented
(TASK-112) but was not actively enabled during the benchmark runs (the
`lag_consumer_groups` list was empty).

End-to-end processing latency measurement was implemented (TASK-113) but
PostgreSQL probing was disabled during the TASK-114 run (`pg_db_url` was
empty).

### 4. Warehouse Loader Instability

**Classification: Observed limitation**

The warehouse-loader accumulated 30 restarts (as of TASK-110) and 35
restarts (as of TASK-111) across benchmark observation windows. The E2E
report documented 18,880 to 20,140 Silver Parquet files in the lake layer
and recorded that the warehouse loader encountered a processing error
before ultimately completing a successful load of all 20,140 files.

The TASK-115 task specification reports OOMKilled as the termination
reason with higher restart and file counts from a later inspection, but
these figures are not present in committed artifacts. No committed artifact
records an actual OOMKilled termination for the warehouse-loader.

While the pod was Running during benchmark windows, the restart pattern
indicates recurring failures that affect the Silver-to-PostgreSQL data
path. The root cause has not been established through profiling or log
analysis.


## Hypotheses Requiring Investigation

### 1. Producer-Call Duration Increase Under Concurrency

**Classification: Hypothesis**

The producer-call duration increases with the number of effective workers
and target rate. Possible explanations include:

- Increased contention on the Kafka producer's internal serialization lock
  with more concurrent worker threads
- Broker-side queueing under higher in-flight message volume from 30
  concurrent producers
- Network stack behavior under higher concurrent connection utilization

No isolated experiment has tested these explanations independently. The
benchmark documents note that multiple environmental variables differ
between runs, making single-cause attribution unreliable.

### 2. Warehouse Loader Restart Root Cause

**Classification: Hypothesis**

The warehouse-loader has accumulated 30-35 restarts across benchmark
observations. The task specification reports OOMKilled as the termination
reason with 134 restarts and ~55,361 files from a later inspection, but
these figures are not in committed artifacts.

If the restarts are caused by memory exhaustion, possible explanations
include:

- The Silver Parquet file count (18,880-20,140 in committed evidence,
  potentially higher at later inspection points) may cause excessive
  memory usage during file discovery or scanning.
- Polars lazy scanning behavior accumulating unmaterialized query plans.
- An undersized memory limit (512Mi) for the workload profile.
- Batch insert sizing when writing to PostgreSQL.

No memory profiling of the warehouse loader under representative load is
available. The root cause has not been established. The OOMKilled
termination reason reported in the task specification has not been
verified against committed Kubernetes events or pod describe output.

### 3. API Tail Latency Attribution

**Classification: Hypothesis**

The high tail latency on `/api/v1/analytics/price-changes` and
`/api/v1/products` may be caused by:

- PostgreSQL query execution time under concurrent pipeline write load
- Missing or suboptimal database indexes for the analytical queries
- Connection pool exhaustion or contention
- Application-level serialization overhead
- Network latency between the API pod and PostgreSQL

No database profiling, query plan analysis, or application-level tracing
has been performed to attribute the latency to a specific cause.

### 4. Raw Writer Instability

**Classification: Hypothesis**

The raw-writer accumulated 11 restarts as of the TASK-110 benchmark. The
cause has not been investigated. Possible explanations include Kafka
connectivity issues, memory pressure, or application errors. No log
analysis has been performed.


## Recommended Follow-up Investigations

The following investigations are recommended based on the evidence gathered
in this analysis. Each recommendation is grounded in a specific evidence
gap identified above.

### 1. Warehouse Loader Memory Profiling and Restart Diagnosis

**Motivation:** The warehouse-loader has accumulated 30-35 restarts across
benchmark observations. The task specification reports OOMKilled as the
termination reason, but no committed artifact confirms this. The E2E
report documented 18,880-20,140 Silver Parquet files and a processing
error before a successful load cycle.

**Recommended approach:** First, inspect Kubernetes events and pod
describe output to determine the actual termination reason for the
warehouse-loader restarts. If OOMKilled is confirmed, profile memory usage
during a representative workload. Measure memory consumption as a function
of the number of discovered Parquet files. Determine whether the file
discovery phase, the Parquet scanning phase, or the PostgreSQL write phase
dominates memory usage.

### 2. End-to-End Processing Latency Benchmark

**Motivation:** No completed end-to-end processing latency measurement
exists in the benchmark artifacts. The measurement capability was
implemented in TASK-113 but has not been exercised in a committed benchmark
run.

**Recommended approach:** Run the load-test harness with PostgreSQL probing
enabled (`pg_db_url` configured) at 100 eps target rate. Record the
distribution of produce-to-PostgreSQL latency. This will quantify the
actual end-to-end pipeline delay and validate or refute the illustrative
stage estimates from TASK-113.

### 3. Consumer Lag Under Sustained Load

**Motivation:** Consumer lag monitoring was implemented in TASK-112 but no
benchmark run has actively monitored consumer group lag. Without this
measurement, it is unknown whether downstream consumers can keep up with
producer throughput.

**Recommended approach:** Run the load-test harness with
`--monitor-group processor --monitor-group raw-writer` at 100 eps and
500 eps target rates. Record lag growth patterns and compare against the
WARNING (1,000) and CRITICAL (10,000) thresholds.

### 4. API Latency Profiling

**Motivation:** API tail latency was observed but not attributed. With only
11 samples per endpoint and no server-side profiling, the root cause is
unknown.

**Recommended approach:** Enable database query logging and/or
OpenTelemetry tracing on the API service. Run a longer-duration benchmark
(to increase sample count) with concurrent pipeline load. Analyze query
plans for `/api/v1/analytics/price-changes` and `/api/v1/products`
endpoints.

### 5. Load Generator Async Produce Evaluation

**Motivation:** The producer-call duration is the binding constraint on
the load generator at 500 eps and above. The current implementation uses
synchronous produce-wait per worker.

**Recommended approach:** Evaluate switching from synchronous produce-wait
to batch/async production in the load-test harness. This is a load
generator configuration change, not a pipeline code change. The goal is to
determine whether higher producer throughput is achievable, which would
allow testing the pipeline at rates above 333 eps.

### 6. Raw Writer Restart Cause

**Motivation:** The raw-writer accumulated 11 restarts. The cause is
unknown and has not been investigated.

**Recommended approach:** Inspect raw-writer pod logs and Kubernetes events
to determine the termination reason for each restart. Check for OOMKilled,
application errors, or Kafka connectivity issues.


## Evidence References

### Primary Benchmark Artifacts

| Artifact | Path | Source Task |
|---|---|---|
| Load-test harness documentation | `docs/load-test-harness.md` | TASK-108 |
| 100 eps benchmark report | `docs/benchmark-100-eps.md` | TASK-109 |
| 500 eps benchmark report | `docs/benchmark-500-eps.md` | TASK-110 |
| 1000 eps benchmark report | `docs/benchmark-1000-eps.md` | TASK-111 |
| Kafka lag measurement design | `docs/kafka-lag-measurement.md` | TASK-112 |
| Processing latency measurement design | `docs/processing-latency-measurement.md` | TASK-113 |
| API latency benchmark report | `docs/benchmarks/TASK-114-api-latency.md` | TASK-114 |
| API latency JSON data | `docs/benchmarks/task-114-api-latency-100eps.json` | TASK-114 |

### Supporting Documentation

| Artifact | Path |
|---|---|
| Kafka operational metrics | `docs/kafka-metrics.md` |
| Kubernetes troubleshooting guide | `docs/kubernetes-troubleshooting.md` |
| E2E source-to-PostgreSQL report | `docs/e2e/E2E-SOURCE-TO-POSTGRESQL-2026-09-24.md` |
| E2E PostgreSQL-to-API report | `docs/e2e/E2E-POSTGRESQL-TO-API-2026-09-24.md` |
| Project constitution | `ai/PROJECT.md` |
| Agent operating rules | `ai/AGENTS.md` |

### Raw Result Files

| File | Source Task |
|---|---|
| `results/100eps-linux-incluster-verification.json` | TASK-109 |
| `results/500eps-linux-incluster.json` | TASK-110 |
| `results/1000eps-linux-incluster.json` | TASK-111 |
| `docs/benchmarks/task-114-api-latency-100eps.json` | TASK-114 |
