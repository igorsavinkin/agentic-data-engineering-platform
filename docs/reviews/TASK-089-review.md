# TASK-089 Review — Structured Logging

## 1. Review Header

- **Task ID:** TASK-089
- **Review date:** 2026-09-20
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `7d6318b9e7a098533ecb6290e11ec92aa5e385ce...ab6eabaead868847bf488be51a552de3642ba521`
- **Reviewed HEAD (commit):** `ab6eabaead868847bf488be51a552de3642ba521` on `feature/TASK-089`
- **Commits reviewed:**
  - `ab6eaba` — `feat(TASK-089): Structured JSON logging with centralized configuration`
- **Scope:** A centralized structured JSON logging configuration (`libs/observability/logging_config.py`) with a `StructuredFormatter` (service/environment/timestamp/level plus arbitrary `extra` fields), an exception convention, and a `ContextVar`-backed correlation ID; migration of five pipeline services (ingestion, processor, raw-writer, lake-writer, warehouse-loader) from `logging.basicConfig` to `setup_logging`; documentation in `monitoring/README.md`; and unit tests in `tests/test_logging_config.py`.
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

Sources of authority consulted: `ai/tasks/TASK-089-structured-logging.md`; `ai/PROJECT.md` §10 (observability principles, "Secrets must never be logged"); `ai/SPECIFICATION.md` §20 ("Use structured logs … Do not log secrets"); `ai/ROADMAP.md` Milestone 10 (`TASK-089 Structured logging`); `ai/AGENTS.md` §6/§9/§10; `ai/AGENT_WORKFLOW.md` §8. The sole ADR (`docs/adr/ADR-001-kafka-topic-configuration.md`) is not applicable to this logging change.

## 2. Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| Machine-readable logs with `service`/`environment`/`timestamp`/`level` | ✅ Met | `StructuredFormatter.format()` emits a JSON object with `timestamp`, `level`, `logger`, `message`, `service`, `environment`. |
| Centralized configuration across core services | ✅ Met | `libs/observability/logging_config.py` provides `setup_logging()`; all five pipeline service entry points call it (`services/ingestion/__main__.py`, `processor/__main__.py`, `raw-writer/consumer.py`, `lake-writer/consumer.py`, `warehouse-loader/runner.py`). |
| Safe correlation context | ✅ Met (mechanism) | `correlation_id_var: ContextVar[str | None]`, `set_correlation_id()`, `get_correlation_id()`; included in the log entry only when set. Not yet wired into any service (see N1). |
| Exception conventions | ✅ Met | `record.exc_info` renders a formatted traceback under the `exception` field; `monitoring/README.md` documents `logger.exception(...)`. |
| Avoid secrets | ✅ Met | No secret/logging change introduces or emits credentials; no call site logs secrets. (No automated redaction — see N6.) |
| Avoid excessive payloads | ⚠️ Partial | See F1 — the raw-writer/lake-writer DLQ sinks log the full event envelope. |
| Avoid duplicate logging | ✅ Met | Each service now configures a single `StreamHandler` replacing `basicConfig`; no duplicated handlers. |
| No unrelated architecture changes / secrets / new dependencies | ✅ Met | No new Python dependency, no secret, no architecture/contract change; only entry-point logging setup is altered. |
| Instrumentation failure must not alter processing semantics | ✅ Met | The change is a pure logging-configuration substitution; consumer loops, offset-commit, and at-least-once semantics are untouched. |
| Deterministic tests / quality checks | ✅ Met | 10 unit tests added; ruff/format/mypy clean (details in §4). |

## 3. Git Diff Review

**Range:** `7d6318b9...ab6eaba` — 1 commit, 8 files, +405/−18.

Files changed:

- `libs/observability/logging_config.py` (new, 139 lines) — `StructuredFormatter`, `setup_logging`, `set_correlation_id`/`get_correlation_id`.
- `monitoring/README.md` (+82) — documents the JSON format, standard fields, usage, and exception handling.
- `services/ingestion/__main__.py`, `services/processor/__main__.py`, `services/raw-writer/consumer.py`, `services/lake-writer/consumer.py`, `services/warehouse-loader/runner.py` — replace `logging.basicConfig(...)` with `setup_logging(service_name=...)`; add the import.
- `tests/test_logging_config.py` (new, 174 lines) — formatter/setup/correlation unit tests.

**Scope correctness:** All changes belong to TASK-089. No unrelated task changes are mixed in.

**Unrelated/accidental changes:** None observed.

**Architectural changes:** None. Service boundaries, event contract, Kafka/persistence semantics, and data-lake/warehouse/API ownership are unchanged.

**Dependency/config changes:** None. No new Python dependency; no Compose/Helm/CI change.

**Debug/temp/dead code/secrets:** No debug prints, temp files, or generated artifacts. No credentials, tokens, or payload fields were introduced by this diff (the pre-existing DLQ envelope logging noted in F1 is not part of this diff).

**Branch and task isolation:** Reviewed HEAD is on `feature/TASK-089`; the range contains exactly one commit and it belongs to TASK-089. Working tree was clean at review time.

## 4. Test and Verification Review

**Tests added/changed:**

- `tests/test_logging_config.py` (10 tests): standard-field presence; `extra` field passthrough; non-JSON-serializable `extra` → string; exception/traceback inclusion; correlation ID present when set and absent when cleared; `setup_logging` configures root logger with `StructuredFormatter`; default-environment fallback; `set`/`get` correlation ID; default `None`.

**Independently verified (executed by reviewer):**

- `python -m pytest tests/test_logging_config.py -q` → **10 passed in 0.24s**.
- `python -m ruff check libs/observability/logging_config.py tests/test_logging_config.py services/ingestion/__main__.py services/lake-writer/consumer.py services/processor/__main__.py services/raw-writer/consumer.py services/warehouse-loader/runner.py` → **All checks passed**.
- `python -m ruff format --check <same 7 files>` → **7 files already formatted**.
- `python -m mypy libs/observability/logging_config.py tests/test_logging_config.py` → **Success: no issues found in 2 source files**.

**Implementation evidence reviewed (not rerun):** None beyond the above; the commit is a single self-contained change with no reported CI artifacts inside the range.

**Unverified:**

- **`python -m pytest -m integration` was not run**, and no implementation evidence of such a run exists in the change set. The task touches Kafka-consuming service entry points, but the actual diff is a pure logging-configuration substitution (`basicConfig` → `setup_logging`) that does not alter Kafka consumer, offset-commit, persistence, or at-least-once semantics. Integration risk is therefore low, but the end-to-end "structured JSON emitted from a running consumer" path is not integration-verified.

## 5. Findings

### F1 — Moderate — DLQ sinks log the full event envelope, contradicting the "avoid excessive payloads" objective

- **Files:** `services/raw-writer/consumer.py` (`_build_dead_letter_sink`, ~line 46), `services/lake-writer/consumer.py` (`_build_dead_letter_sink`, ~line 46).
- **Problem:** Both dead-letter sinks call `logger.error("…_dlq_failed", extra={"envelope": str(envelope)})`, emitting the entire deserialization/processing envelope. TASK-089's objective explicitly includes "avoid … excessive payloads", and the new JSON formatter now renders that full payload as a structured, machine-readable field rather than a formatted string. This behavior predates TASK-089 (the diff only replaced `basicConfig`), but the task touched both files without addressing the one concrete excessive-payload case in the codebase.
- **Impact:** Unbounded, potentially large log records containing complete event payloads; noisy and costly at scale. No secrets are involved (product/observation data only).
- **Recommendation:** Reduce the envelope to a bounded, identifying subset (e.g., topic/partition/offset/key or a length-capped digest) instead of the full `str(envelope)`, or document why the full envelope is required for DLQ forensics.

### F2 — Minor — `StructuredFormatter` leaks spurious `name` and `taskName` fields

- **File:** `libs/observability/logging_config.py:60-88` (the `record.__dict__` skip list).
- **Problem:** The skip tuple omits the LogRecord attributes `name` and `taskName`. On Python 3.12 a `LogRecord` always carries `name` (duplicating the already-emitted `logger` field) and `taskName` (defaulting to `None`). Independently reproduced: formatting a simple record yields `{"logger": "x", "name": "x", "taskName": null, ...}`.
- **Impact:** Every structured log entry carries a redundant `name` and a constant `taskName: null`, slightly undermining the "standardized fields" goal. No functional impact.
- **Recommendation:** Add `"name"` and `"taskName"` to the skip list (or explicitly map `name` into `logger` and drop both), and add a test asserting the absence of `name`/`taskName` in the output.

### F3 — Minor — Stale `logging.basicConfig` duplicate left in `services/lake-writer/__init__.py`

- **File:** `services/lake-writer/__init__.py:74`.
- **Problem:** `services/lake-writer/__init__.py` still contains a full `run_consumer()` that calls `logging.basicConfig(...)` and lacks the metrics/lag wiring. This is dead code — the deployed entry point is `python -m services.lake-writer.consumer` (confirmed by `tests/test_kubernetes_manifests.py` and the TASK-080 review) — and the `__init__.py` copy was already flagged as redundant in the TASK-022 review.
- **Impact:** Confusing maintenance surface; a stale unstructured-logging entry point remains in the tree, contrary to the "standardize logging" goal. Not executed, so no runtime impact.
- **Recommendation:** Reduce `__init__.py` to a minimal package init (or remove the duplicated `run_consumer`), so no stale `basicConfig` remains anywhere in the repository.

### F4 — Minor — `test_setup_logging_uses_default_environment` is environment-sensitive

- **File:** `tests/test_logging_config.py:155-159`.
- **Problem:** The test calls `setup_logging(service_name="test-service")` (no `environment`) and asserts `formatter.environment in ["dev", "test", "prod"]`. If `APP_ENVIRONMENT` is set to any other value (e.g., `ci`, `staging`) in the test environment, the assertion fails even though the code is correct.
- **Impact:** Flaky/`environment-dependent` test; does not affect production code.
- **Recommendation:** Pass `environment="test"` explicitly, or assert the value equals `os.environ.get("APP_ENVIRONMENT", "dev")` rather than a fixed allow-list.

## 6. Non-Defect Observations

- **N1 — Correlation context is a dormant mechanism.** `set_correlation_id`/`get_correlation_id` are implemented and tested, but no service calls `set_correlation_id`, so no production log will carry a `correlation_id` until it is wired into request/event flows. This is consistent with the roadmap (TASK-090 OpenTelemetry, TASK-091 distributed tracing own the trace-propagation work), so it is an observation, not a defect.
- **N2 — SPECIFICATION §20 field naming differs from the implementation.** SPECIFICATION lists `error` and `event_id`/`source`/`operation`/`trace_id` as example contextual fields. The formatter emits `exception` (not `error`) for tracebacks and standardizes only `service`/`environment`/`timestamp`/`level`/`message`/`logger`/`correlation_id`; `event_id`/`source`/`operation` appear only if passed via `extra`. The task specification narrows the required standard fields, so this is acceptable, but the `error` vs `exception` naming is worth aligning with SPECIFICATION eventually.
- **N3 — API and Airflow are not migrated.** The FastAPI service (uvicorn) and the Airflow DAGs still use their own logging (`logging.getLogger(__name__)`, uvicorn's handlers). Given the task scope ("core services") and the deferral of tracing to TASK-090/091, this is defensible, but "all platform services" would not yet be fully standardized.
- **N4 — `setup_logging` mutates the global root logger.** It clears all root handlers and adds a stdout `StreamHandler`, which persists across the pytest process; any later test that logs at INFO+ will emit JSON to stdout. No test in the current suite appears to depend on the prior root configuration, but this is a global-state side effect worth noting for future test isolation.
- **N5 — Commit attribution.** The single commit is authored by `Workflow Test <workflow@example.invalid>`, the same automated identity noted in the TASK-088 review (N1). Worth confirming intended attribution before merge.
- **N6 — No automated secret redaction.** The formatter trusts callers to not pass secrets via `extra`; there is no field-value filtering. This matches the platform convention ("do not log secrets" is a usage rule), but any future structured logging of request/response bodies would need an explicit redaction decision.

## 7. Verdict

**`APPROVED WITH NON-BLOCKING FINDINGS`**

The core deliverable is in place and correct. Structured JSON logging is centralized in `libs/observability/logging_config.py`, emits the required `service`/`environment`/`timestamp`/`level` fields plus arbitrary `extra` context, defines a clear exception convention, and provides a safe `ContextVar`-based correlation mechanism. All five pipeline service entry points are migrated from `basicConfig` to `setup_logging`, the change is a pure logging substitution that does not alter Kafka, persistence, or at-least-once processing semantics, and no secrets, new dependencies, or architecture changes were introduced.

Verification is solid at the unit level: the 10 structured-logging tests pass, and ruff (lint + format) and mypy are clean on the changed files — all independently executed by this reviewer. The only unverified dimension is the optional Kafka integration run, which is low-risk here because the diff does not change any consumer/commit/persistence behavior.

The remaining findings are non-blocking: one Moderate (the pre-existing full-envelope DLQ logging conflicts with the task's own "avoid excessive payloads" objective — F1) and three Minor (spurious `name`/`taskName` fields, a stale `basicConfig` duplicate in the lake-writer package init, and an environment-sensitive test). None of these compromise the correctness of the structured-logging implementation or the event pipeline.
