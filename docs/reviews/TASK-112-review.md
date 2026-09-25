# TASK-112 Review — Measure Kafka Lag

## 1. Review Header

- **Task ID:** TASK-112 — Measure Kafka Lag
- **Review date:** 2026-09-25
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `9057bf8875ded23202de65de42a1882dcf377afd..7877f5a6fb93c6ab8ba39d081bf52e5b00656442`
- **Reviewed HEAD:** `7877f5a6fb93c6ab8ba39d081bf52e5b00656442` on `feature/TASK-112`
- **Commit reviewed:** `7877f5a feat(TASK-112): add Kafka consumer lag measurement to load-test harness`
- **Scope:** Kafka consumer-lag measurement integrated into the load-test harness (`libs/load_test/`, `scripts/run_load_test.py`, `docs/kafka-lag-measurement.md`, `tests/test_lag_collector.py`).
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

### Authorities consulted

- `ai/PROJECT.md` (§5 at-least-once, §9 reliability, §10 observability, §12 testing)
- `ai/SPECIFICATION.md` (§8 Kafka Architecture, §20 Observability, §23 Performance Testing)
- `docs/adr/ADR-001-kafka-topic-configuration.md` (partition counts, consumer groups)
- `ai/tasks/TASK-112-measure-kafka-lag.md` (primary task source)
- `ai/ROADMAP.md` (Milestone 13 — Performance Testing)
- `ai/AGENTS.md`, `ai/REVIEWER.md`
- Existing implementation: `libs/observability/kafka_metrics.py`, `libs/observability/prometheus_exporter.py`, `libs/common/kafka_consumer.py`, TASK-108 harness, TASK-088 lag dashboard.

No authority conflicts identified.

---

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
|---|---|---|
| Systematic consumer-lag measurement across load tests | **Met** | `LagCollector` + `kafka_lag_probe.create_lag_query_fn()` wired into `LoadTestRunner.run()` via a background `_start_lag_monitor` thread (`libs/load_test/runner.py`). |
| Report lag **per partition and consumer group** | **Met** | `to_report_dict()` emits `consumer_lag.per_partition[]` with `consumer_group`, `topic`, `partition`, and min/max/mean/final lag (`lag_collector.py`). |
| Identify lag **growth patterns** under sustained load | **Met** | `_classify_growth()` classifies `stable`/`increasing`/`decreasing`/`insufficient_data`; `LagSummary.any_growing` → report `any_growing_lag`. |
| Document thresholds where lag becomes operationally concerning | **Met** | `docs/kafka-lag-measurement.md` (WARNING 1000 / CRITICAL 10000) plus `thresholds` in the JSON report (`lag_collector.py` constants). |
| Do not invent benchmark numbers; record actual results | **Met** | No fabricated numbers; thresholds are operational guidance, not benchmark claims. |
| Reuse existing Kafka metrics and monitoring infrastructure | **Partially met** | New `kafka_lag_probe.py` re-implements committed-offset/watermark querying instead of extending `libs/observability/kafka_metrics.py`; introduces a second `LagSample` dataclass. See Finding 3. |
| Measurements reproducible | **Met** | Deterministic collector, documented config env vars and CLI flags, monotonic-clock timestamps. |
| Document lag behavior and operational thresholds | **Met** | `docs/kafka-lag-measurement.md` covers architecture, configuration, thresholds, growth classification, report format, and limitations. |
| Deterministic tests where applicable | **Partially met** | `lag_collector.py` is well covered (201 lines); `kafka_lag_probe.py` has zero test coverage. See Finding 1. |
| No unrelated architecture changes or secrets | **Met** | Change set is confined to the load-test harness and its docs; no credentials/secrets introduced. |

---

## 3. Git Diff Review

**Files changed (8 files, +879 / −1):**

| File | Change |
|---|---|
| `docs/kafka-lag-measurement.md` | New (+149) |
| `libs/load_test/__init__.py` | +14/−1 (exports, docstring) |
| `libs/load_test/config.py` | +21 (4 new settings) |
| `libs/load_test/kafka_lag_probe.py` | New (+155) |
| `libs/load_test/lag_collector.py` | New (+249) |
| `libs/load_test/runner.py` | +43 (lag monitor integration) |
| `scripts/run_load_test.py` | +48 (CLI flags, probe wiring) |
| `tests/test_lag_collector.py` | New (+201) |

- **Scope correctness:** All changes belong to TASK-112. No unrelated files touched.
- **Unrelated changes:** None.
- **Architectural changes:** None to service boundaries, event contract, or ADR-001 partitioning/consumer-group assignments. The harness remains source-adapter independent.
- **Dependency/configuration changes:** No new third-party dependency (`confluent_kafka` already established). Four new `LoadTestSettings` fields (`lag_consumer_groups`, `lag_topics`, `lag_poll_interval_sec`, `lag_partition_count`), all opt-in with sensible defaults; lag monitoring is disabled when `lag_consumer_groups` is empty.
- **Accidental changes:** None observed (no debug code, temp files, generated artifacts, or secrets).
- **Test changes that weaken validation:** None. Existing tests untouched; only additions.
- **Behavior change to existing harness:** None for default runs — `lag_query_fn` defaults to `None`, so `_start_lag_monitor` returns `None` and the `consumer_lag` report section is only added when samples exist. Existing report consumers are unaffected.

---

## 4. Test and Verification Review

### Tests examined

- `tests/test_lag_collector.py` (new) — covers `LagSample`, `_classify_growth` (stable/increasing/decreasing/insufficient/increasing-from-zero), `LagCollector` empty/single/multi-batch, time-series, summary stats, partition sorting, `any_growing`, and report structure. Good coverage of the pure logic.
- `tests/test_load_test/test_runner.py` (existing) — runner orchestration; not extended to exercise `lag_query_fn` or `_start_lag_monitor`.
- No test references `kafka_lag_probe`, `create_lag_query_fn`, `_get_committed_offsets`, or `_start_lag_monitor`.

### Verification classification

| Check | Status | Evidence |
|---|---|---|
| `python -m pytest tests/test_lag_collector.py tests/test_load_test/ -q` | **Independently verified** | `67 passed in 11.89s` (run by reviewer). |
| `python -m ruff check libs/load_test/ scripts/run_load_test.py tests/test_lag_collector.py` | **Independently verified** | `All checks passed!` |
| `python -m ruff format --check …` | **Independently verified** | `10 files already formatted` |
| `python -m mypy libs/load_test/ scripts/run_load_test.py` | **Independently verified** | `Success: no issues found in 9 source files` |
| Kafka integration tests (`pytest -m integration`) | **Unverified / no evidence** | No integration test was added for the lag probe, and no integration run report was supplied. Not rerun (requires Docker Compose stack). |

### Test adequacy

- The deterministic, pure-logic `lag_collector.py` is well tested, including the growth classifier edge cases.
- The **Kafka-interacting module `kafka_lag_probe.py` is untested** — no unit test (mock-based) and no integration test. Given it encodes the committed-offset/watermark/lag semantics that are the substance of this task, this is the most material test gap (Finding 1).

---

## 5. Findings

### F1 — Moderate: `kafka_lag_probe.py` has no test coverage
- **Affected:** `libs/load_test/kafka_lag_probe.py` (whole module)
- **Problem:** The only module that actually talks to Kafka and implements the lag semantics (`list_consumer_group_offsets`, `get_watermark_offsets`, committed-offset→lag conversion, error handling) has neither a unit test nor an integration test. Only the pure `lag_collector.py` logic is tested.
- **Impact:** Regression risk in the substantive part of the task; the no-commit / partition-count / watermark behavior could change silently. The remaining Milestone 13 tasks (TASK-113/114/115) will rely on this measurement.
- **Recommendation:** Add a deterministic mock-based unit test for `create_lag_query_fn`/`_get_committed_offsets` (pattern exists in `tests/test_kafka_metrics.py`), and/or an `@pytest.mark.integration` test exercising the probe against the local Docker stack.

### F2 — Moderate: probe clients are never closed (resource leak)
- **Affected:** `libs/load_test/kafka_lag_probe.py:57-62`; `scripts/run_load_test.py` (no cleanup)
- **Problem:** `create_lag_query_fn` constructs an `AdminClient` and a `Consumer` but returns only the `query` callable; there is no cleanup hook. `run_load_test.py` closes the producer in its `finally` block but never closes these two clients.
- **Impact:** Open broker connections leak per run. Minor for a one-shot CLI (process exit), but the harness is documented as "reusable" — programmatic multi-run use accumulates leaked clients.
- **Recommendation:** Return a `(query, close)` pair or a small context-manager, and close both clients in `run_load_test.py`'s `finally`.

### F3 — Moderate: parallel re-implementation + `LagSample` name collision with existing lag infrastructure
- **Affected:** `libs/load_test/kafka_lag_probe.py`; `libs/load_test/lag_collector.py:21`
- **Problem:** The task's Performance Rule "Reuse existing Kafka metrics and monitoring infrastructure" is only partially honored. The codebase already has `libs.observability.kafka_metrics.LagSample` (fields `topic`, `partition`, `lag`, `sampled_at`) and `libs.common.kafka_consumer.ConsumerLag`/`sample_lag()`. TASK-112 introduces a **second, incompatible `LagSample`** (`elapsed_sec`, `consumer_group`, `topic`, `partition`, `lag`) and a fresh AdminClient-based query path.
- **Impact:** Two same-named dataclasses with different shapes in one repo create import ambiguity and maintenance confusion. There is partial justification — the existing `sample_lag()` only reports the consuming process's *own* assignment, whereas the load test must observe *arbitrary* consumer groups (`processor`, `raw-writer`) without joining them — but the naming collision and duplicated watermark-query pattern remain avoidable.
- **Recommendation:** Rename the load-test type (e.g., `LoadTestLagSample`) or extend/reuse the existing `LagSample` type, and consider placing the probe under `libs/observability` alongside the existing lag machinery.

### F4 — Moderate: lag-monitor failure is silent
- **Affected:** `libs/load_test/kafka_lag_probe.py:65-91`; `libs/load_test/runner.py:280-287`
- **Problem:** `query()` swallows all exceptions (debug-level logs only) and always returns a list. Consequently `runner._start_lag_monitor`'s `except Exception: logger.debug("lag_monitor_query_failed", …)` is effectively dead code — the query fn never raises. If the broker is unreachable or every group/topic query fails, the `consumer_lag` section is silently absent from the report, indistinguishable from "lag monitoring disabled".
- **Impact:** Contradicts observability principles (PROJECT.md §10, SPECIFICATION.md §20). An operator running a load test would not know lag was *not* measured.
- **Recommendation:** Track a lag-query error counter (e.g., reuse `KafkaMetric.LAG_ERRORS`) and/or emit a warning-level log, and surface an explicit marker in the report when monitoring was enabled but produced no samples.

### F5 — Moderate: partition count hardcoded instead of discovered
- **Affected:** `libs/load_test/kafka_lag_probe.py:36-38,124-154`
- **Problem:** The probe assumes `partition_count` partitions per topic (default 3) rather than reading the actual partition count from broker metadata. For a topic with more partitions the probe silently misses them; for a topic with fewer (e.g., `products.invalid.v1` = 1 per ADR-001) it issues doomed watermark queries that are skipped.
- **Impact:** Default is correct for `products.raw.v1` (3 partitions, ADR-001), so the out-of-the-box case works, but monitoring other topics yields incomplete or misleading results without any warning.
- **Recommendation:** Discover partitions via `AdminClient.list_topics()` / `Consumer.list_topics()` and use the actual counts, falling back to the configured value only as an explicit opt-in.

### F6 — Minor: `group.id` built from CPython `id()`
- **Affected:** `libs/load_test/kafka_lag_probe.py:60-62`
- **Problem:** `group.id = f"lag-probe-{id(admin)}"` uses the object id, which is not meaningful or stable across processes and could theoretically collide.
- **Impact:** Cosmetic/non-portable; works here because `admin` is captured and `assign()` (not `subscribe()`) means no real group is joined.
- **Recommendation:** Use `uuid.uuid4()` or a constant like `"load-test-lag-probe"`.

### F7 — Minor: "no committed offset" reported as full partition depth
- **Affected:** `libs/load_test/kafka_lag_probe.py:80-83`
- **Problem:** When a partition has no committed offset (`offset == -1`), lag is reported as `high - low` (the entire partition). A group that simply hasn't committed yet (e.g., `processor` before its first run) will read as catastrophically behind.
- **Impact:** Potentially misleading reading; distinct from the documented "committed offset staleness" limitation but not explicitly called out.
- **Recommendation:** Document this convention, or emit an explicit `None`/`unknown` sentinel for no-commit partitions.

### F8 — Minor: test file placement inconsistent with existing load-test tests
- **Affected:** `tests/test_lag_collector.py`
- **Problem:** The new test lives at the `tests/` root, whereas all other load-test tests live under `tests/test_load_test/`.
- **Impact:** Minor organizational inconsistency.
- **Recommendation:** Move to `tests/test_load_test/test_lag_collector.py`.

### F9 — Minor: module docstring drops still-measured metric
- **Affected:** `libs/load_test/__init__.py:4`
- **Problem:** Docstring changed "ingestion throughput" → "consumer lag", yet throughput (`throughput_events_per_sec`) is still measured and reported.
- **Impact:** Documentation drift; trivial.
- **Recommendation:** Keep both terms (e.g., "…latency, throughput, consumer lag, and resource utilization").

### F10 — Minor: lag thresholds not configurable
- **Affected:** `libs/load_test/lag_collector.py:82-83`
- **Problem:** `LAG_THRESHOLD_WARNING`/`LAG_THRESHOLD_CRITICAL` are hardcoded constants, unlike the rest of the harness's knobs.
- **Impact:** Fine for task scope; limits reuse across different environments where operational thresholds may differ.
- **Recommendation:** Optionally promote to `LoadTestSettings` fields.

---

## 6. Non-Defect Observations

- **Sound rebalance-avoidance design:** using `AdminClient.list_consumer_group_offsets` + `Consumer.assign()` (not `subscribe()`) correctly avoids triggering consumer-group rebalances and does not interfere with real consumers. This is well documented in `docs/kafka-lag-measurement.md`.
- **Correct thread-safety:** `LagCollector` mutates under a lock and computes summaries on a detached copy outside the lock — no lock held during `statistics.mean`/sorting.
- **Deterministic ordering:** `get_summary()` sorts samples by `elapsed_sec` before computing `final_lag`, so out-of-order batch arrival cannot corrupt "final" values.
- **Clean dependency injection:** `LagQueryFn` injection mirrors the existing `ProduceFn` pattern, keeping the collector unit-testable without a broker — a good separation of concerns.
- **Opt-in and backward-compatible:** lag monitoring is disabled by default and in `--dry-run`; the `consumer_lag` report section is only present when samples exist, so the existing report contract is preserved.
- **Correct lag sign handling:** `max(0, high - committed_offset)` guards against negative lag after log truncation/retention.

---

## 7. Verdict

**`APPROVED WITH NON-BLOCKING FINDINGS`**

The implementation is correct, well-typed, lint-clean, and the pure analysis logic is deterministically tested. It satisfies the TASK-112 objective: per-partition/per-group lag reporting, growth-pattern classification, and documented operational thresholds, without altering existing harness behavior or introducing architecture changes, dependencies, or secrets.

No Critical or High findings. The Moderate findings are non-blocking but should be addressed in follow-up — most importantly **test coverage for `kafka_lag_probe.py` (F1)** and **probe resource cleanup (F2)** before this measurement is relied upon by the downstream Milestone 13 tasks (TASK-113/114/115). The reuse/naming collision (F3), silent-failure observability gap (F4), and hardcoded partition count (F5) are maintainability and operational-quality issues rather than correctness defects.
