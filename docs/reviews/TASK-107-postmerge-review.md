# TASK-107 Post-Merge Review — Recovery Documentation

## 1. Review Header

| Field | Value |
|-------|-------|
| Task ID | TASK-107 |
| Review date | 2026-09-24 |
| Reviewer | Qwen Code (independent review, no code modified) |
| Reviewed change set / Git range | `421574ad198f4a2d13b4ec6f3f94b5f9748d91a1..8e225a0291ef8990e3bea8d6de20da5f593ccba7` (single commit `8e225a0` "docs(TASK-107): add Milestone 12 failure recovery procedures", merged to `main` via PR #126, merge commit `70aff8b`) |
| Scope | Documentation-only change: one new file, `docs/milestone-12-recovery-procedures.md` (+294 lines) |
| Verdict | **CHANGES REQUIRED** |

The reviewed change set is exactly one commit that adds a single Markdown file. No application code, tests, configuration, or infrastructure were changed.

---

## 2. Requirements Coverage

Task objective (from `ai/tasks/TASK-107-recovery-documentation.md`): document all failure scenarios tested in Milestone 12 with clear recovery procedures, each following **Failure → Detection → Metric/log → Recovery → No silent data loss**, covering TASK-101 through TASK-106.

| Requirement | Status | Implementation evidence |
|-------------|--------|------------------------|
| Cover all TASK-101 … TASK-106 scenarios | ✅ Met | Six sections, one per task, each with the required lifecycle subsections |
| Failure → Detection → Metric/log → Recovery → No silent data loss structure | ✅ Met | Each scenario has `Failure`, `Detection`, `Metric/Log Evidence`, `Recovery`, `No Silent Data Loss` |
| Include reproduction steps and expected outcomes | ✅ Met | "Running the Tests" section lists the exact pytest commands; each scenario has a "Test verifies" line |
| Metric/log evidence is accurate | ❌ Partially met | Several metric/log names are invented (do not exist in the code); see Findings |
| Recovery steps are accurate per scenario | ❌ Partially met | TASK-102 describes Kafka-consumer recovery for a component that is actually a batch Parquet→PostgreSQL loader; see Findings |
| Understandable by an experienced engineer | ✅ Met (structurally) | Clear, well-organized, with tables and cross-cutting concerns |

The document is structurally complete and covers the required breadth, but the accuracy of the **metric/log signal names** and the **TASK-102 recovery mechanism** — the core value of a recovery runbook — has defects.

---

## 3. Git Diff Review

- **Scope correctness:** ✅ The commit contains only `docs/milestone-12-recovery-procedures.md` (+294 insertions). This is exactly the scope of TASK-107.
- **Unrelated changes:** ✅ None. No code, test, config, or infrastructure files touched.
- **Architectural changes:** ✅ None.
- **Accidental changes / debugging / temporary / dead code / secrets:** ✅ None. No secrets introduced.
- **Dependency/configuration changes:** ✅ None.
- **Test changes:** ✅ None (no tests modified or added).

The diff is clean and correctly scoped. All findings below are content-accuracy issues within the added documentation, not scope or hygiene issues.

---

## 4. Test and Verification Review

This is a documentation-only task; no tests were added or changed by TASK-107. The relevant verification is whether the document's claims match the implementation.

- **Tests examined:** the six referenced test files all exist and their paths are correct:
  - `tests/test_kafka_failure.py` (TASK-101) ✅
  - `tests/warehouse/test_postgresql_failure.py` (TASK-102) ✅
  - `tests/test_processor_crash.py` (TASK-103) ✅
  - `tests/test_duplicate_replay.py` (TASK-104) ✅
  - `tests/test_dlq.py` (TASK-105) ✅
  - `tests/test_observability/test_source_freshness_failure.py` (TASK-106) ✅
- **Claim verification method:** I independently inspected the implementation (metric enums, log statements, Prometheus exporter, warehouse loader, health assessment, agent tools) to cross-check every metric/log name and recovery step in the document. This is code inspection, not test execution.
- **Tests independently executed:** None. The integration tests require Docker Compose and are out of scope for verifying a documentation change; I did not rerun them.
- **`pyproject.toml` `addopts` claim:** ✅ Confirmed — `addopts = "-m 'not integration'"` is present, so the document's note that integration tests are deselected by default is correct.
- **TASK-106 "deterministic, no infrastructure" claim:** ✅ Confirmed — `test_source_freshness_failure.py` has no `pytestmark = pytest.mark.integration` and uses injected clocks.

Verification classification: **Implementation evidence reviewed** (source inspected directly); no test execution performed.

---

## 5. Findings

### Finding 1 — High: TASK-102 misrepresents the recovery mechanism as a Kafka consumer path

- **Affected file/line:** `docs/milestone-12-recovery-procedures.md`, lines ~59–98 (TASK-102 section).
- **Problem:** The document describes the warehouse loader as a Kafka consumer whose recovery is "Consumer restarts with the same `group.id`; Kafka re-delivers from the last committed offset", whose detection includes "`KafkaMetric.PROCESSED` counter does not increment" and "`kafka_processing_stopped`", and whose lossless guarantee is "Consumer offset is only committed after successful write".
  The actual implementation (`warehouse/loader/batch_loader.py`, exercised by `tests/warehouse/test_postgresql_failure.py`) is a **batch loader that reads Silver Parquet files** via `LakeReader` and upserts into PostgreSQL. It has no Kafka consumer, no group ID, no offset commit, and no `kafka_processing_stopped` path. On failure it raises `psycopg2.OperationalError`; recovery is **re-running the loader over the same Parquet files**, with `ON CONFLICT (event_id) DO NOTHING` providing idempotency.
- **Impact:** An engineer following this runbook for a real PostgreSQL outage would look for a Kafka consumer and a "committed offset" that do not exist in this component, and would miss the correct recovery action (re-run the loader over the same Silver Parquet inputs). This defeats the primary purpose of the document.
- **Recommendation:** Rewrite the TASK-102 `Detection`, `Metric/Log Evidence`, `Recovery`, and `No Silent Data Loss` sections to describe the actual batch loader: detection = `psycopg2.OperationalError` + `load_failed` / `batch_rolled_back` logs; recovery = restart PostgreSQL and re-run `load_from_parquet_files` over the same inputs; no-loss guarantee = `ON CONFLICT (event_id) DO NOTHING` + per-batch transactions.

### Finding 2 — High: Invented log message `warehouse_write_failed`

- **Affected file/line:** `docs/milestone-12-recovery-procedures.md`, lines 68 and 76.
- **Problem:** The document asserts the warehouse loader logs `warehouse_write_failed`. A repository-wide search finds this string **only in the documentation itself**. The loader's actual error log messages are `load_failed` (top-level load failure), `batch_failed`, and `batch_rolled_back` (`warehouse/loader/batch_loader.py`). The TASK-102 test explicitly asserts on `batch_rolled_back` or `load_failed`.
- **Impact:** The cited detection signal does not exist; operators would search logs for a token that never appears.
- **Recommendation:** Replace `warehouse_write_failed` with `load_failed` / `batch_rolled_back` (and note they carry `error` context, not "table name and record details").

### Finding 3 — Moderate: Invented metric name `kafka_produce_errors_total` (TASK-101)

- **Affected file/line:** `docs/milestone-12-recovery-procedures.md`, line 37.
- **Problem:** The document cites a producer-failure counter `kafka_produce_errors_total`. This name does not exist. The actual metric is `ingestion_errors_total` (`KafkaMetric.PRODUCER_ERRORS` in `libs/observability/kafka_metrics.py`), which is what `tests/test_kafka_failure.py` asserts via `KafkaMetric.PRODUCER_ERRORS.value`.
- **Impact:** Operator dashboards/alerts would reference a metric that is not exported.
- **Recommendation:** Replace with `ingestion_errors_total`.

### Finding 4 — Moderate: Invented metric name `kafka_processed_total` (TASK-103 and TASK-104)

- **Affected file/line:** `docs/milestone-12-recovery-procedures.md`, lines 114 and 150.
- **Problem:** The document cites `kafka_processed_total`. The actual metric is `kafka_events_processed_total` (`KafkaMetric.PROCESSED`). The TASK-104 line additionally misstates semantics: `kafka_events_processed_total` is a **consumer-level** counter incremented only for valid records that are successfully processed and committed — it is *not* "incremented per processed event (including duplicates that are deduplicated)". Duplicate accounting lives at the processor layer (`processor_events_duplicate_total` / `ProcessorMetric.EVENTS_DUPLICATE`).
- **Impact:** Wrong metric name plus a wrong description of what the counter counts.
- **Recommendation:** Use `kafka_events_processed_total` with the correct consumer-level description; move duplicate accounting to the processor metric (see Finding 5).

### Finding 5 — Moderate: Invented metric name `kafka_deduplicated_total` (TASK-104)

- **Affected file/line:** `docs/milestone-12-recovery-procedures.md`, line 151.
- **Problem:** The document cites `kafka_deduplicated_total` (hedged as "if applicable"). This name does not exist. The actual deduplication metric is `processor_events_duplicate_total` (`ProcessorMetric.EVENTS_DUPLICATE`), asserted by `tests/test_duplicate_replay.py` and exported by `libs/observability/processor_metrics.py` / `prometheus_exporter.py`.
- **Impact:** Same as Finding 4 — operators would reference a non-existent metric.
- **Recommendation:** Replace with `processor_events_duplicate_total`.

### Finding 6 — Minor: TASK-101 attributes exponential-backoff retry to producer publish failures

- **Affected file/line:** `docs/milestone-12-recovery-procedures.md`, lines ~31–35 (TASK-101 `Detection`).
- **Problem:** "Producer publish failures raise exceptions caught by the ingestion runner; retry with exponential backoff." In `services/ingestion/runner.py`, exponential backoff applies to `SourceFetchError` (adapter fetch), not to producer `PublishError`. `PublishError` is caught in `_publish_event` and only logged, with no retry.
- **Impact:** Minor overstatement of where retry/backoff applies.
- **Recommendation:** Clarify that exponential backoff is the ingestion runner's retry for transient *source fetch* failures, while producer delivery failures are logged and the event is dropped from that cycle (recovered via at-least-once replay).

### Finding 7 — Minor: TASK-101 cites `source_fetch_failure_total` with an unsupported causal link

- **Affected file/line:** `docs/milestone-12-recovery-procedures.md`, line ~39 (TASK-101 metric table).
- **Problem:** The table describes `source_fetch_failure_total` as "Incremented when adapter fetch fails due to Kafka unavailability." The metric (`SourceMetric.FETCH_FAILURE`) exists, but the TASK-101 Kafka-broker-failure test does not exercise source adapters at all, and the metric records source fetch failures, not Kafka availability.
- **Impact:** Spurious evidence in a broker-failure runbook; the causal link is speculative.
- **Recommendation:** Remove `source_fetch_failure_total` from the TASK-101 evidence table, or reword to remove the unsupported "due to Kafka unavailability" causality.

---

## 6. Non-Defect Observations

- The document correctly captures the architecture's **at-least-once** semantics and the idempotency boundaries (`event_id` deduplication at the processor, `ON CONFLICT (event_id) DO NOTHING` at the warehouse) — these match the implementation.
- TASK-105 is accurate: `DeserializationError`, `diagnostic_envelope()` fields (`error_type`, `raw_value_base64`, `topic`, `partition`, `offset`, `consumer_group`, `attempts`), `KafkaMetric.DEAD_LETTERED`, `KafkaMetric.INVALID`, and the `kafka_dead_letter_delivered` / `kafka_processing_retry` log messages all exist and are correctly described.
- TASK-106 is accurate: `SourceFreshness`, `SourceHealthTracker`, `source_freshness_age_seconds` gauge, `SourceDegradationState.STALE`, `FreshnessState.STALE`, `_derive_alerts()` → `source_stale` alert, and `PipelineStatusRepository` → `overall_status: stale` all check out.
- The "Running the Tests" commands are correct, and the note about `addopts = "-m 'not integration'"` deselecting integration tests is accurate and useful.
- TASK-103's `kafka_processing_stopped` (ERROR) and `KafkaMetric.PROCESSING_ERRORS` references are correct (only the `kafka_processed_total` name in the same table is wrong — Finding 4).

---

## 7. Verdict

**CHANGES REQUIRED**

The change is correctly scoped (documentation only, one file, no unrelated modifications) and structurally complete, and most scenario descriptions are accurate. However, the document contains two High findings that materially misrepresent the recovery behavior:

1. The TASK-102 section describes Kafka-consumer recovery (`group.id`, offset commits, `kafka_processing_stopped`) for a component that is actually a batch Parquet→PostgreSQL loader with no Kafka involvement, and
2. it cites a `warehouse_write_failed` log message that does not exist.

Additionally, four metric/log signal names are invented and do not exist in the codebase (`kafka_produce_errors_total`, `warehouse_write_failed`, `kafka_processed_total`, `kafka_deduplicated_total`). Because the task's explicit purpose is accurate, portfolio-grade recovery documentation, these inaccuracies must be corrected before the deliverable can be considered acceptable.

Recommended corrections are enumerated in Findings 1–7. No application code, tests, or configuration should be modified to resolve them — these are documentation-only fixes.
