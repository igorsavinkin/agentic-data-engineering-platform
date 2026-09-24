# Qwen Review: TASK-PERF-FIX-001

**Branch:** `feature/TASK-PERF-FIX-001`
**Date:** 2026-09-24
**Reviewer:** Qwen CLI (qwen review)
**Scope:** Load-generator injection capacity increase for TASK-108 harness

## Summary

The changes increase the TASK-108 load-test harness throughput capacity from
~25 eps (single-threaded, uuid4-based) to reliably sustain 100+ eps with
headroom for 500 and 1000 eps benchmarks. The approach is sound: eliminate
per-event overhead (uuid4, Pydantic validation, timestamp syscalls), add
auto-scaling worker threads, and remove lock contention on the hot path.

## Findings

### C1 — Critical: Non-atomic integer increment under GIL

**File:** `libs/load_test/metrics_collector.py`
**Status:** FIXED

`self._produced_count += 1` and `self._error_count += 1` are NOT atomic under
the GIL. The compound operation compiles to multiple bytecodes
(`LOAD_ATTR`, `LOAD_SMALL_INT`, `BINARY_OP`, `SWAP`, `STORE_ATTR`), and a
thread preemption between LOAD and STORE can lose updates.

**Fix applied:** Removed separate integer counters. `produced_count` is now
derived from `len(self._latencies)` and `error_count` from `len(self._errors)`.
`list.append` is a single bytecode (`CALL_METHOD`) and is atomic under the GIL.

### M1 — Major: Event ID entropy reduced from 122 to 32 bits

**File:** `libs/load_test/runner.py`
**Status:** FIXED

The run_id prefix was truncated to 8 hex characters (`self._run_id[:8]`),
providing only 32 bits of entropy. With the birthday paradox, collisions become
likely after ~65k events, which is within the 5000-event benchmark scope.

**Fix applied:** Changed to `self._run_id.replace("-", "")` which preserves
the full 32 hex characters (122 bits of UUID v4 entropy).

### M2 — Major: Auto-scaling ignores `total_events`, causing overshoot

**File:** `libs/load_test/runner.py`
**Status:** FIXED

When `total_events=10` and `target_events_per_sec=10000`, the auto-scaling
formula provisions `ceil(10000/50 * 1.5) = 300` workers (capped at 64), even
though only 10 events are needed. This wastes resources and can cause
thread-scheduling overhead.

**Fix applied:** Added `min(effective, max(total_events, 1))` cap when
`total_events > 0`.

### M3 — Major: `model_construct()` bypasses validation — fragile contract

**File:** `libs/load_test/event_generator.py`
**Status:** Accepted (info-level risk)

`model_construct()` skips all Pydantic validators. If new required fields are
added to `ProductObservationEvent` or `ProductObservationPayload`, the
generator will silently produce invalid events. This is acceptable for a
load-test harness where the generator is updated alongside the contract, but
should be documented.

**Mitigation:** Module docstring already notes this is "safe because the
generator produces valid data by construction." The test suite validates
generated events against the contract.

### i1 — Minor: Lock retained on `record_resource_snapshot` but not needed for append

**File:** `libs/load_test/metrics_collector.py`
**Status:** Accepted (no fix needed)

The lock on `record_resource_snapshot` protects the `self._resource_snapshots`
list append, but `list.append` is already GIL-atomic. The lock is retained
because the method also reads `os.times()` and `/proc/<pid>/status`, and the
lock ensures the snapshot is internally consistent. This is correct — the
lock protects the multi-step read, not the append.

### i2 — Minor: `_TIMESTAMP_REFRESH_SEC = 0.1` may cause stale timestamps

**File:** `libs/load_test/event_generator.py`
**Status:** Accepted (no fix needed)

The cached timestamp is refreshed every 100ms. Under high throughput, many
events share the same `collected_at` and `produced_at` values. This is
acceptable for load testing — the events are synthetic and the timestamp
granularity doesn't affect the benchmark validity.

### i3 — Info: `_ESTIMATED_EPS_PER_WORKER = 50` is platform-dependent

**File:** `libs/load_test/runner.py`
**Status:** Accepted (no fix needed)

The 50 eps per worker estimate is calibrated for this machine (Windows, Python
3.14). On Linux with different CPU/GIL characteristics, the actual per-worker
throughput may differ. The auto-scaling formula includes a 1.5x safety margin,
which should absorb moderate platform differences.

### i4 — Info: `stop_event.wait(timeout=sleep_time)` is more precise than `time.sleep`

**File:** `libs/load_test/runner.py`
**Status:** Positive observation

Using `stop_event.wait()` instead of `time.sleep()` allows immediate
termination when the stop signal is set, avoiding up to 1 interval of
delayed shutdown. Good design choice.

## Verdict

**APPROVED** after fixes. The C1 critical data race and M1/M2 major issues
have been addressed. The remaining info-level findings are acceptable for a
load-test harness that is not production infrastructure.

## Files Changed

| File | Change |
|------|--------|
| `libs/load_test/metrics_collector.py` | Lock-free hot path; len()-based counts |
| `libs/load_test/event_generator.py` | Counter-based IDs; model_construct; cached timestamps |
| `libs/load_test/runner.py` | Auto-scaling workers; hot-path optimizations; total_events cap |
| `docs/load-test-harness.md` | Fixed total_cpu_sec platform note |
| `tests/test_load_test/test_event_generator.py` | Event ID format tests |
| `tests/test_load_test/test_metrics_collector.py` | Concurrent record_latency test |
| `tests/test_load_test/test_runner.py` | 100 eps auto-scaling test; worker provisioning test |
