# TASK-115 — Document Performance Bottlenecks

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-114.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-115 only.

## Objective

Produce an evidence-based performance bottleneck analysis for the platform
using measurements collected during TASK-108 through TASK-114.

The analysis must distinguish measured facts from interpretations and
unverified hypotheses.

This is primarily an analysis/documentation task.
Do not optimize, redesign, or modify runtime behavior as part of TASK-115.


## Evidence Sources

Use repository evidence produced by TASK-108 through TASK-114.

Do not invent benchmark numbers.

### TASK-109 — 100 events/sec

Recorded actual throughput:

- 95.55 events/sec

Use the repository benchmark evidence as the authoritative source.

### TASK-110 — 500 events/sec

Recorded actual throughput:

- 305.88 events/sec

Use the repository benchmark evidence as the authoritative source.

### TASK-111 — 1000 events/sec

Recorded actual throughput:

- 333.43 events/sec

Use the repository benchmark evidence as the authoritative source.

The limited increase from TASK-110 to TASK-111 may be described as a
measured throughput plateau.

Do NOT infer from this alone that Kafka, the producer, CPU, networking,
or another component is the root cause.


### TASK-112 — Kafka Lag

Use TASK-112 repository evidence and runtime measurements.

Do not claim that the complete downstream pipeline sustainably processes
333.43 events/sec unless consumer-lag evidence demonstrates this.

Existing lag observations must be interpreted in the context of the
actual load under which they were collected.


### TASK-113 — Processing Latency

Use the TASK-113 implementation and recorded benchmark/runtime evidence.

Extract actual measurements from repository evidence.

Do not reconstruct or invent missing measurements.


### TASK-114 — API Latency

Primary runtime evidence:

- `docs/benchmarks/TASK-114-api-latency.md`
- `docs/benchmarks/task-114-api-latency-100eps.json`

Recorded benchmark:

- target producer rate: 100 events/sec
- actual throughput: 94.50 events/sec
- produced events: 5,671
- producer errors: 0

Measured API latency:

| Endpoint | p50 | p95 | p99 |
|---|---:|---:|---:|
| `/api/v1/health` | 8.081 ms | 42.399 ms | 68.299 ms |
| `/api/v1/products` | 49.850 ms | 846.760 ms | 1462.073 ms |
| `/api/v1/analytics/price-changes` | 290.856 ms | 1232.959 ms | 1951.586 ms |
| `/api/v1/quality/summary` | 14.241 ms | 221.817 ms | 384.875 ms |

All 44 API probe requests returned HTTP 200.

Only 11 samples were collected per endpoint.
Tail latency therefore represents indicative runtime evidence rather
than high-confidence production SLO statistics.

Do not attribute API latency to PostgreSQL, SQL queries, networking,
or application code without profiling evidence.


## Additional Runtime Observation — Warehouse Loader

During runtime verification the Warehouse Loader was observed with:

- termination reason: `OOMKilled`
- exit code: `137`
- approximately 55,361 Silver Parquet files discovered before processing
- 134 pod restarts observed at the inspection point

The OOM condition is confirmed runtime evidence.

The root cause is NOT established.

Do not claim that small Parquet files, Polars lazy scanning, MinIO,
PostgreSQL, or another component caused the OOM unless supported by
profiling evidence.


## Classification Rules

Every significant finding must be classified as one of:

### Confirmed bottleneck

A bottleneck whose cause is directly demonstrated by benchmark,
profiling, monitoring, or runtime evidence.

### Observed limitation

A measurable limitation, degradation, failure, or performance behavior
exists, but its root cause has not been demonstrated.

### Hypothesis

Evidence suggests a possible explanation, but additional investigation
is required.

Never promote a hypothesis to a confirmed bottleneck.


## Required Analysis

Analyze:

1. producer throughput scaling;
2. Kafka consumer lag evidence;
3. end-to-end processing latency;
4. API latency;
5. resource/failure observations;
6. differences between configured target rates and achieved throughput;
7. whether evidence demonstrates downstream sustainability;
8. confirmed bottlenecks;
9. observed limitations;
10. hypotheses requiring profiling or further benchmarks.


## Deliverable

Create or update:

`docs/performance/bottleneck-analysis.md`

The report should contain:

- Executive Summary
- Benchmark Environment
- Evidence Summary
- Throughput Analysis
- Kafka Lag Analysis
- Processing Latency Analysis
- API Latency Analysis
- Resource / Failure Analysis
- Confirmed Bottlenecks
- Observed Limitations
- Hypotheses Requiring Investigation
- Recommended Follow-up Investigations
- Evidence References


## Constraints

- Do not invent benchmark numbers.
- Do not present configured target throughput as achieved throughput.
- Do not infer causality from correlation alone.
- Do not modify production/runtime behavior.
- Do not perform performance optimizations.
- Do not redesign architecture.
- Do not silently fix discovered problems.
- Prefer repository benchmark artifacts over values copied into this task
  when both exist.


## Acceptance Criteria

- [ ] TASK-108–114 performance evidence has been reviewed.
- [ ] Actual measured throughput is distinguished from configured target rate.
- [ ] Kafka lag evidence is documented with its measurement context.
- [ ] TASK-113 processing latency evidence is included.
- [ ] TASK-114 runtime API benchmark is included.
- [ ] Warehouse Loader OOMKilled observation is documented.
- [ ] Confirmed bottlenecks are separated from observed limitations.
- [ ] Hypotheses are explicitly identified as hypotheses.
- [ ] No unsupported root-cause claims are made.
- [ ] Recommended follow-up investigations are evidence-based.
- [ ] `docs/performance/bottleneck-analysis.md` is created or updated.
- [ ] No runtime behavior is changed.