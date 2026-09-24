# TASK-109 Qwen Review

**Reviewer:** Qwen Code (independent, review-only)
**Date:** 2026-09-24
**Branch:** feature/TASK-109-100-events-per-second
**Verdict:** APPROVED

## Scope

Review of TASK-109: benchmark documentation task. The branch adds:
1. `docs/benchmark-100-eps.md` — benchmark results at 100 events/sec target
2. `results/100eps.json` — raw JSON benchmark data
3. 2-line prerequisite update to `docs/load-test-harness.md`

## What Was Verified

### Metric Arithmetic and JSON-Markdown Consistency

- Throughput: `1132 / 60.014 = 18.86 eps` (matches harness formula `produced / duration`)
- Duration `60.014`, produced `1132`, errors `0` — all match
- Latency min/mean/p50/p90/p95/p99/max — verbatim match between JSON and markdown
- `total_cpu_sec=1.969` reported as real value; `peak_rss_mb=0.0` correctly annotated "N/A (Windows)"
- Configuration block (rate 100, duration 60, workers 1, seed 42, topic, client ID, source) matches JSON

### Environment Facts (Verified Against Repo Config)

- Topic `products.raw.v1` = 3 partitions / replication 1 (verified in `kafka-topics-job.yaml`)
- Single broker, KRaft (`broker,controller`), heap `-Xmx512M` (verified in `kafka-deployment.yaml`)
- Advertised `PLAINTEXT_HOST://localhost:9092` (verified)
- Namespace `ai-data-platform` (verified)
- Pod list (9 workloads) matches actual deployments/statefulsets

### Root-Cause Analysis

Sound: the worker loop computes a 10ms interval for 100 eps, but the synchronous produce takes ~47ms, so the rate limiter never binds and throughput is latency-bound.

### Scope Discipline

`git diff main --stat` shows only `docs/benchmark-100-eps.md`, `results/100eps.json`, and a 2-line addition to `docs/load-test-harness.md`. No code changes, no optimization.

### Prerequisite Update

Correct: `KafkaProducerSettings` inherits `AppSettings.environment` (required, no default), so a real run fails without `APP_ENVIRONMENT`.

## Findings (All Low Severity — None Blocking)

### L1 — Per-worker budget correction (FIXED)

Original said "~100ms per event cycle" with 5 workers. Corrected to ~50ms (`worker_count / target = 5/100 = 50ms`), noting this is marginal given ~47ms produce latency.

### L2 — Cluster name conflation (FIXED)

Original said "kind cluster `kind-ai-data-platform`". Corrected to "kind cluster `ai-data-platform` (context `kind-ai-data-platform`)" — `kind-` prefix is the kubectl context name, not the cluster name.

### L3 — Theoretical maximum uses mean latency (FIXED)

Original used p50 (47ms) for theoretical max (~21 eps). Corrected to use mean (52.8ms) giving ~18.9 eps, which matches measured 18.86 almost exactly.

### L4 — Pre-existing cross-doc inconsistency (NOT FIXED — out of scope)

`docs/load-test-harness.md` (TASK-108) claims both `peak_rss_mb` and `total_cpu_sec` are "Linux-only... report 0.0" on Windows. The collector actually reads `os.times()` (cross-platform) for CPU and only `/proc` for RSS, so on Windows `total_cpu_sec` is meaningful — and `results/100eps.json` proves it with `1.969`. Only `peak_rss_mb` is truly Linux-only. Flagged for follow-up.

## Completeness Note

The TASK-109 objective lists "processing latency, Kafka lag, and API latency" as metrics to record, but the TASK-108 harness only measures producer-side latency. The documentation correctly does not invent those numbers and defers them to TASK-112/113/114. Given the "do not invent benchmark numbers" rule and "no code changes" scope, deferring with explicit limitation is the right call.

## Recommendation

APPROVED. L1-L3 fixed in commit `3c1c456`. L4 flagged for follow-up (TASK-108 harness doc).
