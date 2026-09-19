# TASK-087 Review — Data-Quality Dashboard

## 1. Review Header

- **Task ID:** TASK-087
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `578d8e37f620833bd24cfc49f70fea2891ad2e94...5fbe2850bb3c068b5f7a89c62fe0fbdbafc7cc13`
- **Reviewed HEAD:** `5fbe2850bb3c068b5f7a89c62fe0fbdbafc7cc13` on `feature/TASK-087`
- **Commits reviewed:**
  - `5fbe285` — `feat(TASK-087): Add data-quality dashboard`
- **Scope:** Version-controlled Grafana data-quality dashboard (`data-quality.json`) provisioned via Docker Compose volume mount and Helm ConfigMap, with a fixed Prometheus datasource UID, deterministic dashboard/Helm tests, and documentation.
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

## 2. Requirements Coverage

Requirements sourced from `ai/tasks/TASK-087-data-quality-dashboard.md`, with context from `ai/PROJECT.md` (§10 Observability, §11 Security), `ai/SPECIFICATION.md` (§14 Data Quality, §20 Observability), `ai/ROADMAP.md` (Milestone 10 — "Data-quality dashboard" / required "Data quality" dashboard), and `ai/AGENTS.md`. No ADR applies (the sole ADR, ADR-001, is Kafka topic configuration).

| Requirement | Status | Evidence |
|---|---|---|
| Provisioned dashboard for data-quality/freshness results | ✅ Met | `monitoring/grafana/dashboards/data-quality.json` (Compose) and `helm/ai-data-platform/dashboards/data-quality.json` (Helm, byte-identical, guarded by `test_both_dashboards_are_identical`). Both provisioning paths auto-detect the file. |
| Show current failures and trends | ✅ Met | Gauges/stats for current state (Validation Pass Rate, Source Freshness, Source Fetch Success Rate, Source Fetch Failure Rate); timeseries for trends (Invalid Event Rate, Deduplication Rate, Processing Failure Rate, DLQ Rate, Malformed Records, Zero-Record Fetches, Partial Failures & Retries, Collected vs Emitted). |
| Distinguish missing data from explicit pass states | ✅ Met | See Non-Defect Observation N1: pass-rate gauges use `rate(a) / (rate(a) + rate(b))` against counters that are *always* exported (zero-valued) by `ProcessorMetrics.snapshot()` / `SourceMetrics.snapshot()`, so a silent pipeline yields `0/0 → NaN → "No data"`, whereas a flowing-but-clean pipeline yields `100%`. Freshness is a gauge emitted only after the first successful fetch, so "never fetched" also renders "No data" rather than "fresh". |
| Reuse established metrics (no new telemetry) | ✅ Met | Every referenced metric exists in `libs/observability/{kafka_metrics,processor_metrics,source_metrics}.py` and is exported by `libs/observability/prometheus_exporter.py`. No new metric families, labels, or instrumentation were introduced. |
| Low-cardinality labels; no secrets/payloads | ✅ Met | Labels limited to `service` and `source`; no secret or payload fields in the dashboard JSON. |
| Keep dashboards/provisioning version-controlled and reproducible | ✅ Met | Dashboard JSON and the Helm `grafana-dashboards` ConfigMap are committed; the Compose datasource (`uid: prometheus`) and Helm datasource (`uid: prometheus`) match every panel's `datasource.uid`. |
| Follow existing Kubernetes/Helm conventions | ✅ Met | Reuses the TASK-086 `grafana-dashboards` ConfigMap with `.Files.Glob "dashboards/*.json"`; no new template required. |
| No unrelated architecture changes / secrets / new dependencies | ✅ Met | Diff is scoped to dashboard JSON + docs + tests; no production Python changes, no new dependencies, no secrets. |

## 3. Git Diff Review

**Range:** `578d8e37f620833bd24cfc49f70fea2891ad2e94...5fbe2850bb3c068b5f7a89c62fe0fbdbafc7cc13` (1 commit, 5 files, +943/−3).

Files changed:

- `monitoring/grafana/dashboards/data-quality.json` (new, 327 lines) — dashboard JSON (Compose path).
- `helm/ai-data-platform/dashboards/data-quality.json` (new, 327 lines) — byte-identical copy for Helm `.Files.Glob`.
- `monitoring/README.md` (+30) — adds a "Data Quality Dashboard (TASK-087)" section and documents nine previously-undocumented (but already existing) metrics.
- `tests/test_grafana_data_quality_dashboard.py` (new, 251 lines) — 26 dashboard-structure/PromQL/datasource-UID/coverage tests.
- `tests/test_helm_chart.py` (+11/−3) — extends the existing `grafana-dashboards` ConfigMap assertion to also assert `data-quality.json` and its `uid`.

**Scope correctness:** All changes belong to TASK-087. No unrelated task changes are mixed in.

**Unrelated/accidental changes:** None observed.

**Architectural changes:** None. Grafana remains an observability consumer; the event pipeline, data-lake, warehouse, and API boundaries are untouched. No new dependencies or container images (reuses the TASK-085 `grafana/grafana:11.4.0` image).

**Dependency/config changes:** None beyond adding a second dashboard JSON to the already-established `.Files.Glob` ConfigMap. No Helm template or datasource changes were required because TASK-086 already established the pattern.

**Debug/temp/dead code/secrets:** None committed.

**Provisioning wiring (Compose vs Helm):** Correct and consistent.

- Compose: `docker-compose.yml` mounts `./monitoring/grafana/dashboards` → `/etc/grafana/provisioning/dashboards:ro`; `dashboard.yml`'s provider path matches. The datasource `prometheus.yml` declares `uid: prometheus`, matching every panel's `datasource.uid`. ✅
- Helm: `grafana-dashboards` ConfigMap globs `dashboards/*.json` (now includes `data-quality.json`) and is mounted read-only at `/var/lib/grafana/dashboards`; `grafana-provisioning` ConfigMap declares `uid: prometheus` and its `dashboards.yml` provider path matches the mount. ✅

## 4. Test and Verification Review

**Tests added/changed:**

- `tests/test_grafana_data_quality_dashboard.py` (26 tests): validates the two dashboard copies exist and are identical; top-level structure (`schemaVersion` 39, `uid`, `title`, `tags`, `editable`); per-panel title/type/target/datasource presence and datasource **UID** equality; non-overlapping grid positions; that every PromQL metric name (after stripping `_bucket`/`_count`/`_sum`) appears in `KNOWN_METRICS`; that no `histogram_quantile` query is used; and that coverage panels exist for validation/freshness/dedup/failures/DLQ/source-quality.
- `tests/test_helm_chart.py` (extended): asserts the `grafana-dashboards` ConfigMap now also contains `data-quality.json` with `uid == "ai-data-platform-data-quality"`.

**Independently verified (executed by reviewer):**

- `python -m pytest tests/test_grafana_data_quality_dashboard.py -q` → **26 passed**.
- `python -m pytest tests/test_helm_chart.py -q` → **23 passed, 28 skipped** (the `_helm_template`/`_helm_lint` cases skip because `helm` is not installed in this environment).
- `python -m ruff check tests/test_grafana_data_quality_dashboard.py tests/test_helm_chart.py` → **All checks passed**.
- `python -m ruff format --check tests/test_grafana_data_quality_dashboard.py tests/test_helm_chart.py` → **2 files already formatted**.

**Implementation evidence reviewed (not rerun):**

- The specific Helm assertion `test_grafana_dashboards_configmap_contains_dashboard_json` is skipped locally (`helm binary not available`). It runs in CI (Helm is installed there). The inclusion of `data-quality.json` is confirmed by inspection: the ConfigMap template uses `.Files.Glob "dashboards/*.json"` and the file is present in `helm/ai-data-platform/dashboards/`.

**Unverified:**

- Helm rendering/lint could not be executed locally (`helm` not installed); the new Helm assertion was reviewed manually.
- `mypy` was not rerun; the change set is JSON/YAML/docs/tests only (no production Python changes), so type-check impact is nil.

**Integration tests:** Not applicable. TASK-087 is a dashboard/provisioning change; it does not touch Kafka, persistence, MinIO/S3, or infrastructure boundaries, so the `-m integration` requirement does not apply.

**Metric-existence verification (independent of the test's allow-list):** The test's `KNOWN_METRICS` set is a hardcoded allow-list, not cross-referenced against the source. I independently confirmed every referenced metric is defined and exported: `processor_events_{valid,invalid,duplicate,failed}_total` in `processor_metrics.py`/`_PROCESSOR_COUNTERS`; `events_invalid_total`, `kafka_processing_errors_total`, `kafka_dead_letter_events_total` in `kafka_metrics.py`/`_KAFKA_COUNTERS`; and `source_fetch_{attempts,success,failure}_total`, `source_records_{collected,emitted}_total`, `source_zero_record_fetches_total`, `source_retry_attempts_total`, `source_malformed_records_total`, `source_partial_failures_total`, `source_freshness_age_seconds` in `source_metrics.py` and `prometheus_exporter.py`. No dashboard query references a non-existent metric.

## 5. Findings

### F1 — Minor — "references real metrics" test silently skips the bare freshness query

- **File:** `tests/test_grafana_data_quality_dashboard.py` (the `_extract_metric_names` helper and `test_all_metric_names_are_known`).
- **Problem:** `_extract_metric_names` matches a token only when it is followed by `[`, `{`, or `(`. The "Source Freshness" panel query is the bare `source_freshness_age_seconds` (no function/brackets), so it is never extracted. `test_all_metric_names_are_known` therefore iterates over an empty set for that panel and provides no protection against a typo'd freshness metric name.
- **Impact:** Test-completeness gap only. The metric currently referenced *is* real (independently confirmed), so no live defect. But the "real metrics" guarantee is weaker than its name implies. The same pattern pre-exists in `tests/test_grafana_dashboard.py` (TASK-086) for the bare `up` and `source_freshness_age_seconds` queries.
- **Recommendation:** Also assert bare gauge expressions against `KNOWN_METRICS` (e.g., special-case tokens that match `^[a-zA-Z_:][a-zA-Z0-9_:]*$` with no function call), or list panel `expr` values that contain no `(`/`[` and check them explicitly.

### F2 — Minor — "Zero-Record Fetches" and "Partial Failures & Retries" thresholds never escalate to red

- **Files:** `monitoring/grafana/dashboards/data-quality.json` (panels "Source Zero-Record Fetches" and "Source Partial Failures & Retries"); identical in `helm/ai-data-platform/dashboards/data-quality.json`.
- **Problem:** Both panels declare only `{ "color": "green", "value": null }, { "color": "yellow", "value": 1 }`. With Grafana's ascending-absolute threshold evaluation, any rate ≥ 1 renders yellow and there is no red step, so a severe zero-record/partial-failure rate is visually indistinguishable from a mild one.
- **Impact:** Cosmetic — data renders correctly, but the color coding under-communicates severity for two panels that exist specifically to surface source degradation.
- **Recommendation:** Add a red breakpoint (e.g., `{ "color": "red", "value": 5 }` or a source-appropriate value) so high rates escalate distinctly. Non-blocking.

### F3 — Minor — Dashboard JSON duplicated across Compose and Helm instead of reconciled

- **Files:** `monitoring/grafana/dashboards/data-quality.json` and `helm/ai-data-platform/dashboards/data-quality.json`.
- **Problem:** Two byte-identical copies are kept, synchronized only by `test_both_dashboards_are_identical`. This is the same approach (and trade-off) flagged in the TASK-086 review.
- **Impact:** Maintainability risk — future edits must be duplicated, and divergence is caught only at test time. The `monitoring/README.md` "Adding dashboards" section documents the two-copy procedure, so it is discoverable.
- **Recommendation:** Prefer a single source-of-truth directory consumed by both Compose and Helm, or retain the two-copy approach with the trade-off noted. Non-blocking.

## 6. Non-Defect Observations

- **N1 — "Missing data vs explicit pass" is achieved through a subtle but correct mechanism.** The pass-rate gauges rely on the fact that `ProcessorMetrics.snapshot()` and `SourceMetrics.snapshot()` return *all* counters (initialized via `dict.fromkeys`, including zeros), and `PlatformMetricsCollector` adds every counter value to its `CounterMetricFamily`. Consequently a silent pipeline produces `rate(valid) = 0` and `rate(invalid) = 0`, making `0 / (0 + 0) * 100 = NaN`, which Grafana renders as "No data" — not 100%/green. A clean-but-active pipeline produces 100%. The freshness gauge (`source_freshness_age_seconds`) is only emitted once `source_last_successful_fetch` is non-null, so "never fetched" also renders "No data". This correctly satisfies the task's core distinction, but it is implicit in the metric mechanics rather than expressed in the dashboard; a one-line comment in the dashboard JSON or README explaining the "No data = missing, 100% = explicit pass" intent would aid future maintainers.
- **N2 — Some panel overlap with TASK-086's `platform-overview.json`.** "Source Freshness" and "Source Fetch Success Rate" appear in both dashboards. This is acceptable (a focused data-quality view may legitimately re-surface source-health signals) but worth noting for future dashboard consolidation.
- **N3 — `source_pages_fetched_total` is documented but not used by any panel.** The README's metrics table (correctly) lists it as an existing `SourceMetrics` counter, but the dashboard does not reference it. Not a defect; the README is completing documentation of pre-existing metrics.
- **N4 — `histogram` remains in `PANEL_TYPES` but is unused.** The dashboard uses only `timeseries`, `stat`, and `gauge`. Not a defect.
- **N5 — The `-m integration` requirement does not apply** because this task touches no Kafka/persistence/infrastructure boundary.

## 7. Verdict

**`APPROVED WITH NON-BLOCKING FINDINGS`**

The change is correctly scoped, follows repository conventions, and is internally consistent. All twelve dashboard panels reference real, currently-exported Prometheus metrics (verified independently against `libs/observability`, not just the test allow-list), and the dashboard genuinely distinguishes missing data from explicit pass states via always-exported zero-valued counters and the freshness gauge's first-fetch gating. Provisioning is correct on both the Docker Compose and Helm paths, and the datasource `uid: prometheus` matches the provisioned datasource.

The three findings are all Minor (test-completeness gap, cosmetic threshold escalation, and dashboard duplication) and do not block acceptance. Recommend addressing them in a follow-up pass but not as a merge gate.
