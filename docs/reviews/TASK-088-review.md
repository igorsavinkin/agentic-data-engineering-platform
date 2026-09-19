# TASK-088 Review — Kafka Lag Dashboard

## 1. Review Header

- **Task ID:** TASK-088
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `31e33730b3cce1501cf1ec72b42f79069c913af6...0c5566437f6994e73d66d5bc63db1f1d67311a3c`
- **Reviewed HEAD:** `0c5566437f6994e73d66d5bc63db1f1d67311a3c` on `feature/TASK-088`
- **Commits reviewed:**
  - `0c55664` — `feat(TASK-088): Add Kafka & Processing dashboard`
- **Scope:** Version-controlled Grafana Kafka & Processing dashboard (`kafka-processing.json`) provisioned via Docker Compose volume mount and Helm ConfigMap, with dashboard-validation tests, a Helm assertion, and documentation.
- **Verdict:** `CHANGES REQUIRED`

## 2. Requirements Coverage

Requirements sourced from `ai/tasks/TASK-088-kafka-lag-dashboard.md`, with context from `ai/SPECIFICATION.md` (§20 Observability — "Kafka consumer lag should also be observable"), `ai/ROADMAP.md` (Milestone 10 — "Kafka lag dashboard" / required "Kafka/processing" dashboard), `ai/PROJECT.md` (§10 Observability), and `ai/AGENTS.md` (§7 Testing, §9 Observability, §10 Security). `docs/kafka-metrics.md` documents the established Kafka/lag semantics. No ADR applies (the sole ADR, ADR-001, is Kafka topic configuration).

The task objective has **two clauses**: (1) a Kafka/processing dashboard for consumer lag, throughput, errors and relevant latency; (2) a controlled backlog test demonstrating lag increase and recovery.

| Requirement | Status | Evidence |
|---|---|---|
| Kafka/processing dashboard (throughput, errors, latency) | ✅ Met | 12 panels cover consumer throughput, error rates, DLQ, invalid events, lag-query errors, processor throughput/latency/batch-size, ingestion rate/errors, and pipeline health. |
| Dashboard shows **consumer lag** | ⚠️ Partial | The only "lag" panel is `rate(kafka_events_consumed_total[5m]) - rate(kafka_events_processed_total[5m])` — a **rate-gap proxy**, not consumer lag (broker high-watermark − committed offset). The real `kafka_consumer_lag` gauge is designed in `docs/kafka-metrics.md` but is **not exported** by the Prometheus collector. See F1/F2. |
| **Document a controlled backlog test demonstrating lag increase and recovery** | ❌ Not met | No backlog test, no lag increase/recovery demonstration, and no accompanying documentation exist anywhere in the change set or repository. See F1. |
| Reuse established metrics (no new telemetry) | ✅ Met | Every referenced metric exists in `libs/observability/{kafka_metrics,processor_metrics}.py` and is exported by `libs/observability/prometheus_exporter.py`. No new metric families or instrumentation were introduced. |
| Low-cardinality labels; no secrets/payloads | ✅ Met | Labels limited to `service`; no secret or payload fields in the dashboard JSON. |
| Keep dashboards/provisioning version-controlled and reproducible | ✅ Met | Dashboard JSON and the Helm `grafana-dashboards` ConfigMap are committed; both provisioning paths auto-detect the file; datasource `uid: prometheus` matches. |
| Follow existing Kubernetes/Helm conventions | ✅ Met | Reuses the TASK-086 `grafana-dashboards` ConfigMap with `.Files.Glob "dashboards/*.json"`; no new template required. |
| No unrelated architecture changes / secrets / new dependencies | ✅ Met | Diff scoped to dashboard JSON + docs + tests; no production Python changes, no new dependencies, no secrets. |
| Acceptance behavior demonstrated (DoD) | ⚠️ Partial | Dashboard artifacts are reproducible and tested, but the backlog/lag-recovery acceptance behavior is absent. |

## 3. Git Diff Review

**Range:** `31e33730b3cce1501cf1ec72b42f79069c913af6...0c5566437f6994e73d66d5bc63db1f1d67311a3c` (1 commit, 5 files, +885/−0).

Files changed:

- `monitoring/grafana/dashboards/kafka-processing.json` (new, 311 lines) — dashboard JSON (Compose path).
- `helm/ai-data-platform/dashboards/kafka-processing.json` (new, 311 lines) — byte-identical copy for Helm `.Files.Glob`.
- `monitoring/README.md` (+21) — adds a "Kafka & Processing Dashboard (TASK-088)" section documenting the 12 panels.
- `tests/test_grafana_kafka_dashboard.py` (new, 237 lines) — 25 dashboard-structure/PromQL/datasource-UID/coverage tests.
- `tests/test_helm_chart.py` (+5) — extends the existing `grafana-dashboards` ConfigMap assertion to also assert `kafka-processing.json` and its `uid`.

**Scope correctness:** All changes belong to TASK-088. No unrelated task changes are mixed in.

**Unrelated/accidental changes:** None observed.

**Architectural changes:** None. Grafana remains an observability consumer; the event pipeline, data-lake, warehouse, and API boundaries are untouched. No new dependencies or container images.

**Dependency/config changes:** None beyond adding a third dashboard JSON to the already-established `.Files.Glob` ConfigMap.

**Debug/temp/dead code/secrets:** None committed. The full diff was read; no credentials, tokens, or payload data appear.

**Provisioning wiring (Compose vs Helm):** Correct and consistent.

- Compose: `docker-compose.yml` mounts `./monitoring/grafana/dashboards` → `/etc/grafana/provisioning/dashboards:ro`. The dashboard is present in that directory. ✅
- Helm: `grafana-dashboards` ConfigMap globs `dashboards/*.json` (now includes `kafka-processing.json`) and is mounted read-only at `/var/lib/grafana/dashboards`. The `test_helm_chart.py` assertion confirms inclusion (skipped locally, `helm` absent; confirmed by template inspection). ✅

## 4. Test and Verification Review

**Tests added/changed:**

- `tests/test_grafana_kafka_dashboard.py` (25 tests): validates the two dashboard copies exist and are identical; top-level structure (`schemaVersion` 39, `uid`, `title`, `tags`, `editable`); per-panel title/type/target/datasource presence and datasource **UID** equality; grid positions; that every PromQL metric name appears in `KNOWN_METRICS`; that no `histogram_quantile` query is used; and that coverage panels exist for throughput/lag/errors/latency/DLQ/ingestion.
- `tests/test_helm_chart.py` (extended): asserts the `grafana-dashboards` ConfigMap now also contains `kafka-processing.json` with `uid == "ai-data-platform-kafka"`.

**Independently verified (executed by reviewer):**

- `python -m pytest tests/test_grafana_kafka_dashboard.py -v` → **25 passed**.
- `python -m pytest tests/test_helm_chart.py::TestHelmTemplate::test_grafana_dashboards_configmap_contains_dashboard_json -v` → **1 skipped** (`helm` binary not available locally).
- `python -m ruff check tests/test_grafana_kafka_dashboard.py tests/test_helm_chart.py` → **All checks passed**.
- `python -m ruff format --check tests/test_grafana_kafka_dashboard.py tests/test_helm_chart.py` → **2 files already formatted**.

**Implementation evidence reviewed (not rerun):**

- The Helm `grafana-dashboards` ConfigMap inclusion is confirmed by inspection: the template uses `.Files.Glob "dashboards/*.json"` and `kafka-processing.json` is present in `helm/ai-data-platform/dashboards/`. The Helm assertion runs in CI (Helm installed there).

**Unverified:**

- Helm rendering/lint could not be executed locally (`helm` not installed); the new Helm assertion was reviewed manually.
- `mypy` was not rerun; the change set is JSON/docs/tests only (no production Python changes), so type-check impact is nil.

**Integration tests:** The task's *dashboard* artifacts are pure JSON/provisioning and do not require integration execution. However, the task's second objective — a **controlled backlog test demonstrating lag increase and recovery** — is by nature an integration test against a real Kafka broker, and it is **absent**. There is no evidence that `python -m pytest -m integration` was run for a lag/backlog scenario, because no such scenario was implemented. The `-m integration` obligation is therefore unmet for the missing deliverable (see F1).

**Metric-existence verification (independent of the test's allow-list):** The test's `KNOWN_METRICS` set is a hardcoded allow-list, not cross-referenced against the source. I independently confirmed every referenced metric is defined and exported: `kafka_events_{consumed,processed}_total`, `kafka_{consumer,processing}_errors_total`, `kafka_dead_letter_events_total`, `kafka_lag_errors_total`, `events_invalid_total`, `ingestion_{events,errors}_total` in `kafka_metrics.py`/`_KAFKA_COUNTERS`; and `processor_events_{processed,valid,invalid}_total`, `processor_batches_total`, `processor_batch_records_total`, `processor_processing_seconds` (summary) in `processor_metrics.py`/`_PROCESSOR_COUNTERS`/`_collect_processor_latency`. No dashboard query references a non-existent metric.

## 5. Findings

### F1 — High — Missing "controlled backlog test demonstrating lag increase and recovery"

- **File:** `ai/tasks/TASK-088-kafka-lag-dashboard.md` (objective), against the entire change set.
- **Problem:** The task objective's second clause — "Document a controlled backlog test demonstrating lag increase and recovery" — is entirely absent. No backlog test, no lag increase/recovery scenario, and no documentation of such a test exist in the diff or elsewhere in the repository. The Definition of Done ("Acceptance behavior is demonstrated") is therefore not satisfied.
- **Impact:** A primary deliverable of the task is missing. The dashboard exists, but the task's central acceptance behavior — proving that lag can be made to increase (backlog) and then recover — is not demonstrated. This is the core of a "Kafka **lag** dashboard" task.
- **Recommendation:** Add a deterministic integration test that drives a consumer backlog (e.g., pause/stop the consumer while producing) and asserts lag increases via `KafkaConsumer.sample_lag()`, then resumes and asserts lag decreases to near zero after commits; document the procedure (as TASK-039/050 did for replay/recovery). This will also surface the F2 gap, because a true lag test requires an exported lag metric.

### F2 — High — Dashboard does not display actual consumer lag

- **File:** `monitoring/grafana/dashboards/kafka-processing.json` (panel "Consumer Lag Indicator"); identical in `helm/ai-data-platform/dashboards/kafka-processing.json`.
- **Problem:** The only "lag" panel uses `rate(kafka_events_consumed_total[5m]) - rate(kafka_events_processed_total[5m])` — a difference of two throughput rates, i.e. a "consumed vs processed" gap. This is **not** consumer lag. Consumer lag is the broker high-watermark minus the group's committed offset, which the platform already computes in `KafkaConsumer.sample_lag()` (returning `ConsumerLag(topic, partition, lag)`). `docs/kafka-metrics.md` explicitly specifies that successful lag samples should be published as `kafka_consumer_lag` gauges, but the `PlatformMetricsCollector` in `libs/observability/prometheus_exporter.py` does **not** export any `kafka_consumer_lag` gauge (it was deferred to "the later observability milestone"). Consequently, the dashboard titled "Kafka Lag Dashboard" cannot surface real lag, and the rate-gap proxy is noisy (consumed includes invalid/DLQ/redeliveries while processed excludes DLQ, so the gap accumulates even without a real backlog).
- **Impact:** The primary objective ("dashboard for consumer lag") is not genuinely met. The panel is honestly labeled "…Indicator" and the README documents it as "consumed rate - processed rate (gap indicator)", so nothing is misrepresented, but the core signal the task is named for is absent from the dashboard.
- **Recommendation:** Either export the already-designed `kafka_consumer_lag` gauge (topic/partition labels, `None`→unavailable) as part of this task, or explicitly re-scope the task/roadmap to defer true lag visualization and keep only the proxy. A lag dashboard that shows no lag metric is incomplete.

### F3 — Moderate — Substantial panel duplication with `platform-overview.json` (TASK-086)

- **Files:** `monitoring/grafana/dashboards/kafka-processing.json` vs `monitoring/grafana/dashboards/platform-overview.json` (and their Helm copies).
- **Problem:** 8 of 12 panels duplicate the overview dashboard: "Consumer Throughput" ≈ "Service Event Rates"; "Kafka Error Rates" + "Dead Letter Queue Rate" + "Invalid Event Rate" ≈ "Error Rates"; "Processor Throughput" and "Processor Latency (avg)" (byte-identical query) duplicate the overview; "Ingestion Rate"/"Ingestion Errors" ≈ "Ingestion Events". Only four panels are genuinely new: "Consumer Lag Indicator", "Lag Query Errors", "Processor Batch Size (avg)", and "Processor Pipeline Health".
- **Impact:** Maintainability concern and diluted value — the ROADMAP requires a separate "Kafka/processing" dashboard, but a dedicated dashboard should go *deeper* on Kafka/processing-specific signals (actual lag, lag-query errors, batch size, DLQ detail) rather than restating overview panels. Duplicating overview panels doubles the maintenance surface and divergence risk.
- **Recommendation:** Keep the focused Kafka/processing panels and trim the redundant overview repeats, or clearly differentiate them (e.g., per-partition/per-topic lag once F2 is addressed). Non-blocking for acceptance but worth resolving in conjunction with F2.

### F4 — Minor — "references real metrics" test relies on a hardcoded allow-list

- **File:** `tests/test_grafana_kafka_dashboard.py` (the `KNOWN_METRICS` set and `test_all_metric_names_are_known`).
- **Problem:** The test's docstring claims queries "reference real metrics exposed by the platform", but `KNOWN_METRICS` is a hardcoded set, not derived from `libs/observability/{kafka_metrics,processor_metrics,prometheus_exporter}.py`. If a metric were renamed or removed from the exporter, this test would still pass as long as the dashboard and the allow-list agree, so it does not protect against metric drift from the source of truth.
- **Impact:** Test-completeness gap only. All referenced metrics currently *do* exist (independently confirmed), so no live defect. This mirrors the same weakness noted in the TASK-087 review.
- **Recommendation:** Derive `KNOWN_METRICS` from the exporter's counter/collector definitions, or add an assertion that the allow-list is a subset of the exported metric names.

## 6. Non-Defect Observations

- **N1 — Unusual commit attribution.** The commit author is `Workflow Test <workflow@example.invalid>`, unlike prior TASK commits authored by a developer identity. This may indicate the commit was produced/committed by an automated workflow rather than the implementation agent. Worth confirming the intended attribution before merge.
- **N2 — "Processor Pipeline Health" denominator differs from the data-quality pass rate.** The gauge uses `rate(processor_events_valid_total[5m]) / rate(processor_events_processed_total[5m]) * 100`, where `processed` includes valid + invalid + duplicate records. The TASK-087 data-quality dashboard uses `valid / (valid + invalid) * 100`. Both are defensible but measure slightly different things (validity-of-all-processed vs validity-excluding-duplicates). Not a defect; note for future dashboard consistency.
- **N3 — Byte-identical dashboard duplication across Compose and Helm** is the established repository convention (same as TASK-086/087), synchronized by `test_both_dashboards_are_identical`. Maintainability trade-off noted; discoverable via `monitoring/README.md`.
- **N4 — No bare gauge expressions exist in this dashboard** (every query is wrapped in `rate(...)`), so the `_extract_metric_names` regex weakness flagged in the TASK-087 review does **not** apply here — all metric names are correctly extracted and validated.
- **N5 — The `-m integration` requirement is unmet for the backlog deliverable** (see F1); it does not apply to the dashboard JSON itself, which contains no Kafka/persistence boundary code.

## 7. Verdict

**`CHANGES REQUIRED`**

The dashboard artifact itself is correctly scoped, follows repository conventions, passes its 25 validation tests, lints cleanly, is provisioned correctly on both Compose and Helm paths, references only real currently-exported Prometheus metrics (verified independently against `libs/observability`), and introduces no secrets, new dependencies, or architecture changes.

However, two High findings block acceptance:

1. **F1** — the task's explicit second deliverable, a controlled backlog test demonstrating lag increase and recovery, is entirely absent.
2. **F2** — the dashboard does not actually display consumer lag; the "Consumer Lag Indicator" is a rate-gap proxy, and the real `kafka_consumer_lag` gauge (already designed in `docs/kafka-metrics.md`) is not exported, so the "Kafka Lag Dashboard" surfaces no true lag signal.

Both are tightly coupled: the missing backlog test requires a real lag measurement, and real lag is not observable through the dashboard or the exporter today. Recommend addressing F1 and F2 together (export the `kafka_consumer_lag` gauge and add the backlog increase/recovery integration test + documentation) before acceptance. F3 and F4 are non-blocking but worth resolving in the same pass.
