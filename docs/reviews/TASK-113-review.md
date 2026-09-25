# TASK-113 Review — Measure Processing Latency

## 1. Review Header

- **Task ID:** TASK-113 — Measure Processing Latency
- **Review date:** 2026-09-25
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `0386386ba25395d0c8af128fbf74fcb46668b709...deba6d4d07b52e0d3c77eb59edb75e71ed432ca9`
- **Reviewed HEAD:** `deba6d4d07b52e0d3c77eb59edb75e71ed432ca9` on `feature/TASK-113`
- **Commit reviewed:** `deba6d4 feat(TASK-113): add end-to-end processing latency measurement`
- **Scope:** End-to-end processing-latency measurement (Kafka produce → PostgreSQL availability) integrated into the load-test harness (`libs/load_test/`, `scripts/run_load_test.py`, `docs/processing-latency-measurement.md`, `tests/test_latency_collector.py`, `tests/test_pg_latency_probe.py`).
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

### Authorities consulted

- `ai/PROJECT.md` (§5 at-least-once, §10 observability, §11 security, §12 testing)
- `ai/SPECIFICATION.md` (§7 event contract, §20 observability, §23 performance testing)
- `docs/adr/ADR-001-kafka-topic-configuration.md` (partitioning/consumer groups — not materially affected)
- `ai/tasks/TASK-113-measure-processing-latency.md` (primary task source)
- `ai/ROADMAP.md` (Milestone 13 — Performance Testing)
- `ai/AGENTS.md`, `ai/REVIEWER.md`
- Existing implementation: TASK-108 harness (`libs/load_test/runner.py`, `metrics_collector.py`, `event_generator.py`), TASK-112 lag probe (`kafka_lag_probe.py`, `lag_collector.py`), warehouse schema (`warehouse/migrations/versions/001…003`, `warehouse/schema/SCHEMA_DESIGN.md`), `libs/observability/otel_config.py`.

No authority conflicts identified.

---

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
|---|---|---|
| Systematic processing-latency measurement across load tests | **Met** | `LatencyCollector` + `pg_latency_probe.create_pg_probe_fn()` wired into `LoadTestRunner.run()` via background `_start_pg_latency_monitor` (`libs/load_test/runner.py`). |
| Report end-to-end latency from event ingestion (Kafka produce) to PostgreSQL availability | **Met** | `record_produce()` stamps produce wall-clock UTC; `record_pg_arrivals()` computes `query_time − produce_time` (`latency_collector.py`). Report `processing_latency` section emitted by `runner.run()`. |
| Identify latency distribution (p50, p95, p99) | **Met** | `_compute_percentiles()` produces `min/p50/p95/p99/max/mean` (`latency_collector.py`). |
| Document where latency is spent | **Partially met** | `docs/processing-latency-measurement.md` identifies the warehouse-loader batch interval as the dominant factor, but the "Pipeline Stage Breakdown" table uses unmeasured latency ranges (see Finding F8). |
| Do not invent benchmark numbers; record actual results | **Met** | No fabricated results in the report path — `latency_ms` is computed from real measurements. The only unmeasured numbers are in the docs' stage table (F8). |
| Reuse existing tracing/metrics infrastructure where available | **Partially met** | Reuses the TASK-108 harness (`MetricsCollector`, `LoadTestRunner`) and the TASK-112 `create_*_probe_fn` factory pattern. OpenTelemetry is explicitly deferred in the docs for per-stage precision. No reuse conflict. |
| Measurements reproducible | **Met** | Deterministic collector; configurable `pg_latency_poll_interval_sec` / `pg_latency_source`; both timestamps from the same machine clock (no cross-node skew). |
| Document latency distribution and bottlenecks | **Met** | Docs cover architecture, data flow, configuration, report format, measurement imprecision, limitations, and the dominant bottleneck. |
| Deterministic tests where applicable | **Met** | `latency_collector.py` is well covered (206 lines); `pg_latency_probe.py` has mock-based unit coverage (see F4 for the integration gap). |
| No unrelated architecture changes or secrets | **Partially met** | Change set is confined to the harness/docs; however the new `pg_db_url` setting is dumped into the report and stdout, which can expose a connection-string password (see F1). |

---

## 3. Git Diff Review

**Files changed (9 files, +831 / −2):**

| File | Change |
|---|---|
| `docs/processing-latency-measurement.md` | New (+156) |
| `libs/load_test/__init__.py` | +15/−2 (exports, docstring) |
| `libs/load_test/config.py` | +16 (3 new settings) |
| `libs/load_test/latency_collector.py` | New (+181) |
| `libs/load_test/pg_latency_probe.py` | New (+69) |
| `libs/load_test/runner.py` | +59 (latency monitor integration) |
| `scripts/run_load_test.py` | +40 (CLI flags, probe wiring) |
| `tests/test_latency_collector.py` | New (+206) |
| `tests/test_pg_latency_probe.py` | New (+91) |

- **Scope correctness:** All changes belong to TASK-113. No unrelated files touched.
- **Unrelated changes:** None.
- **Architectural changes:** None to service boundaries, the event contract, or ADR-001 partitioning. The harness remains source-adapter independent; the probe connects read-only to PostgreSQL, consistent with the load-test harness being a measurement client rather than a pipeline component.
- **Dependency/configuration changes:** No new third-party dependency — `psycopg2` is already declared (`psycopg2-binary>=2.9` in `requirements.txt`, used by the warehouse loader). Three new `LoadTestSettings` fields (`pg_db_url`, `pg_latency_poll_interval_sec`, `pg_latency_source`), all opt-in; probing is disabled when `pg_db_url` is empty or in `--dry-run`.
- **Accidental changes:** None observed (no debug code, temp files, generated artifacts, or committed secrets).
- **Test changes that weaken validation:** None. Existing tests untouched; only additions.
- **Behavior change to existing harness:** None for default runs — `pg_query_fn` defaults to `None`, so `_start_pg_latency_monitor` returns `None` and the `processing_latency` report section is only added when samples exist. Existing report consumers are unaffected.

---

## 4. Test and Verification Review

### Tests examined

- `tests/test_latency_collector.py` (new) — covers `ProduceRecord`/`EndToEndSample` frozen dataclasses, `LatencyCollector` produce/arrival/duplicate/unknown-ID behavior, pending/sample counts, report with full and partial resolution, and `_compute_percentiles` edge cases. Good coverage of the pure logic.
- `tests/test_pg_latency_probe.py` (new) — covers empty-ID short-circuit, found-ID return, `postgresql+psycopg2://` scheme stripping, connection close on success and on error, and source-filter parameter placement, all via mocked `psycopg2`.
- `tests/test_load_test/test_runner.py` (existing) — not extended to exercise `pg_query_fn` or `_start_pg_latency_monitor`.
- No test references `create_pg_probe_fn`'s SQL against a real schema; the mock only asserts `"s.name = %s"` appears in the query and `params[0]` equals the source (see F4).

### Verification classification

| Check | Status | Evidence |
|---|---|---|
| `python -m pytest tests/test_latency_collector.py tests/test_pg_latency_probe.py tests/test_lag_collector.py tests/test_load_test/ -q` | **Independently verified** | `90 passed in 11.99s` (run by reviewer). |
| `python -m ruff check libs/load_test/ scripts/run_load_test.py tests/test_latency_collector.py tests/test_pg_latency_probe.py` | **Independently verified** | `All checks passed!` |
| `python -m ruff format --check libs/load_test/ scripts/run_load_test.py tests/test_latency_collector.py tests/test_pg_latency_probe.py` | **Independently verified** | `13 files already formatted` |
| `python -m mypy libs/load_test/latency_collector.py libs/load_test/pg_latency_probe.py libs/load_test/runner.py libs/load_test/config.py scripts/run_load_test.py` | **Independently verified** | `Success: no issues found in 5 source files` |
| PostgreSQL probe schema correctness | **Independently verified (static)** | Probe SQL checked against `warehouse/migrations/versions/001…003` (`product_observations.event_id` added in 002; `source_product_id`, `source_products.id/source_id`, `sources.name` all present). Query is correct. |
| PostgreSQL integration tests (`pytest -m integration`) | **Unverified / no evidence** | No integration test was added for the probe, and no integration run report was supplied. Not rerun (requires Docker Compose stack). |

### Test adequacy

- The deterministic, pure-logic `latency_collector.py` is well tested, including duplicate/unknown-ID handling and partial resolution.
- The `pg_latency_probe.py` unit tests exercise the query's structure only via mocks; they would not catch a wrong table/column name or a broken JOIN. Given the probe's SQL is the substantive interface to the warehouse, the absence of an integration test against the real schema is the most material test gap (F4).

---

## 5. Findings

### F1 — Moderate: `pg_db_url` (may embed a password) is dumped into the report and stdout
- **Affected:** `libs/load_test/config.py` (`pg_db_url` field); `libs/load_test/runner.py` (`build_report(settings_dict=self._settings.model_dump(), …)`); `scripts/run_load_test.py` (final `print(json.dumps(report, …))`).
- **Problem:** `LoadTestSettings.model_dump()` now includes `pg_db_url`, which is written into the JSON report's `configuration` section and echoed to stdout. A connection URL of the documented form `postgresql://user:pass@host/db` exposes the password. `BaseAppSettings` has no secret redaction and `pg_db_url` is a plain `str`, not `SecretStr`.
- **Impact:** Runtime secret exposure in a persisted artifact and terminal output. Local-dev credentials are typically low-value (`platform/platform-local`), but pointing the harness at a real RDS (TASK-123) would leak a real password. Contradicts PROJECT.md §11 "Secrets must never be logged" and the task DoD "no secrets introduced".
- **Recommendation:** Model `pg_db_url` as `SecretStr`, or exclude/redact it from `model_dump()` before building the report (e.g., mask the password component), so the report and stdout never contain credentials.

### F2 — Moderate: probe source filter is not coupled to `--source`
- **Affected:** `scripts/run_load_test.py` (probe wiring); `libs/load_test/config.py` (`pg_latency_source` default `"load-test"`).
- **Problem:** `--source` changes the source embedded in generated events (`source_name`), but the probe filters on `pg_latency_source`, which defaults to `"load-test"` and has **no CLI flag**. Running `--source custom --pg-url …` produces events tagged `custom` while the probe still queries `WHERE s.name = 'load-test'`, silently returning zero matches.
- **Impact:** Silent empty `processing_latency` results for any non-default source. The env var `APP_PG_LATENCY_SOURCE` can work around it, but the natural CLI path is broken.
- **Recommendation:** Default `pg_latency_source` to the effective `source_name`, and/or add a `--pg-source` flag. At minimum, log a warning when `pg_latency_source != source_name`.

### F3 — Moderate: unbounded `IN (...)` clause can exceed PostgreSQL limits and degrade
- **Affected:** `libs/load_test/pg_latency_probe.py` (`placeholders = ", ".join(["%s"] * len(event_ids))`).
- **Problem:** Every poll (and the final post-run probe) sends the entire pending-ID list in a single `WHERE … IN (…)`. At 1000 eps × 60 s ≈ 60 000 pending IDs, this approaches PostgreSQL's 65 535 bind-parameter limit; higher rates or longer durations exceed it, raising an error that is swallowed by `logger.debug` in `_start_pg_latency_monitor`.
- **Impact:** At scale the measurement silently fails or becomes very heavy; a single large query also adds read load disproportionate to what the docs' "Limitations" section describes.
- **Recommendation:** Chunk the pending IDs into bounded batches (e.g., ≤ 1000 per query), or query by a run-scoped marker instead of an explicit ID list.

### F4 — Moderate: no integration test for the probe SQL against the real schema
- **Affected:** `tests/test_pg_latency_probe.py` (mock-only); `libs/load_test/pg_latency_probe.py`.
- **Problem:** The probe's JOIN (`product_observations → source_products → sources`) and `event_id IN` filter are validated only by asserting `"s.name = %s"` is present and `params[0] == source`. A wrong column name or broken JOIN would not be caught. This task touches the PostgreSQL boundary, but no `@pytest.mark.integration` test was added, and no integration run evidence was supplied (REVIEWER.md requirement).
- **Impact:** Regression risk in the substantive SQL; the remaining Milestone 13 tasks rely on this measurement.
- **Recommendation:** Add an `@pytest.mark.integration` test inserting a known `source`/`source_product`/`product_observations` row and asserting the probe finds the expected `event_id`. (I independently verified the current SQL against migrations 001–003 and it is correct.)

### F5 — Moderate: probe failure is silent
- **Affected:** `libs/load_test/runner.py` (`_start_pg_latency_monitor`); `libs/load_test/pg_latency_probe.py`.
- **Problem:** Both the periodic and final probes catch `Exception` and log only at `logger.debug`. If the DB is unreachable, or the query errors (e.g., the F3 limit), the `processing_latency` section is silently absent from the report — indistinguishable from "probing disabled". `to_report_dict()` also returns `None` when no samples, dropping even `total_produced`/`unresolved` feedback.
- **Impact:** Contradicts observability principles (PROJECT.md §10); an operator would not know latency was *not* measured.
- **Recommendation:** Surface an explicit marker in the report when probing was enabled but produced no samples, and/or log a warning on probe failure (with an error counter).

### F6 — Minor: test file placement inconsistent with existing load-test tests
- **Affected:** `tests/test_latency_collector.py`, `tests/test_pg_latency_probe.py`.
- **Problem:** These live at the `tests/` root, whereas all other load-test tests live under `tests/test_load_test/`.
- **Impact:** Minor organizational inconsistency (also present in TASK-112's `test_lag_collector.py`).
- **Recommendation:** Move to `tests/test_load_test/`.

### F7 — Minor: duplicated `_compute_percentiles` with a different key set
- **Affected:** `libs/load_test/latency_collector.py` (`_compute_percentiles`).
- **Problem:** This re-implements `MetricsCollector._compute_percentiles` but omits `p90`. The report's `processing_latency.latency_ms` therefore has a different shape from `results.latency_ms` (which includes `p90`).
- **Impact:** Minor shape inconsistency and duplicated code; no correctness issue.
- **Recommendation:** Reuse a single shared percentile helper, or accept the difference and document it.

### F8 — Minor: docs present unmeasured latency ranges as "Typical"
- **Affected:** `docs/processing-latency-measurement.md` ("Pipeline Stage Breakdown" table).
- **Problem:** The table lists concrete ranges (e.g., "Produce → Kafka ack 1–50 ms", "Warehouse → PostgreSQL 10–500 ms") with no label indicating they are estimates, not recorded results. The task's Performance Rule is "Do not invent benchmark numbers; record actual results."
- **Impact:** A reader could mistake these for measured values. The report itself contains only real measurements; this is documentation-only.
- **Recommendation:** Mark the ranges as illustrative/expected, or replace them with "measured via OTel traces (see …)" to avoid conflation.

---

## 6. Non-Defect Observations

- **Correct schema targeting:** The probe's SQL matches the actual migrated schema — `product_observations.event_id` (migration 002, NOT NULL/unique/indexed), `source_product_id`, `source_products.source_id`, and `sources.name`. The `postgresql+psycopg2://` scheme stripping is a nice robustness touch.
- **Sound read-only, non-interfering design:** The probe is a read-only `SELECT` that neither joins consumer groups nor mutates pipeline state, and it is disabled in `--dry-run` and when `pg_db_url` is empty — consistent with the TASK-112 probe pattern and the platform's read-only-agent posture.
- **Clean dependency injection:** `LatencyCollector`/`PgQueryFn` injection mirrors the existing `ProduceFn`/`LagQueryFn` pattern, keeping the collector unit-testable without a database — a good separation of concerns.
- **Correct thread-safety:** `LatencyCollector` mutates under a lock and computes `to_report_dict()` on a detached copy outside the lock; no lock held during sorting/percentile math.
- **Deduplication handled:** `record_pg_arrivals` ignores already-resolved IDs and IDs without a matching produce record, so duplicate probes cannot double-count a sample.
- **Honest imprecision documentation:** The "Measurement Imprecision" section (polling overcount, clock, warehouse batch cycle) correctly frames the method's limits and points to OpenTelemetry for precise per-stage breakdowns.
- **Backward compatible:** The `processing_latency` section is only present when samples exist, preserving the existing report contract for default runs.
- **Minor imprecision not documented:** the produce-side timestamp is recorded *after* `produce_fn` returns (post-ack), so it overcounts end-to-end latency by the produce-to-ack duration; this is negligible but could be noted alongside the polling overcount.

---

## 7. Verdict

**`APPROVED WITH NON-BLOCKING FINDINGS`**

The implementation correctly, cleanly, and deterministically implements end-to-end processing-latency measurement: produce-time stamping, a read-only PostgreSQL probe, `p50/p95/p99` distribution computation, and a JSON report section — without altering existing harness behavior, architecture, or dependencies. The pure logic is well tested, and lint/format/type checks pass. I independently verified the probe SQL against the current migrations and confirmed the collection/percentile logic via unit tests.

No Critical findings. The Moderate findings are non-blocking but should be addressed in follow-up, most importantly **redaction of `pg_db_url` from the report/stdout (F1)**, **coupling the probe source filter to `--source` (F2)**, **bounding the `IN (...)` query (F3)**, **an integration test for the probe SQL (F4)**, and **surface-probe-failure visibility (F5)** — before this measurement is relied upon by the downstream Milestone 13 tasks (TASK-114/115).
