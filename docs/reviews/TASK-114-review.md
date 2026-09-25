# TASK-114 Review — Measure API Latency

## 1. Review Header

- **Task ID:** TASK-114 — Measure API Latency
- **Review date:** 2026-09-25
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `51a884485930fea68f9b9ac017803b723dbe65f6...d6fc4edab012d50f3981bc7afe86f4b65f68af8e` (three-dot merge-base diff)
- **Reviewed HEAD:** `d6fc4edab012d50f3981bc7afe86f4b65f68af8e` on `feature/TASK-114`
- **Commit reviewed:** `d6fc4ed feat(TASK-114): add API latency measurement to load test harness`
- **Scope:** Systematic API latency measurement during load tests, integrated into the load-test harness (`libs/load_test/`, `scripts/run_load_test.py`, `docs/api-latency-measurement.md`, `tests/test_api_latency_collector.py`, `tests/test_api_latency_probe.py`).
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

### Authorities consulted

- `ai/PROJECT.md` (§10 observability — "API latency … must be observable", §11 security — no secrets, §12 testing)
- `ai/SPECIFICATION.md` (§20 Observability, §23 Performance Testing — "API latency" is an explicit measurement under 100/500/1000 eps load scenarios)
- `ai/tasks/TASK-114-measure-api-latency.md` (primary task source)
- `ai/AGENTS.md`, `ai/REVIEWER.md`
- Existing implementation: TASK-108 harness (`libs/load_test/runner.py`, `config.py`, `scripts/run_load_test.py`), TASK-112 lag probe (`kafka_lag_probe.py`, `lag_collector.py`), TASK-113 latency probe (`pg_latency_probe.py`, `latency_collector.py`), and the FastAPI routes under `services/api/routes/v1/`.

No authority conflicts identified.

---

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
|---|---|---|
| Systematic API latency measurement across load tests | **Met** | `ApiLatencyCollector` + `api_latency_probe.create_api_probe_fn()` wired into `LoadTestRunner.run()` via a background `_start_api_latency_monitor` thread (`libs/load_test/runner.py`). |
| Report response-time distribution for key endpoints under pipeline load | **Met** | `to_report_dict()` computes per-endpoint and overall `min/p50/p95/p99/max/mean`; `runner.run()` emits an `api_latency` report section. |
| Identify slow queries | **Partially met** | Per-endpoint percentile comparisons identify slow endpoints, and `status_codes` capture 5xx under stress. However, requests that time out are silently dropped (see F1), so the very slowest endpoints can be under-reported. |
| Document API behavior when the pipeline is under stress | **Met** | HTTP status codes (including 5xx) are recorded per endpoint; docs describe status-code interpretation and error rates. Timeout behavior is the exception (F1). |
| Do not invent benchmark numbers; record actual results | **Met** | No fabricated numbers — latency is computed from `time.perf_counter()` measurements; docs contain no invented benchmark tables. |
| Reuse existing API and monitoring infrastructure | **Met** | Reuses the TASK-108 harness, the TASK-112/113 `create_*_probe_fn` factory pattern, and stdlib `urllib.request` (no new third-party dependency). |
| Measurements reproducible | **Met** | Deterministic, configurable (`api_base_url`, `api_endpoints`, `api_latency_poll_interval_sec`, `api_latency_timeout_sec`); client-side clock only, no cross-node skew. |
| Document API latency behavior under pipeline load | **Met** | `docs/api-latency-measurement.md` covers architecture, configuration, report format, slow-query interpretation, and limitations. |
| Deterministic tests where applicable | **Met** | `api_latency_collector.py` and `api_latency_probe.py` are well covered by mock-based unit tests. |
| No unrelated architecture changes or secrets | **Met** | Change set is confined to the harness/docs/tests; no secrets, no new dependencies, no architecture changes. |

---

## 3. Git Diff Review

### Change-set topology (important)

The supplied three-dot range resolves through the merge base to a single commit:

- `git merge-base 51a8844 d6fc4ed` → `191ac19a5faf247a52062fb96fb6f97ac3ea03be`
- `51a8844` ("docs: add post-M13 platform inventory task") is a **sibling** commit on `main` (in the other worktree `C:/Users/igors/RnD/agentic-data-platform`), sharing parent `191ac19` with `d6fc4ed`. It is **not** an ancestor of the reviewed HEAD.
- Therefore `git diff 51a8844...d6fc4ed` == `git diff 191ac19 d6fc4ed` == exactly the TASK-114 change, and `git log 51a8844..d6fc4ed` == `{d6fc4ed}`.

A naive two-dot diff `git diff 51a8844..d6fc4ed` additionally shows `ai/tasks/TASK-DOCS-PLATFORM-INVENTORY-M13.md` as deleted (365 lines). That is **not** a TASK-114 change: `main` added that file *after* the branch point, and it is not tracked on `feature/TASK-114` (confirmed via `git ls-files`). This is a sibling-branch artifact, not a scope problem.

**Files changed (9 files, +706):**

| File | Change |
|---|---|
| `docs/api-latency-measurement.md` | New (+116) |
| `libs/load_test/__init__.py` | +3 (exports `ApiLatencyCollector`, `ApiLatencySample`) |
| `libs/load_test/api_latency_collector.py` | New (+137) |
| `libs/load_test/api_latency_probe.py` | New (+80) |
| `libs/load_test/config.py` | +26 (4 new settings) |
| `libs/load_test/runner.py` | +42 (API latency monitor integration) |
| `scripts/run_load_test.py` | +52 (3 CLI flags, probe wiring) |
| `tests/test_api_latency_collector.py` | New (+137) |
| `tests/test_api_latency_probe.py` | New (+113) |

- **Scope correctness:** All nine files belong to TASK-114. No unrelated files touched.
- **Unrelated changes:** None (the inventory-doc "deletion" in the two-dot diff is a sibling-branch artifact, as explained above).
- **Architectural changes:** None. The harness remains source-adapter independent; the probe is a read-only HTTP GET client that never mutates pipeline state and never touches Kafka or PostgreSQL.
- **Dependency/configuration changes:** No new third-party dependency — `urllib.request` (stdlib) is used deliberately to avoid adding `httpx`/`requests`. Four new opt-in `LoadTestSettings` fields; probing is disabled when `api_base_url` is empty or in `--dry-run`.
- **Accidental changes:** None observed (no debug code, temp files, generated artifacts, or committed secrets).
- **Test changes that weaken validation:** None. Existing tests untouched; only additions.
- **Behavior change to existing harness:** None for default runs — `api_probe_fn` defaults to `None`, so `_start_api_latency_monitor` returns `None` and the `api_latency` report section is only added when samples exist. Existing report consumers are unaffected.

---

## 4. Test and Verification Review

### Tests examined

- `tests/test_api_latency_collector.py` (new) — covers the frozen `ApiLatencySample`, empty-report behavior, `record_sample`/`get_samples`, single/multiple-endpoint reports, error status codes, overall latency, and `_compute_percentiles` edge cases (empty, single, multiple, distribution shape). Good coverage of the pure logic.
- `tests/test_api_latency_probe.py` (new) — covers successful probe, multiple endpoints, HTTP-error status capture (503), connection-error skip, and trailing-slash normalization, all via mocked `urllib.request.urlopen`.
- `tests/test_load_test/test_runner.py` (existing) — not extended to exercise `_start_api_latency_monitor` or the `api_latency` report key.
- `tests/test_load_test/test_config.py` (existing) — not extended to cover the four new settings (see F3).
- No test references the probe against a live FastAPI app; mock-only (see F6).

### Verification classification

| Check | Status | Evidence |
|---|---|---|
| `python -m pytest tests/test_api_latency_collector.py tests/test_api_latency_probe.py tests/test_load_test/ tests/test_latency_collector.py tests/test_lag_collector.py tests/test_pg_latency_probe.py -q` | **Independently verified** | `124 passed in 12.25s` (run by reviewer). |
| `python -m ruff check <8 changed py files>` | **Independently verified** | `All checks passed!` |
| `python -m ruff format --check <changed py files>` | **Independently verified** | `2 files already formatted` (new files) — full changed set formatted. |
| `python -m mypy libs/load_test/api_latency_collector.py libs/load_test/api_latency_probe.py libs/load_test/runner.py libs/load_test/config.py libs/load_test/__init__.py scripts/run_load_test.py` | **Independently verified** | `Success: no issues found in 6 source files` |
| Default endpoint existence | **Independently verified (static)** | All four defaults confirmed in `services/api/routes/v1/`: `/api/v1/health` (`health.py`), `/api/v1/products` (`products.py`), `/api/v1/analytics/price-changes` (`analytics.py`), `/api/v1/quality/summary` (`quality.py`), mounted under prefix `/api/v1` (`services/api/app.py`). |
| Integration tests (`pytest -m integration`) | **Unverified / no evidence** | No `@pytest.mark.integration` test was added for the probe, and no integration run report was supplied. Not rerun (requires Docker Compose stack). |

### Test adequacy

- The deterministic, pure-logic collector and the probe's HTTP handling are well unit-tested, including error/edge paths.
- The probe's correctness is independent of the API's internals (it is a generic HTTP GET), so the absence of an integration test against a live API is lower-risk than the analogous gap flagged for TASK-113's SQL probe. The material residual risk is that endpoint paths are configurable and validated only by convention, not by a test against the router (F6).

---

## 5. Findings

### F1 — Moderate: timeouts and connection errors are silently dropped, hiding the slowest endpoints
- **Affected:** `libs/load_test/api_latency_probe.py:67-71` (`except urllib.error.HTTPError` → records status; `except Exception` → `continue`).
- **Problem:** `urllib.request.urlopen(..., timeout=timeout_sec)` raises `socket.timeout`/`urllib.error.URLError` when a request exceeds `api_latency_timeout_sec` (default 10.0 s) or the connection is refused. Both fall into the broad `except Exception: continue`, so **no sample is recorded**. `ApiLatencyCollector.to_report_dict()` returns `None` when there are zero samples, so a fully unresponsive or slow endpoint produces no `api_latency` section at all — indistinguishable from probing disabled.
- **Impact:** Directly weakens the task objective ("identify slow queries", "document API behavior when the pipeline is under stress"). An endpoint degraded to the point of timing out is exactly the case the measurement should surface, but it is excluded from the latency distribution and status-code counts, understating p99/max and error rate.
- **Recommendation:** Record a synthetic timeout sample (e.g., `status_code=0` or a dedicated `"timeouts"` counter) so timed-out endpoints appear in the report; alternatively log a warning per timeout. At minimum, when probing was enabled but produced no samples, emit an explicit `api_latency` marker (e.g., `{"total_samples": 0, "enabled": true}`) rather than omitting the section.

### F2 — Minor: duplicated `_compute_percentiles` (third copy in the codebase)
- **Affected:** `libs/load_test/api_latency_collector.py:108-137`.
- **Problem:** `_compute_percentiles` here is a verbatim copy of `libs/load_test/latency_collector.py:161` (same key set, same linear-interpolation formula). Combined with the variant in `libs/load_test/metrics_collector.py:251` (which additionally emits `p90`), there are now three percentile implementations.
- **Impact:** Maintainability/drift risk; a future bug fix or key-set change must be applied in three places.
- **Recommendation:** Extract a single shared percentile helper in `libs/load_test/` and reuse it in all three modules.

### F3 — Minor: new `LoadTestSettings` fields lack configuration tests
- **Affected:** `libs/load_test/config.py:102-126`; `tests/test_load_test/test_config.py`.
- **Problem:** TASK-108's `test_config.py` asserts defaults and validation for existing fields, but TASK-114's four new fields (`api_base_url`, `api_endpoints`, `api_latency_poll_interval_sec`, `api_latency_timeout_sec`) have no test coverage: no default assertions, no `gt=0` validation tests for the two interval fields, and no test that the `api_endpoints` default is the four canonical paths.
- **Impact:** Minor; a regression in defaults or validation constraints would go unnoticed.
- **Recommendation:** Add default-value and validation tests to `tests/test_load_test/test_config.py`.

### F4 — Minor: `APP_API_ENDPOINTS` environment-variable format is undocumented
- **Affected:** `docs/api-latency-measurement.md:60`; `libs/load_test/config.py:109`.
- **Problem:** `api_endpoints: list[str]` is parsed by pydantic-settings as JSON. The docs table lists the default using comma-separated prose ("`/api/v1/health`, `/api/v1/products`, …") without stating that the env value must be a JSON array (e.g. `APP_API_ENDPOINTS='["/api/v1/health","/api/v1/products"]'`). A user setting a plain comma/space-separated value will get a validation error.
- **Impact:** Minor usability/documentation gap; the CLI `--api-endpoints` (space-separated, `nargs="+"`) works as documented, but the env-var path is ambiguous.
- **Recommendation:** Document the JSON-array format explicitly in the env-var table.

### F5 — Minor: test file placement inconsistent with existing load-test tests
- **Affected:** `tests/test_api_latency_collector.py`, `tests/test_api_latency_probe.py`.
- **Problem:** These live at the `tests/` root, whereas the TASK-108 load-test tests live under `tests/test_load_test/`.
- **Impact:** Organizational inconsistency (also present for TASK-112's `test_lag_collector.py` and TASK-113's `test_latency_collector.py`/`test_pg_latency_probe.py`, so the repo already carries this split).
- **Recommendation:** Move to `tests/test_load_test/` for consistency, or adopt the root placement uniformly across all load-test tests.

### F6 — Minor: no integration test exercises the probe against the live API
- **Affected:** `tests/test_api_latency_probe.py` (mock-only); `libs/load_test/api_latency_probe.py`.
- **Problem:** The probe is validated only against mocked `urllib.request.urlopen`. No `@pytest.mark.integration` test spins up the FastAPI app (or a stub server) and asserts the probe records a real sample for the default endpoints.
- **Impact:** Low risk (generic HTTP GET, endpoints independently verified), but the default endpoint list is validated only by convention. A future route rename would silently turn a probe into a stream of 404s without a test failing.
- **Recommendation:** Add a lightweight integration test that starts the FastAPI app (or a `http.server` stub) and asserts the probe records status 200 for a real path.

---

## 6. Non-Defect Observations

- **Correct endpoint targeting:** All four default endpoints exist and are reachable under the `/api/v1` prefix (verified against `services/api/routes/v1/*.py` and `services/api/app.py`).
- **Clean dependency injection:** `ApiLatencyCollector`/`ApiProbeFn` injection mirrors the existing `ProduceFn`/`LagQueryFn`/`PgQueryFn` pattern, keeping the collector and probe unit-testable without a network — a good separation of concerns.
- **Correct thread-safety:** `ApiLatencyCollector` mutates under a lock and computes `to_report_dict()` on a detached copy outside the lock; no lock is held during sorting/percentile math.
- **Backward compatible:** The `api_latency` section is only present when samples exist, and the monitor is disabled when `api_base_url` is empty or in `--dry-run`. Existing report consumers and default runs are unaffected.
- **No new dependency:** Using stdlib `urllib.request` avoids an `httpx`/`requests` dependency, consistent with the "reuse existing infrastructure" rule.
- **Honest limitation documentation:** `docs/api-latency-measurement.md` correctly notes client-side measurement (network overhead included), sequential synchronous probes, and unauthenticated endpoints.
- **Report shape consistency:** `api_latency.latency_ms` uses the same `min/p50/p95/p99/max/mean` key set as `processing_latency.latency_ms` (no `p90`), so the two latency sections are mutually consistent.
- **Complementary, not duplicative, of server metrics:** The harness measures client-side round-trip latency; SPECIFICATION.md §20's `api_request_duration_seconds` (server-side Prometheus) remains a separate, complementary signal. This is correctly framed in the docs as client-side.

---

## 7. Verdict

**`APPROVED WITH NON-BLOCKING FINDINGS`**

The implementation correctly, cleanly, and deterministically implements systematic API-latency measurement: a stdlib-HTTP probe with a thread-safe per-endpoint collector, `p50/p95/p99` distribution computation, a JSON `api_latency` report section, CLI/env configuration, and a dedicated documentation page — without altering existing harness behavior, architecture, or dependencies. The pure logic is well unit-tested, and lint/format/type checks pass. I independently confirmed the default endpoints exist in the FastAPI router and verified the collection/percentile logic via the unit tests.

No Critical or High findings. The one Moderate finding (**F1: timeouts/connection failures are silently dropped, hiding the slowest endpoints**) is the most material gap and should be addressed before this measurement is relied upon to characterize API behavior under heavy stress. The Minor findings (F2–F6) are follow-up improvements: de-duplicate the percentile helper, add config tests, document the env-var JSON format, normalize test placement, and add a live-API integration test.
