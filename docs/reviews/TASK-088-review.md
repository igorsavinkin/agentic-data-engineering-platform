# TASK-088 Review — Kafka Lag Dashboard

## 1. Review Header

- **Task ID:** TASK-088
- **Review date:** 2026-09-20
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `31e33730b3cce1501cf1ec72b42f79069c913af6...3d66321dac3f40452f991b0e60a9d81f3e557009`
- **Reviewed HEAD (commit):** `3d66321dac3f40452f991b0e60a9d81f3e557009` on `feature/TASK-088`
- **Commits reviewed:**
  - `0c55664` — `feat(TASK-088): Add Kafka & Processing dashboard`
  - `fc9da92` — `fix(TASK-088): Add real kafka_consumer_lag gauge and backlog test docs`
  - `3d66321` — `fix(TASK-088): Address round 2 review findings`
- **Scope:** Version-controlled Grafana "Kafka & Processing" dashboard (`kafka-processing.json`) provisioned via Docker Compose and Helm; a real `kafka_consumer_lag` gauge exported by the Prometheus collector; periodic lag sampling in the processor, raw-writer, and lake-writer consumer loops; staleness tracking for lag samples; a documented controlled backlog test; and dashboard/Helm/lag unit tests.
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

Sources of authority consulted: `ai/tasks/TASK-088-kafka-lag-dashboard.md`; `ai/PROJECT.md` §10 (observability); `ai/SPECIFICATION.md` §20 ("Kafka consumer lag should also be observable"); `ai/ROADMAP.md` Milestone 10 ("Kafka lag dashboard"); `ai/AGENTS.md` §7/§9/§10; `docs/kafka-metrics.md` (established lag semantics and "Later Prometheus integration" guidance). The sole ADR (`docs/adr/ADR-001-kafka-topic-configuration.md`) is not directly applicable to this observability change.

This is the final review of the complete three-commit task range. Two earlier review artifacts (round 1 and round 2, both authored by "Qwen Code") are committed inside the change set; the round-2 review (`fc9da92`) returned `CHANGES REQUIRED` with findings F1–F6. Commit `3d66321` was written specifically to address F1–F5. This report re-assesses those findings against `3d66321` and supersedes the earlier artifacts.

## 2. Requirements Coverage

The task objective has two clauses: (1) a Kafka/processing dashboard for consumer lag, throughput, errors, and relevant latency; (2) a controlled backlog test demonstrating lag increase and recovery.

| Requirement | Status | Evidence |
|---|---|---|
| Kafka/processing dashboard (throughput, errors, latency) | ✅ Met | 12 panels: consumer throughput, consumer lag, Kafka error rates, DLQ rate, invalid-event rate, lag-query errors, processor throughput/latency/batch-size, ingestion rate/errors, pipeline health. |
| Dashboard shows **real consumer lag** | ✅ Met | "Consumer Lag" panel uses the `kafka_consumer_lag` gauge (broker high-watermark − committed offset via `KafkaConsumer.sample_lag()`), not a rate-gap proxy. Gauge is emitted by `_collect_kafka_lag()`. |
| Document a controlled backlog test demonstrating lag increase and recovery | ✅ Met | `monitoring/README.md` now documents a 6-step procedure against the actual run mechanism (`python -m services.ingestion` / `python -m services.processor` for local, `kubectl scale deployment processor` for Kubernetes), with an expected-outcome statement. F3 resolved. |
| Reuse established metrics / no new telemetry beyond lag gauge | ✅ Met | The only new metric is `kafka_consumer_lag`, already specified in `docs/kafka-metrics.md`; all other referenced metrics pre-exist in `libs/observability`. |
| Low-cardinality labels; no secrets/payloads | ✅ Met | Lag gauge labels bounded to `service`, `topic`, `partition`; no secret or payload fields anywhere in the change set. |
| Dashboards/provisioning version-controlled and reproducible | ✅ Met | Dashboard JSON committed on both Compose and Helm paths (byte-identical, verified by test); datasource `uid: prometheus` matches; Helm `.Files.Glob "dashboards/*.json"` auto-includes the new file. |
| Follow Kubernetes/Helm conventions | ✅ Met | Reuses the TASK-086 `grafana-dashboards` ConfigMap; no new template or image. |
| No unrelated architecture changes / secrets / new dependencies | ✅ Met | No new Python dependency, no secrets, no container image; pipeline/data-lake/warehouse/API boundaries untouched. |
| Instrumentation failure must not alter processing semantics | ✅ Met | `_sample_lag` wraps sampling in `try/except Exception` and never affects the consume/commit loop; at-least-once/idempotency semantics unchanged. |
| Deterministic tests / quality checks | ✅ Met | Dashboard, Helm, and lag-storage unit tests added and passing; ruff/format/mypy clean (details in §4). |

## 3. Git Diff Review

**Range:** `31e33730b3cce1501cf1ec72b42f79069c913af6...3d66321dac3f40452f991b0e60a9d81f3e557009` — 3 commits, 12 files, +1300/−0.

Files changed:

- `monitoring/grafana/dashboards/kafka-processing.json` (new, 311 lines) — dashboard JSON (Compose path).
- `helm/ai-data-platform/dashboards/kafka-processing.json` (new, 311 lines) — byte-identical copy for Helm.
- `libs/observability/kafka_metrics.py` — adds `LagSample` dataclass with `sampled_at`/`age_seconds()`, `_lag_samples` storage, `update_lag()`, `lag_snapshot()`, `clear_stale_lag()`.
- `libs/observability/prometheus_exporter.py` — registers a lag snapshot source and adds `_collect_kafka_lag()` emitting the `kafka_consumer_lag` gauge.
- `services/processor/__main__.py`, `services/raw-writer/consumer.py`, `services/lake-writer/consumer.py` — add `_sample_lag()` (sample → `update_lag` → `clear_stale_lag`) invoked every 50 consumer-loop iterations.
- `monitoring/README.md` — documents the dashboard, the lag metric, and the corrected backlog test procedure.
- `tests/test_grafana_kafka_dashboard.py` (new, 238 lines) — dashboard-structure/PromQL/coverage tests.
- `tests/test_kafka_metrics_lag.py` (new, 101 lines) — `LagSample`/`update_lag`/`lag_snapshot`/`clear_stale_lag` unit tests.
- `tests/test_helm_chart.py` (+5) — extends the `grafana-dashboards` ConfigMap assertion to `kafka-processing.json`.
- `docs/reviews/TASK-088-review.md` — prior review artifacts committed within the change set (see N2).

**Scope correctness:** All changes belong to TASK-088. No unrelated task changes are mixed in.

**Unrelated/accidental changes:** None observed (excluding the committed review artifacts noted in N2).

**Architectural changes:** None. Grafana remains an observability consumer; pipeline/data-lake/warehouse/API boundaries are unchanged. Lag sampling runs on the consumer thread and does not alter offset-commit or at-least-once semantics.

**Dependency/config changes:** None. No new Python dependency, no new container image, no Compose/Helm config change beyond adding the third dashboard JSON to the existing glob ConfigMap.

**Debug/temp/dead code/secrets:** None committed. Full diff read; no credentials, tokens, or payload data appear.

## 4. Test and Verification Review

**Tests added/changed:**

- `tests/test_kafka_metrics_lag.py` (10 tests): `LagSample` creation/age/custom-timestamp, empty initial snapshot, `update_lag` (append and replace semantics), snapshot detachment, `clear_stale_lag` (removes old, keeps fresh, empty-list).
- `tests/test_grafana_kafka_dashboard.py` (26 tests): both dashboard copies exist and are identical; top-level structure; per-panel title/type/target/datasource/UID/gridPos; PromQL metric names against a `KNOWN_METRICS` allow-list; no `histogram_quantile`; coverage of throughput/lag/errors/latency/DLQ/ingestion.
- `tests/test_helm_chart.py` (extended): asserts the `grafana-dashboards` ConfigMap contains `kafka-processing.json` with `uid == "ai-data-platform-kafka"`.

**Independently verified (executed by reviewer):**

- `python -m pytest tests/test_kafka_metrics_lag.py tests/test_grafana_kafka_dashboard.py tests/test_kafka_metrics.py tests/test_observability/test_prometheus_exporter.py -q` → **74 passed, 1 deselected** (the `-m integration` lag-follows-commit test).
- `python -m pytest tests/test_helm_chart.py -q` → **23 passed, 28 skipped** (`helm` binary absent locally; the `grafana-dashboards` ConfigMap assertion for `kafka-processing.json` is among the skipped tests, but the ConfigMap inclusion is confirmed by template inspection of `.Files.Glob "dashboards/*.json"`).
- `python -m ruff check <8 changed .py files>` → **All checks passed**.
- `python -m ruff format --check <8 changed .py files>` → **8 files already formatted**.
- `python -m mypy libs/observability/kafka_metrics.py libs/observability/prometheus_exporter.py tests/test_kafka_metrics_lag.py tests/test_grafana_kafka_dashboard.py` → **Success: no issues found in 4 source files**.

**Round-2 finding resolution (re-verified against `3d66321`):**

- **F1 (double-count of `kafka_lag_errors_total`) — RESOLVED.** `_sample_lag` no longer increments `LAG_ERRORS`; `KafkaConsumer.sample_lag()` owns the counter (increments on `KafkaException`/`TimeoutError` only). The `KafkaMetric` import was removed from all three service files.
- **F2 (no sample-age tracking) — RESOLVED.** `LagSample.sampled_at` (monotonic, auto-populated), `age_seconds()`, and `clear_stale_lag(max_age_seconds=60.0)` are implemented and unit-tested.
- **F3 (backlog procedure referenced non-existent Compose services) — RESOLVED.** `docker-compose.yml` contains no `processor`/`raw-writer`/`lake-writer`/`ingestion` service; the README now references `python -m services.ingestion` / `python -m services.processor` (both valid entry points; `services.ingestion` runs with Fake Store alone, no API key required) and `kubectl scale deployment processor --replicas=0` for Kubernetes.
- **F4 (new lag runtime code untested) — PARTIALLY RESOLVED.** The storage layer (`LagSample`, `update_lag`, `lag_snapshot`, `clear_stale_lag`) is now unit-tested, but `_collect_kafka_lag()` (gauge emission) and the three `_sample_lag()` wrappers still have no dedicated tests (see F-A).
- **F5 (Consumer Lag legend ambiguous) — RESOLVED.** Legend is now `{{ service }} / {{ topic }}-{{ partition }}`.
- **F6 (`KNOWN_METRICS` allow-list) — NOT ADDRESSED** (was Minor/non-blocking); see F-C.

**Implementation evidence reviewed (not rerun):**

- Helm `grafana-dashboards` ConfigMap inclusion of `kafka-processing.json` is confirmed by template inspection (`.Files.Glob "dashboards/*.json"`, file present in `helm/ai-data-platform/dashboards/`); the runtime Helm assertion is skipped locally due to absent `helm`.

**Unverified:**

- **`python -m pytest -m integration` for Kafka was not run**, and no implementation evidence of such a run exists in the change set. CI (`.github/workflows/ci.yml`) runs `pytest` (unit, `-m 'not integration'`) and only warehouse-migration integration tests (`tests/warehouse/test_migrations.py`); the Kafka integration tests are not exercised in CI. The task adds Kafka-bound runtime changes (lag sampling in three consumer loops plus a new gauge), so the end-to-end lag-export path (broker → `sample_lag()` → `update_lag()` → scrape → `kafka_consumer_lag`) is not integration-verified. The only lag integration test (`test_real_counters_and_lag_follow_commit`) predates this task and covers `KafkaConsumer.sample_lag()`, not the new gauge or `_sample_lag()` wrapper.
- The documented backlog test is a manual procedure; there is no evidence it was executed or that its outcome (lag increase → recovery) was observed.

## 5. Findings

### F-A — Minor — `_collect_kafka_lag()` and `_sample_lag()` wrappers still lack dedicated tests (F4 residual)

- **Files:** `libs/observability/prometheus_exporter.py` (`_collect_kafka_lag`), `services/processor/__main__.py`, `services/raw-writer/consumer.py`, `services/lake-writer/consumer.py` (`_sample_lag`).
- **Problem:** Commit `3d66321` added unit tests for the storage layer (`LagSample`/`update_lag`/`lag_snapshot`/`clear_stale_lag`) but not for the gauge-emission method or the three `_sample_lag` wrappers. `_collect_kafka_lag` follows the same pattern as the already-tested `_collect_kafka_counters`, and `_sample_lag` composes already-tested primitives, so the residual risk is low — but the gauge's label/value/`None`-omission behavior and the wrapper's success/failure paths are not regression-protected.
- **Impact:** A future change to the gauge labels or the wrapper's `except` clause (the exact site of the F1 double-count bug) would not be caught by tests.
- **Recommendation:** Add a unit test for `_collect_kafka_lag` (service/topic/partition labels, value, `None` omission) and a small test for `_sample_lag` success/failure using a mock `KafkaConsumer` (asserting `update_lag` is called with `None`-filtered samples on success and `clear_stale_lag` is called on failure, with the correct `LAG_ERRORS` count).

### F-B — Minor — `_sample_lag`'s broad `except Exception` leaves `RuntimeError`/`ValueError` uncounted

- **Files:** `services/processor/__main__.py`, `services/raw-writer/consumer.py`, `services/lake-writer/consumer.py`.
- **Problem:** `KafkaConsumer.sample_lag()` increments `kafka_lag_errors_total` only for `KafkaException` and `TimeoutError`; it raises `RuntimeError` (closed consumer) and `ValueError` (invalid timeout) without counting. The wrapper's `except Exception` now correctly avoids double-counting, but it also swallows these two paths at debug level with no metric.
- **Impact:** Negligible in practice — the timeout is hardcoded to a valid `2.0` and the consumer is closed only during shutdown — but a lag-query failure of those types would be invisible to the "Lag Query Errors" panel.
- **Recommendation:** No change required for correctness; optionally narrow the catch to `(KafkaException, TimeoutError)` and let `RuntimeError`/`ValueError` propagate, or explicitly count them if they are meant to be observable. Document the intent either way.

### F-C — Minor — `KNOWN_METRICS` allow-list does not guard against exporter drift (F6, unchanged)

- **File:** `tests/test_grafana_kafka_dashboard.py` (`KNOWN_METRICS`, `test_all_metric_names_are_known`).
- **Problem:** The test validates dashboard queries against a hardcoded set rather than the exporter's actual counter/collector definitions. If a metric were renamed or removed from the exporter, the test would still pass as long as the dashboard and the allow-list agree. This mirrors the same weakness noted in the TASK-087 review.
- **Impact:** Test-completeness gap only; all referenced metrics currently exist (independently confirmed against `_KAFKA_COUNTERS`/`_PROCESSOR_COUNTERS` and the `kafka_consumer_lag` gauge).
- **Recommendation:** Derive `KNOWN_METRICS` from the exporter's counter lists and gauge name, or add an assertion that the allow-list is a subset of the exported metric names.

## 6. Non-Defect Observations

- **N1 — Unusual commit attribution.** All three commits are authored by `Workflow Test <workflow@example.invalid>`, unlike prior TASK commits from a developer identity. May indicate automated-workflow commits; worth confirming intended attribution before merge.
- **N2 — Review artifacts are committed inside the reviewed change set.** `docs/reviews/TASK-088-review.md` (round-1 and round-2 reviews) is itself modified by `fc9da92` and `3d66321` and appears in the diff. Review reports are normally authored after the implementation, not committed alongside it. Process/scope observation only; the present report supersedes them.
- **N3 — Panel duplication with `platform-overview.json` persists.** 8 of 12 panels overlap the TASK-086 overview dashboard (throughput, error rates, DLQ, invalid rate, processor throughput/latency, ingestion rate/errors). Only lag, lag-query errors, batch size, and pipeline health are genuinely new. Maintainability consideration, not a defect.
- **N4 — "Processor Pipeline Health" denominator differs from the data-quality pass rate.** It uses `valid / processed * 100` (processed includes valid + invalid + duplicate), whereas the TASK-087 dashboard uses `valid / (valid + invalid)`. Both defensible; measures slightly different things. Noted for cross-dashboard consistency.
- **N5 — Lag sampling cadence is within documented constraints.** Sampling every 50 iterations blocks the consumer thread for up to `timeout=2.0`s; bounded and well inside `max.poll.interval.ms` (300s), consistent with `docs/kafka-metrics.md`'s "schedule sparingly". No action required.
- **N6 — None-as-unavailable is handled correctly.** `_sample_lag` filters `r.lag is not None` before storing, matching the "represent `None` as unavailable" guidance; `update_lag` replaces the whole list, so revoked partitions are dropped on a successful sample.
- **N7 — Effective staleness window can exceed the 60s threshold.** `clear_stale_lag(60.0)` runs in the consumer loop, and when idle the loop samples roughly every ~55s (poll timeout 1s + sleep 0.1s per iteration). A stale sample can therefore be served for up to ~60s + ~55s before being dropped, and staleness is enforced by clearing rather than by the collector omitting expired samples at scrape time. Acceptable for the dashboard's purpose, but the effective window is larger than the nominal 60s.

## 7. Verdict

**`APPROVED WITH NON-BLOCKING FINDINGS`**

The primary deliverable is genuinely in place and correct. The dashboard is version-controlled and provisioned on both Compose and Helm paths; it references only real exported metrics; and it surfaces **actual** consumer lag through a properly-exported `kafka_consumer_lag` gauge (the broker high-watermark − committed offset, not a rate-gap proxy). All five blocking Moderate findings from the round-2 review are resolved: the lag-error double-count is fixed (F1), sample-age tracking with staleness expiry is implemented and unit-tested (F2), the backlog test procedure is corrected to reference the actual run mechanism (F3), the lag-storage code is now unit-tested (F4, with a thin residual gap), and the lag-panel legend disambiguates services (F5).

Verification is solid at the unit level: 74 lag/dashboard/metrics/exporter tests pass, Helm chart tests pass (23, with the dashboard assertion skipped only for lack of a local `helm` binary), and ruff/format/mypy are clean. No secrets, new dependencies, or architecture changes were introduced, and instrumentation failure is correctly contained without altering at-least-once processing semantics.

Remaining findings are Minor and non-blocking: the gauge-emission method and the `_sample_lag` wrappers lack dedicated tests (F-A), `_sample_lag` silently swallows `RuntimeError`/`ValueError` without counting (F-B), and the `KNOWN_METRICS` allow-list does not guard against exporter drift (F-C). One verification gap is flagged rather than a defect: Kafka integration tests (`-m integration`) were not run and are not covered by CI, so the end-to-end lag-export path is unverified. None of these compromise the core event pipeline or the correctness of the dashboard.
