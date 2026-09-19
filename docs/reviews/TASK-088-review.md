# TASK-088 Review — Kafka Lag Dashboard

## 1. Review Header

- **Task ID:** TASK-088
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `31e33730b3cce1501cf1ec72b42f79069c913af6...fc9da9277e0d1f30e03d56a43fa9828f241bf71f`
- **Reviewed HEAD (commit):** `fc9da9277e0d1f30e03d56a43fa9828f241bf71f` on `feature/TASK-088`
- **Commits reviewed:**
  - `0c55664` — `feat(TASK-088): Add Kafka & Processing dashboard`
  - `fc9da92` — `fix(TASK-088): Add real kafka_consumer_lag gauge and backlog test docs`
- **Scope:** Version-controlled Grafana Kafka & Processing dashboard (`kafka-processing.json`) provisioned via Docker Compose and Helm; a real `kafka_consumer_lag` gauge exported by the Prometheus collector and sampled periodically in the processor, raw-writer, and lake-writer consumer loops; backlog test documentation; and dashboard/Helm validation tests.
- **Verdict:** `CHANGES REQUIRED`

Sources of authority consulted: `ai/tasks/TASK-088-kafka-lag-dashboard.md`; `ai/PROJECT.md` §10; `ai/SPECIFICATION.md` §20 ("Kafka consumer lag should also be observable"); `ai/ROADMAP.md` Milestone 10 ("Kafka lag dashboard"); `ai/AGENTS.md` §7/§9/§10; `docs/kafka-metrics.md` (established lag and later-Prometheus-integration semantics). The sole ADR (`docs/adr/ADR-001-kafka-topic-configuration.md`) is not directly applicable to this observability change.

## 2. Requirements Coverage

The task objective has two clauses: (1) a Kafka/processing dashboard for consumer lag, throughput, errors, and relevant latency; (2) a controlled backlog test demonstrating lag increase and recovery.

| Requirement | Status | Evidence |
|---|---|---|
| Kafka/processing dashboard (throughput, errors, latency) | ✅ Met | 12 panels: consumer throughput, consumer lag, Kafka error rates, DLQ rate, invalid event rate, lag query errors, processor throughput/latency/batch-size, ingestion rate/errors, pipeline health. |
| Dashboard shows **real consumer lag** | ✅ Met | The "Consumer Lag" panel now uses the `kafka_consumer_lag` gauge (broker high-watermark − committed offset via `KafkaConsumer.sample_lag()`), replacing the prior rate-gap proxy. Exporter emission independently verified. |
| Document a controlled backlog test demonstrating lag increase and recovery | ⚠️ Partial | `monitoring/README.md` now documents a 5-step backlog/recovery procedure, but it references Compose services that do not exist (F3) and is a manual procedure with no evidence of execution. |
| Reuse established metrics / no new telemetry beyond lag gauge | ✅ Met | The only new metric is `kafka_consumer_lag`, which `docs/kafka-metrics.md` already specifies; all other referenced metrics pre-exist in `libs/observability`. |
| Low-cardinality labels; no secrets/payloads | ✅ Met | Labels bounded to `service`, `topic`, `partition`; no secret or payload fields anywhere in the change set. |
| Dashboards/provisioning version-controlled and reproducible | ✅ Met | Dashboard JSON committed on both Compose and Helm paths; datasource `uid: prometheus` matches; Helm `.Files.Glob "dashboards/*.json"` auto-includes the new file. |
| Follow Kubernetes/Helm conventions | ✅ Met | Reuses the TASK-086 `grafana-dashboards` ConfigMap; no new template or image. |
| No unrelated architecture changes / secrets / new dependencies | ✅ Met | No new dependencies; no secrets; event pipeline, data-lake, warehouse, and API boundaries untouched. |
| Instrumentation failure must not alter processing semantics | ✅ Met | `_sample_lag` wraps sampling in `try/except Exception` and never affects the consume/commit loop. |
| Deterministic tests / quality checks | ⚠️ Partial | Dashboard tests are strong, but the new lag-export runtime code has no dedicated tests (F4); ruff/format clean. |

## 3. Git Diff Review

**Range:** `31e33730b3cce1501cf1ec72b42f79069c913af6...fc9da9277e0d1f30e03d56a43fa9828f241bf71f` — 2 commits, 11 files, +1153/−0.

Files changed:

- `monitoring/grafana/dashboards/kafka-processing.json` (new, 311 lines) — dashboard JSON (Compose path).
- `helm/ai-data-platform/dashboards/kafka-processing.json` (new, 311 lines) — byte-identical copy for Helm.
- `libs/observability/kafka_metrics.py` (+20) — adds `LagSample` dataclass, `_lag_samples` storage, `update_lag()`, `lag_snapshot()`.
- `libs/observability/prometheus_exporter.py` (+18) — registers a lag snapshot source and adds `_collect_kafka_lag()` emitting the `kafka_consumer_lag` gauge.
- `services/processor/__main__.py`, `services/raw-writer/consumer.py`, `services/lake-writer/consumer.py` (+20 each) — add `_sample_lag()` and invoke it every 50 consumer-loop iterations.
- `monitoring/README.md` (+54) — documents the dashboard, the lag metric, and a backlog test procedure.
- `tests/test_grafana_kafka_dashboard.py` (new, 238 lines) — 25 dashboard-structure/PromQL/coverage tests.
- `tests/test_helm_chart.py` (+5) — extends the `grafana-dashboards` ConfigMap assertion to `kafka-processing.json`.
- `docs/reviews/TASK-088-review.md` — a prior review artifact committed within the change set (see N2).

**Scope correctness:** All changes belong to TASK-088. No unrelated task changes are mixed in.

**Unrelated/accidental changes:** None observed (excluding the committed review artifact noted in N2).

**Architectural changes:** None. Grafana remains an observability consumer; the pipeline/data-lake/warehouse/API boundaries are unchanged. The lag sampling runs on the consumer thread and does not alter offset-commit or at-least-once semantics.

**Dependency/config changes:** None. No new Python dependency, no new container image, no Compose/Helm config change beyond adding the third dashboard JSON to the existing glob ConfigMap.

**Debug/temp/dead code/secrets:** None committed. Full diff read; no credentials, tokens, or payload data appear.

## 4. Test and Verification Review

**Tests added/changed:**

- `tests/test_grafana_kafka_dashboard.py` (25 tests): validates both dashboard copies exist and are identical; top-level structure; per-panel title/type/target/datasource/UID/gridPos; that every PromQL metric name is in `KNOWN_METRICS`; no `histogram_quantile`; and coverage of throughput/lag/errors/latency/DLQ/ingestion.
- `tests/test_helm_chart.py` (extended): asserts the `grafana-dashboards` ConfigMap now contains `kafka-processing.json` with `uid == "ai-data-platform-kafka"`.

**Independently verified (executed by reviewer):**

- `python -m pytest tests/test_grafana_kafka_dashboard.py -q` → **25 passed**.
- `python -m pytest tests/test_observability/test_prometheus_exporter.py tests/test_kafka_metrics.py -q` → **39 passed, 1 deselected** (the `-m integration` lag-follows-commit test).
- `python -m pytest tests/test_helm_chart.py -q` → **23 passed, 28 skipped** (`helm` binary absent locally; the ConfigMap assertion for `kafka-processing.json` is among the skipped tests).
- `python -m ruff check <changed .py files>` → **All checks passed**.
- `python -m ruff format --check <changed .py files>` → **6 files already formatted**.
- `kafka_consumer_lag` gauge emission → independently verified via `generate_latest`; produces `kafka_consumer_lag{partition="0",service="processor",topic="products.raw.v1"} 42.0`.
- LAG_ERRORS double-count → independently verified: a single failed `sample_lag` results in `kafka_lag_errors_total == 2` (see F1).

**Implementation evidence reviewed (not rerun):**

- Helm `grafana-dashboards` ConfigMap inclusion of `kafka-processing.json` is confirmed by template inspection (`.Files.Glob "dashboards/*.json"`, file present in `helm/ai-data-platform/dashboards/`); the Helm assertion itself is skipped locally due to absent `helm`.

**Unverified:**

- `python -m pytest -m integration` was **not** run and there is **no** automated integration test exercising the new `kafka_consumer_lag` export path end-to-end. The task adds Kafka-bound runtime changes (lag sampling in three consumer loops), so this is a relevant gap under `ai/AGENTS.md` §7 and the reviewer's integration obligation. The only lag integration test (`test_real_counters_and_lag_follow_commit`) predates this change and covers `KafkaConsumer.sample_lag()`, not the new gauge or `_sample_lag` wrapper.
- The documented backlog test is a manual procedure; there is no evidence it was executed or that its outcome (lag increase → recovery) was observed.

**Metric-existence verification (independent of the test's allow-list):** Every dashboard-referenced metric is defined and exported. `kafka_consumer_lag` is emitted by `_collect_kafka_lag()`; all other `kafka_*`/`events_invalid_total`/`ingestion_*` names are in `_KAFKA_COUNTERS`; all `processor_*` names are in `_PROCESSOR_COUNTERS`/the latency summary. No dashboard query references a non-existent metric.

## 5. Findings

### F1 — Moderate — `kafka_lag_errors_total` is double-counted on every failed lag sample

- **Files:** `services/processor/__main__.py`, `services/raw-writer/consumer.py`, `services/lake-writer/consumer.py` (`_sample_lag`), interacting with `libs/common/kafka_consumer.py::sample_lag()`.
- **Problem:** `KafkaConsumer.sample_lag()` already increments `KafkaMetric.LAG_ERRORS` and re-raises on `KafkaException`/`TimeoutError`, per the contract in `docs/kafka-metrics.md`. The new `_sample_lag()` wrapper catches that exception in `except Exception` and increments `LAG_ERRORS` **again**. Independently reproduced: a single failed sample leaves `kafka_lag_errors_total == 2`.
- **Impact:** The "Lag Query Errors" stat panel and any alert based on it will over-report by 2×. Observability accuracy is degraded for the exact failure mode the metric is meant to surface.
- **Recommendation:** Do not re-increment in `_sample_lag` for failures `sample_lag()` has already counted; let `sample_lag()` own the counter (it is the source of truth for lag-query failure). If the wrapper must also count `RuntimeError`/`ValueError` paths, narrow the catch accordingly.

### F2 — Moderate — No sample-age tracking; stale lag values persist during sampling outage

- **Files:** `libs/observability/kafka_metrics.py` (`LagSample` has no timestamp; `update_lag` only replaces on success) and the three `_sample_lag` wrappers.
- **Problem:** `docs/kafka-metrics.md` ("Later Prometheus integration") specifies: "hand a timestamped copy to the collector. Track sample age and omit expired samples." The implementation stores only `(topic, partition, lag)` and, on a failed sample, leaves the previous values in place. If the broker becomes unreachable (or sampling keeps failing), the `kafka_consumer_lag` gauge continues serving the last successful — potentially long-stale — values indefinitely, misrepresenting a stuck/starving consumer as healthy with low lag.
- **Impact:** A lag dashboard that reports stale values undermines its own purpose (detecting backlog). Contradicts the documented freshness semantics and the "represent unavailable, never reuse stale as current zero" principle.
- **Recommendation:** Add a timestamp to `LagSample` and expire/omit samples older than a threshold in `_collect_kafka_lag()`, or clear stored samples on sampling failure. Align with the sample-age guidance already in `docs/kafka-metrics.md`.

### F3 — Moderate — Backlog test procedure references Docker Compose services that do not exist

- **File:** `monitoring/README.md` ("Backlog Test Procedure").
- **Problem:** The procedure instructs `docker compose stop processor` / `docker compose start processor` and "let the ingestion service run", but `docker-compose.yml` (the only Compose file) defines **no** `processor`, `ingestion`, `raw-writer`, or `lake-writer` service. Local Compose runs only infrastructure (Kafka, MinIO, PostgreSQL, Airflow, Prometheus, Grafana); application services run in Kubernetes (Helm) or via `python -m services.*` (see `docs/local-development.md`).
- **Impact:** The task's explicit second deliverable — a *controlled backlog test demonstrating lag increase and recovery* — is documented but not reproducible as written. The "demonstrating" acceptance behavior cannot actually be performed from these instructions.
- **Recommendation:** Rewrite the procedure against the actual run mechanism (e.g., `kubectl scale deployment processor --replicas=0` in the kind cluster, or stopping a locally-run `python -m services.processor` process), and correct the prerequisites to match. Consider also capturing the expected observed lag increase/recovery.

### F4 — Moderate — New lag-export runtime code has no dedicated tests

- **Files:** `libs/observability/kafka_metrics.py` (`LagSample`, `update_lag`, `lag_snapshot`), `libs/observability/prometheus_exporter.py` (`_collect_kafka_lag`), and the three `_sample_lag` wrappers.
- **Problem:** The only test change is adding `kafka_consumer_lag` to the dashboard test's hardcoded `KNOWN_METRICS` allow-list. No unit test exercises the gauge collector, `LagSample` storage/replacement semantics, `None` omission, or the `_sample_lag` success/failure paths (which is exactly where F1 and F2 live). The exporter test suite (`tests/test_observability/test_prometheus_exporter.py`) was not extended.
- **Impact:** The new gauge path is effectively untested; F1 and F2 were not caught. This falls short of `ai/AGENTS.md` §7 and the task's "add deterministic validation/tests where applicable".
- **Recommendation:** Add unit tests for `_collect_kafka_lag` (labels, value, `None` omission, partition replacement), `update_lag`/`lag_snapshot`, and `_sample_lag` (success and failure, including asserting the exact `LAG_ERRORS` count).

### F5 — Minor — "Consumer Lag" panel legend is ambiguous across services

- **File:** `monitoring/grafana/dashboards/kafka-processing.json` (panel "Consumer Lag"; identical Helm copy).
- **Problem:** `legendFormat` is `{{ topic }}-{{ partition }}`, but the gauge also carries a `service` label. Since `raw-writer` and `processor` both consume `products.raw.v1` (different consumer groups), two distinct series render with the identical legend `products.raw.v1-0`.
- **Impact:** On the dashboard's primary panel, operators cannot distinguish which consumer is lagging. No functional defect; clarity-only.
- **Recommendation:** Include `service` in the legend (e.g. `{{ service }} {{ topic }}-{{ partition }}`).

### F6 — Minor — `KNOWN_METRICS` allow-list does not guard against exporter drift

- **File:** `tests/test_grafana_kafka_dashboard.py` (`KNOWN_METRICS`, `test_all_metric_names_are_known`).
- **Problem:** The test validates dashboard queries against a hardcoded set rather than the exporter's actual counter/collector definitions. If a metric were renamed or removed from the exporter, the test would still pass as long as the dashboard and the allow-list agree. This mirrors the same weakness noted in the TASK-087 review.
- **Impact:** Test-completeness gap only; all referenced metrics currently exist (independently confirmed).
- **Recommendation:** Derive `KNOWN_METRICS` from the exporter's `_KAFKA_COUNTERS`/`_PROCESSOR_COUNTERS` and the lag gauge name, or add an assertion that the allow-list is a subset of the exported metric names.

## 6. Non-Defect Observations

- **N1 — Unusual commit attribution.** Both commits are authored by `Workflow Test <workflow@example.invalid>`, unlike prior TASK commits from a developer identity. May indicate automated-workflow commits; worth confirming intended attribution before merge.
- **N2 — A review artifact is committed inside the reviewed change set.** `docs/reviews/TASK-088-review.md` (a review of `0c55664` with verdict `CHANGES REQUIRED`) is itself modified by `fc9da92` and appears in the diff. Review reports are normally authored after the implementation, not committed alongside it. This is a process/scope observation, not a code defect; the present report supersedes it.
- **N3 — Panel duplication with `platform-overview.json` persists.** 8 of 12 panels overlap the TASK-086 overview dashboard (throughput, error rates, DLQ, invalid rate, processor throughput/latency, ingestion rate/errors). Only lag, lag-query errors, batch size, and pipeline health are genuinely new. Maintainability consideration, not a defect.
- **N4 — "Processor Pipeline Health" denominator differs from the data-quality pass rate.** It uses `valid / processed * 100` (processed includes valid + invalid + duplicate), whereas the TASK-087 dashboard uses `valid / (valid + invalid)`. Both defensible; measures slightly different things. Noted for cross-dashboard consistency.
- **N5 — Lag sampling cadence is within documented constraints.** Sampling every 50 iterations blocks the consumer thread for up to `timeout=2.0`s; bounded and well inside `max.poll.interval.ms` (300s), consistent with `docs/kafka-metrics.md`'s "schedule sparingly". No action required.
- **N6 — None-as-unavailable is handled correctly.** `_sample_lag` filters `r.lag is not None` before storing, matching the "represent `None` as unavailable" guidance; and `update_lag` replaces the whole list, so revoked partitions are dropped on a successful sample.

## 7. Verdict

**`CHANGES REQUIRED`**

The primary deliverable is now genuinely in place: the dashboard exists, is correctly provisioned on both Compose and Helm paths, references only real exported metrics, and — after the fix commit — surfaces **actual** consumer lag through a properly-exported `kafka_consumer_lag` gauge (emission independently verified). Dashboard tests pass (25/25), exporter/consumer unit tests pass (39, 1 integration deselected), and ruff/format are clean. No secrets, new dependencies, or architecture changes were introduced.

However, the following should be resolved before acceptance:

- **F1** — `kafka_lag_errors_total` is double-counted on every failed lag sample (independently reproduced: 1 failure → count 2), corrupting the lag-error signal.
- **F2** — no sample-age tracking means the lag gauge can serve stale values during a sampling outage, contradicting `docs/kafka-metrics.md` and the dashboard's purpose.
- **F3** — the task's second deliverable (a *controlled backlog test*) is documented but not reproducible as written, because it references Docker Compose services that do not exist.
- **F4** — the new lag-export runtime code is untested, which is precisely why F1/F2 slipped through.

F5 and F6 are minor and non-blocking. F1–F4 are Moderate in severity — none are Critical to the core event pipeline (at-least-once/idempotency semantics are untouched, and instrumentation failure is correctly contained), but together they mean the task's observability accuracy and its "demonstrated backlog test" acceptance criteria are not yet met.
