# TASK-086 Review — Platform Dashboard

## 1. Review Header

- **Task ID:** TASK-086
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `c7f38ad53acf6b47573c7c4de345935a094e5ef7...79a987f218cf8d64ba27efb801e99587fb154ac7`
- **Reviewed HEAD:** `79a987f218cf8d64ba27efb801e99587fb154ac7` on `feature/TASK-086`
- **Commits reviewed:**
  - `d034c35` — `feat(TASK-086): Add platform health dashboard`
  - `79a987f` — `fix(TASK-086): Fix datasource UID, use summary-compatible latency queries`
- **Scope:** Version-controlled Grafana platform-health dashboard (`platform-overview.json`) provisioned via Docker Compose volume mount and Helm ConfigMap, with a fixed Prometheus datasource UID, summary-compatible latency queries, a service-availability panel, deterministic dashboard/Helm tests, and documentation.
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

## 2. Requirements Coverage

Requirements sourced from `ai/tasks/TASK-086-platform-dashboard.md`, with context from `ai/PROJECT.md` (§10 Observability, §11 Security), `ai/SPECIFICATION.md` (§20 Observability), `ai/ROADMAP.md` (Milestone 10 — "Platform dashboard" / required "Platform health" dashboard), and `ai/AGENTS.md`. No ADR applies (the sole ADR, ADR-001, is Kafka topic configuration).

| Requirement | Status | Evidence |
|---|---|---|
| Version-controlled Grafana platform-health dashboard | ✅ Met | `monitoring/grafana/dashboards/platform-overview.json` and `helm/ai-data-platform/dashboards/platform-overview.json` (byte-identical, guarded by `test_both_dashboards_are_identical`). |
| Cover **service availability** | ✅ Met | New "Service Availability" panel queries Prometheus `up{}` (legend `{{ job }}`); Prometheus has scrape configs for `ai-data-platform` and `ai-data-platform-background` jobs (`monitoring/prometheus.yml`). |
| Cover **rates** | ✅ Met | "Service Event Rates", "Processor Throughput", "API Request Rate", "Ingestion Events" reference real counters (`kafka_events_processed_total`, `processor_events_valid_total`, `api_requests_total`, `ingestion_events_total`, …). |
| Cover **latency** | ✅ Met | "Processor Latency (avg)", "API Latency (avg)", "Source Fetch Latency (avg)" use summary-compatible `rate(<metric>_sum[5m]) / rate(<metric>_count[5m])` against the platform's `SummaryMetricFamily` / `prometheus_client.Summary` metrics. |
| Cover **errors** | ✅ Met | "Error Rates" references `kafka_consumer_errors_total`, `kafka_processing_errors_total`, `kafka_dead_letter_events_total`, `events_invalid_total` (all real counters). |
| Cover **API** | ✅ Met | "API Request Rate" (`api_requests_total`) and "API Latency (avg)" (`api_request_duration_seconds` summary). |
| Cover **source health/freshness summaries** | ✅ Met | "Source Freshness" (`source_freshness_age_seconds`) and "Source Fetch Success Rate" (`source_fetch_success_total` / `source_fetch_attempts_total`). |
| Use **real metrics** | ✅ Met | Every referenced metric name exists and is emitted by `libs/observability/prometheus_exporter.py` / `services/api/routes/v1/metrics.py`; the metric *types* are now modeled correctly (latency as summaries, not histograms). |
| Low-cardinality labels; no secrets/sensitive payloads | ✅ Met | Labels limited to `service`, `source`, `status`, `job`; no secrets or payloads exposed. |
| Keep dashboards/provisioning version-controlled and reproducible | ✅ Met | Dashboard JSON and the Helm `grafana-dashboards` ConfigMap are committed; Compose and Helm provisioning paths are wired consistently. |
| Follow existing Kubernetes/Helm conventions | ✅ Met | Helm template mirrors the TASK-085 Grafana ConfigMap/Deployment structure and the `.Files.Glob` pattern. |
| No unrelated architecture changes / secrets | ✅ Met | Diff is scoped to Grafana dashboard + provisioning + tests + docs; no production Python changes, no new dependencies. |

## 3. Git Diff Review

**Range:** `c7f38ad53acf6b47573c7c4de345935a094e5ef7...79a987f218cf8d64ba27efb801e99587fb154ac7` (2 commits, 10 files, +913/−4).

Files changed:

- `monitoring/grafana/dashboards/platform-overview.json` (new, 296 lines) — dashboard JSON (Compose path).
- `helm/ai-data-platform/dashboards/platform-overview.json` (new, 296 lines) — byte-identical copy for Helm `.Files.Glob`.
- `helm/ai-data-platform/templates/monitoring/grafana-dashboards-configmap.yaml` (new, 16 lines) — ConfigMap exposing `dashboards/*.json`.
- `helm/ai-data-platform/templates/monitoring/grafana-deployment.yaml` (+6) — mounts the new ConfigMap at `/var/lib/grafana/dashboards`.
- `helm/ai-data-platform/templates/monitoring/grafana-configmap.yaml` (+1) — adds `uid: prometheus` to the Helm datasource provisioning.
- `monitoring/grafana/datasources/prometheus.yml` (+1) — adds `uid: prometheus` to the Compose datasource provisioning.
- `monitoring/README.md` (+33/−1) — documents panels and the two provisioning paths.
- `tests/test_grafana_dashboard.py` (new, 234 lines) — 25 dashboard-structure/PromQL/datasource-UID tests.
- `tests/test_grafana_deployment.py` (+1) — asserts the provisioned datasource `uid`.
- `tests/test_helm_chart.py` (+33) — adds dashboard ConfigMap + volume-mount + datasource-UID assertions.

**Scope correctness:** All changes belong to TASK-086. No unrelated task changes are mixed in.

**Unrelated/accidental changes:** None observed.

**Architectural changes:** None. Grafana remains an observability consumer; the event pipeline, data-lake, warehouse, and API boundaries are untouched. No new dependencies or container images (reuses TASK-085 `grafana/grafana:11.4.0`).

**Dependency/config changes:** The `grafana-dashboards` ConfigMap and the `uid: prometheus` datasource field are new but gated behind the existing `grafana.enabled` flag; both are in-scope.

**Debug/temp/dead code/secrets:** None committed.

**Provisioning wiring (Compose vs Helm):** Correct and consistent.

- Compose: `monitoring/grafana/datasources/prometheus.yml` now declares `uid: prometheus`; the dashboard's panels reference `"uid": "prometheus"`. ✅
- Helm: `grafana-provisioning` ConfigMap declares `uid: prometheus` in `datasources.yml`, and its `dashboards.yml` provider path `/var/lib/grafana/dashboards` matches the `grafana-dashboards` ConfigMap mount. ✅

## 4. Test and Verification Review

**Tests added/changed:**

- `tests/test_grafana_dashboard.py` (25 tests): validates JSON structure, panel type/title/target/datasource presence, datasource **UID** equality, that every PromQL metric name (after stripping `_bucket`/`_count`/`_sum`) appears in `KNOWN_METRICS`, that no `histogram_quantile` query is used, and that coverage panels exist for availability/latency/errors/source-health/API.
- `tests/test_grafana_deployment.py` (+1): asserts the Compose-provisioned datasource `uid == "prometheus"`.
- `tests/test_helm_chart.py` (+5): structural check for the new template, Helm-rendered assertions that the dashboard JSON is in the `grafana-dashboards` ConfigMap, that the volume is mounted, and that the datasource `uid` is set.

**Independently verified (executed by reviewer):**

- `python -m pytest tests/test_grafana_dashboard.py tests/test_grafana_deployment.py -q` → **38 passed**.
- `python -m pytest tests/test_helm_chart.py -q` → **23 passed, 28 skipped** (the `_helm_template`/`_helm_lint` cases skip because `helm` is not installed in this environment).
- `python -m ruff check tests/test_grafana_dashboard.py tests/test_grafana_deployment.py tests/test_helm_chart.py` → **All checks passed**.
- `python -m ruff format --check tests/test_grafana_dashboard.py tests/test_grafana_deployment.py tests/test_helm_chart.py` → **3 files already formatted**.

**Implementation evidence reviewed (not rerun):**

- CI workflow installs Helm and runs `pytest`, so the 28 locally-skipped Helm rendering tests execute in CI.

**Unverified:**

- Helm rendering/lint could not be executed locally (`helm` not installed); the new Helm assertions were reviewed manually.
- `mypy` was not rerun; the change set is JSON/YAML/docs/tests only (no production Python changes), so type-check impact is nil.

**Integration tests:** Not applicable. TASK-086 is a dashboard/provisioning change; it does not touch Kafka, persistence, MinIO/S3, or infrastructure boundaries, so the `-m integration` requirement does not apply.

**Test-adequacy note (resolved from prior round):** The suite now asserts the two properties that previously escaped detection — the datasource `uid` is checked in `test_every_panel_has_datasource`, and `test_no_histogram_quantile_queries` guards against histogram queries against summary metrics. The tests still validate metric *names* rather than *types* (a histogram named `_bucket` would not be detected by type), but the `no_histogram_quantile` guard plus the explicit name allow-list is a reasonable deterministic proxy for this dashboard-only scope.

## 5. Findings

### F1 — Minor — "Processor Throughput" stat thresholds are degenerate and invert the color semantics

- **File:** `monitoring/grafana/dashboards/platform-overview.json` (lines 137–139); identical in `helm/ai-data-platform/dashboards/platform-overview.json`.
- **Problem:** The panel declares `{ "color": "green", "value": null }, { "color": "yellow", "value": 0 }, { "color": "red", "value": 0 }`. With Grafana's ascending-absolute threshold evaluation (a value takes the color of the last threshold whose value is ≤ the data value), any positive rate matches both the `yellow` and `red` steps and renders **red**. The yellow/red distinction at the same value (`0`) is meaningless, and the panel effectively colors a healthy non-zero throughput as red.
- **Impact:** Cosmetic — data renders correctly, but the color coding is inverted/uninformative for a panel meant to signal health.
- **Recommendation:** Use a meaningful threshold scheme (e.g., `{ red: null }` for zero, `{ green: 0 }` for positive, or two distinct positive breakpoints), or remove the yellow/red steps and keep a single neutral style.

### F2 — Minor — "Service Availability" stat panel may collapse multiple `up{}` series to one value

- **File:** `monitoring/grafana/dashboards/platform-overview.json` (lines 9–41).
- **Problem:** The panel queries `up` (one series per scrape job/instance) but does not enable per-series display (`options.allValues` / `options.colorMode`). A Grafana `stat` panel with the default "Calculate" mode reduces multiple series to a single value (last non-null), so the panel shows one aggregate number rather than the per-service up/down status that `legendFormat: "{{ job }}"` implies.
- **Impact:** The availability requirement is met at the metric level, but the panel's usefulness is degraded — an operator cannot see *which* service is down from this panel.
- **Recommendation:** Set `"options": { "allValues": true, ... }` (or equivalent) so the stat panel renders one stat per job, or switch to a `status-history`/`table` panel keyed on `job`. Non-blocking.

### F3 — Minor — Dashboard JSON duplicated across Compose and Helm instead of reconciled

- **Files:** `monitoring/grafana/dashboards/platform-overview.json` and `helm/ai-data-platform/dashboards/platform-overview.json`.
- **Problem:** Two byte-identical copies are kept, synchronized only by `test_both_dashboards_are_identical`. The prior TASK-085 review suggested reconciling Compose/Helm dashboard directories; TASK-086 retains the two-copy approach.
- **Impact:** Maintainability risk — future edits must be duplicated, and divergence is caught only at test time. The `monitoring/README.md` "Adding dashboards" section does document the two-copy procedure, so the approach is discoverable.
- **Recommendation:** Prefer a single source-of-truth directory consumed by both Compose and Helm, or keep the two-copy approach with the explicit trade-off noted. Non-blocking.

## 6. Non-Defect Observations

- **Helm rendering not independently verified.** `helm` is unavailable locally, so the new Helm assertions (`test_grafana_dashboards_configmap_contains_dashboard_json`, `test_grafana_deployment_mounts_dashboard_volume`) were reviewed manually, not executed. They run in CI (Helm is installed there). This mirrors TASK-085.
- **Nested volume mount at `/var/lib/grafana/dashboards` under the `/var/lib/grafana` `emptyDir`.** The `dashboards` ConfigMap (readOnly) is mounted inside the `data` `emptyDir`. kubelet mounts deeper paths first, so this resolves correctly, but the nesting is subtle and worth a comment/test guard.
- **"Error Rates" absolute threshold of `1` ops/s.** For rate-based series an absolute threshold of 1 event/sec is arbitrary; a relative threshold or `value > 0` with a distinct style may be more useful. Tuning observation only.
- **`histogram` appears in `PANEL_TYPES` but is not used.** The dashboard uses only `timeseries`, `stat`, and `gauge`. Not a defect.
- **`import json` inside `test_grafana_dashboards_configmap_contains_dashboard_json`.** Inline import within a function body is a minor style nit; harmless.

## 7. Verdict

**`APPROVED WITH NON-BLOCKING FINDINGS`**

The change is correctly scoped, follows repository conventions, and its provisioning wiring (Compose and Helm) is internally consistent. The two High findings from the prior review round are resolved and independently verified:

1. **Datasource UID (previously High)** — both provisioning sources now declare `uid: prometheus`, matching every panel's `datasource.uid`, and tests assert it.
2. **Latency query type (previously High)** — the three latency panels now use summary-compatible `rate(<metric>_sum[5m]) / rate(<metric>_count[5m])` queries, which are valid against the platform's actual summary metrics.
3. **Service availability** — now covered by a dedicated `up{}` panel.

The remaining findings (F1 threshold color inversion, F2 stat-panel series display, F3 dashboard duplication) are cosmetic/usability/maintainability issues and do not block acceptance. Recommend addressing them in a follow-up pass but not as a merge gate.
