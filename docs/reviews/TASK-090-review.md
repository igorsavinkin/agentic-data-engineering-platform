# TASK-090 Review — OpenTelemetry

## 1. Review Header

- **Task ID:** TASK-090
- **Review date:** 2026-09-20
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `2620cb092b62a4c773d3bb0339aaa600c6589a2b..00b6df6bc94130eb75a93e1713e14a640e79fa33` (i.e. `main..feature/TASK-090`)
- **Reviewed HEAD (commit):** `00b6df6bc94130eb75a93e1713e14a640e79fa33` on `feature/TASK-090`
- **Merge base / main HEAD:** `2620cb092b62a4c773d3bb0339aaa600c6589a2b`
- **Commits reviewed:**
  - `00b6df6` — `feat(TASK-090): OpenTelemetry foundation with resource identity and safe attributes`
- **Scope:** A shared OpenTelemetry setup library (`libs/observability/otel_config.py`) providing consistent resource identity (`service.name`/`service.version`/`deployment.environment`), configurable exporters (OTLP gRPC / console / none), bounded safe-attribute helpers (`truncate_attribute`, `safe_attributes`), and a no-op tracer fallback; wiring of `setup_opentelemetry()` into all six platform services; an OpenTelemetry Collector added to Docker Compose; Helm `values.yaml` OTel section; collector config (`monitoring/otel-collector-config.yaml`); documentation in `monitoring/README.md`; and unit tests in `tests/test_otel_config.py`.
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

> Note on the supplied Git range: the prompt specified `2620cb0...2620cb0` (empty — same commit). The actual TASK-090 work lives on `feature/TASK-090` in the `ai-platform-task-090` worktree; this review inspected `main..feature/TASK-090` (one commit, `00b6df6`).

Sources of authority consulted: `ai/tasks/TASK-090-opentelemetry.md`; `ai/PROJECT.md` §2/§10 ("Prometheus and Grafana for metrics/visualization … OpenTelemetry for tracing", "Secrets must never be logged"); `ai/SPECIFICATION.md` §20 ("Use structured logs … Do not log secrets") and §Tracing ("OpenTelemetry should provide distributed traces across major service boundaries"); `ai/ROADMAP.md` Milestone 10 (`TASK-090 OpenTelemetry`, `TASK-091 Distributed tracing`); `ai/AGENTS.md` §6/§9/§10; `ai/AGENT_WORKFLOW.md`; the adjacent `ai/tasks/TASK-091-distributed-tracing.md` (defers actual span instrumentation / local trace viewing to TASK-091). The sole ADR (`docs/adr/ADR-001-kafka-topic-configuration.md`) is not applicable.

## 2. Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| Shared OpenTelemetry configuration | ✅ Met | `libs/observability/otel_config.py` centralizes `OTelSettings` and `setup_opentelemetry()`; exported via `libs/observability/__init__.py`. |
| Consistent resource identity | ✅ Met | `Resource.create({"service.name", "service.version", "deployment.environment"})`; every service passes a distinct `service_name`. |
| Configurable exporters | ✅ Met | `otel_exporter_type` supports `otlp` (gRPC), `console`, and `none`; endpoint configurable via `APP_OTEL_EXPORTER_ENDPOINT`. |
| Bounded safe attributes | ✅ Met | `truncate_attribute` (256-char nominal bound) and `safe_attributes` (sensitive-key filtering, max 128 attributes, non-serializable → string). |
| Prepare meaningful service boundaries | ✅ Met | All six services call `setup_opentelemetry(OTelSettings(service_name=...))` (api, ingestion, processor, raw-writer, lake-writer, warehouse-loader). |
| Instrumentation failure must not alter processing semantics | ✅ Met | `setup_opentelemetry` is a startup-only side effect wrapped in `try/except ImportError`; `get_tracer` returns a `_NoOpTracer` fallback; no change to consumer loops, offset commits, or at-least-once semantics. |
| Never expose secrets | ✅ Met | `safe_attributes` filters `password`/`secret`/`token`/`api_key`/`authorization`/etc.; no secrets committed; sensitive values never logged. |
| Keep telemetry attributes bounded / low-cardinality | ✅ Met | Attribute length and count caps; resource attributes are fixed low-cardinality keys. |
| Provisioning version-controlled and reproducible | ⚠️ Partial | Compose collector config is version-controlled and reproducible. The Helm `opentelemetry` values have **no chart template** and are not wired to any service env vars — see F1. |
| Deterministic validation/tests | ✅ Met | 24 unit tests added; ruff lint/format and mypy clean (details in §4). |
| No unrelated architecture changes / secrets / new dependencies | ✅ Met | Changes are additive observability wiring only; three OpenTelemetry packages added to `requirements.txt` (all directly used by the feature). |

## 3. Git Diff Review

**Range:** `2620cb0..feature/TASK-090` — 1 commit, 15 files, +701/−2.

Files changed:

- `libs/observability/otel_config.py` (new, 279 lines) — `OTelSettings`, `truncate_attribute`, `safe_attributes`, `get_tracer`, `_NoOpTracer`/`_NoOpSpan`, `setup_opentelemetry`.
- `libs/observability/__init__.py` (+12) — exports the new symbols.
- `services/api/app.py`, `services/ingestion/__main__.py`, `services/processor/__main__.py`, `services/raw-writer/consumer.py`, `services/lake-writer/consumer.py`, `services/warehouse-loader/runner.py` (+2 each) — add `setup_opentelemetry(OTelSettings(service_name=...))`.
- `monitoring/otel-collector-config.yaml` (new, 27 lines) — OTLP gRPC/HTTP receiver, `memory_limiter` + `batch` processors, `debug` exporter.
- `docker-compose.yml` (+14) — adds `otel-collector` service on the `platform` network.
- `helm/ai-data-platform/values.yaml` (+26) — adds `opentelemetry:` section (collector image/ports/resources + per-service `config`).
- `monitoring/README.md` (+72) — documents the SDK, config variables, Compose and Helm flows, and service integration.
- `requirements.txt` (+5) — adds `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-grpc` (`>=1.25,<2`).
- `pyproject.toml` (+1/−1) — adds `opentelemetry.*` to the mypy `ignore_missing_imports` override.
- `tests/test_otel_config.py` (new, 252 lines) — unit tests.

**Scope correctness:** All changes belong to TASK-090. No unrelated task changes are mixed in.

**Unrelated/accidental changes:** None observed. The `pyproject.toml` mypy override and `requirements.txt` additions are directly tied to the new dependency.

**Architectural changes:** None. Service boundaries, the canonical event contract, Kafka/persistence semantics, and data-lake/warehouse/API ownership are unchanged. `setup_opentelemetry` is added only at each service's existing entry point.

**Dependency/config changes:** Three OpenTelemetry packages are introduced, all used by the implementation (SDK + API + OTLP gRPC exporter). Compose and Helm config changes are scoped to observability. No CI/secret/network-policy changes.

**Debug/temp/dead code/secrets:** No debug prints, temp files, or generated artifacts. No credentials, tokens, or payload fields introduced. The `debug` exporter in the collector config is an intentional local-development default, not leftover debugging code.

**Branch and task isolation:** Reviewed HEAD is on `feature/TASK-090`; the range contains exactly one commit belonging to TASK-090. Working tree was clean at review time. The task was implemented on the correct `feature/TASK-090` branch.

## 4. Test and Verification Review

**Tests added/changed:**

- `tests/test_otel_config.py` (24 tests): `truncate_attribute` (short/exact/over/long/custom-max); `safe_attributes` (empty, `None` preservation, primitives, sensitive-key filtering case-insensitive, long-string truncation, non-serializable → string, 128-attribute cap); `OTelSettings` (defaults, `APP_` env override); `_NoOpTracer`/`_NoOpSpan` (span type, context manager, no-op methods); `get_tracer` (fallback when not installed, delegates when installed); `setup_opentelemetry` (disabled no-op, missing SDK warning, console exporter, OTLP-missing-endpoint warning, unknown exporter type warning).

**Independently verified (executed by reviewer):**

- `python -m pytest tests/test_otel_config.py -q` → **24 passed in 0.61s** (run against the worktree checkout; the OTel SDK itself is not installed in the environment, which is fine because the tests mock the `opentelemetry` modules).
- `python -m ruff check <9 changed Python files>` → **All checks passed**.
- `python -m ruff format --check <9 changed Python files>` → **9 files already formatted**.
- `python -m mypy libs/observability/otel_config.py tests/test_otel_config.py` → **Success: no issues found in 2 source files**.

**Implementation evidence reviewed (not rerun):** None beyond the above; the commit is a single self-contained change with no reported CI artifacts inside the range.

**Unverified:**

- **`python -m pytest -m integration` was not run**, and no implementation evidence of such a run exists. The task does not add or modify any integration-marked test. The change is startup-only observability wiring plus a new Compose service; it does not alter Kafka consumer/commit, MinIO/S3, or PostgreSQL behavior, so integration risk to existing semantics is low. However, the **end-to-end OTLP path (service → collector → debug exporter)** is not exercised by any test, which is a coverage gap for the "reproducible observability artifacts" goal (see N2).

## 5. Findings

### F1 — Moderate — Helm `opentelemetry` values are dead config; README documents a non-functional `helm --set` flow

- **Files:** `helm/ai-data-platform/values.yaml` (new `opentelemetry:` section, lines ~434-458), `monitoring/README.md` ("Kubernetes" subsection).
- **Problem:** The chart adds `opentelemetry.enabled`, `opentelemetry.collector.*`, and `opentelemetry.config.*` values, but there is **no Helm template** that renders them. Unlike `prometheus`/`grafana` (which have `templates/monitoring/*-deployment.yaml` guarded by `{{- if .Values.<component>.enabled }}`), there is no `otel-collector` Deployment/Service/ConfigMap template, and `opentelemetry.config.exporterEndpoint`/`exporterType`/`enabled` are not wired into any ConfigMap or service env var. Consequently `helm upgrade --install … --set opentelemetry.enabled=true --set opentelemetry.config.enabled=true` (as documented in `monitoring/README.md`) renders **no resources**, and services deployed via Helm never receive `APP_OTEL_ENABLED`/`APP_OTEL_EXPORTER_ENDPOINT`.
- **Impact:** The Kubernetes tracing path is not reproducible; the README's Kubernetes instructions and the "Services will automatically export traces to `http://otel-collector:4317` when `APP_OTEL_ENABLED=true`" claim are misleading. The Compose path works, so the foundation is still demonstrable locally.
- **Recommendation:** Either add a collector Deployment/Service/ConfigMap template (plus env-var wiring for the `opentelemetry.config.*` values, e.g. into `platform-config` or the per-service Deployments), or explicitly mark the Helm OTel section and the README Kubernetes flow as deferred to TASK-091 and remove the implication that it is operational today.

### F2 — Minor — `truncate_attribute` exceeds its documented 256-char bound

- **File:** `libs/observability/otel_config.py` (`truncate_attribute`, `_MAX_ATTRIBUTE_LENGTH = 256`); `monitoring/README.md` ("bounded string truncation (256 chars)").
- **Problem:** When a value is longer than `max_length`, the function returns `value[:256] + "...[truncated]"`, i.e. 256 + 14 = **270 characters**. The docstring, README, and the "bounded attributes" objective all describe a 256-character cap, which is not actually honored (and the test `test_long_string_truncated` asserts 270, so the deviation is intentional).
- **Impact:** A minor bound inconsistency; attributes can be up to 270 chars rather than 256. Not a high-cardinality or security risk, but the stated guarantee is slightly inaccurate.
- **Recommendation:** Truncate to `max_length - len(suffix)` so the total stays ≤ 256, or update the documentation/tests to state the true maximum (270). Keeping the total strictly bounded is preferable for the "bounded safe attributes" objective.

### F3 — Minor — `safe_attributes` sensitive-key matching uses substring matching and over-filters

- **File:** `libs/observability/otel_config.py` (`_SENSITIVE_KEYS`, `safe_attributes`).
- **Problem:** The filter uses `any(sensitive in key_lower for sensitive in _SENSITIVE_KEYS)`, so any key *containing* a sensitive substring is dropped — including legitimate bounded keys such as `session_count`, `token_count`, or `sessions_total`. This is a false positive in the safe direction (no leak), but it can silently strip non-sensitive attributes the operator intended to trace.
- **Impact:** Potential loss of legitimate low-cardinality attributes; no security or correctness harm.
- **Recommendation:** Match on full key tokens (e.g. split on `_`/`-`/`.` and compare exact tokens), or explicitly document that substring matching intentionally trades precision for safety.

### F4 — Minor — `setup_opentelemetry` is called inside `create_app()` (factory), and README's "after setup_logging()" claim is inaccurate for the API

- **Files:** `services/api/app.py` (call inside `create_app`, ~line 50), `monitoring/README.md` ("Each service calls `setup_opentelemetry(…)` after `setup_logging()`").
- **Problem:** For the API, `setup_opentelemetry()` is invoked inside the `create_app()` factory rather than at the entry point, and the API service does not call `setup_logging()` at all. Every call to `create_app()` (which happens at least once per app construction, and multiple times in tests) re-runs global OTel initialization and re-calls `trace.set_tracer_provider(...)`. It is harmless when OTel is disabled (default), but with OTel enabled it re-creates the global `TracerProvider` on each app construction. The README's blanket statement is therefore not accurate for the API service.
- **Impact:** A global-state side effect inside a factory; repeated provider re-initialization in multi-instance/test contexts. No functional impact on the disabled-by-default path.
- **Recommendation:** Move the `setup_opentelemetry(OTelSettings(service_name="api"))` call to `services/api/__main__.py` (next to uvicorn startup), or guard it so it runs once. Correct the README wording to reflect that the API initializes OTel in `create_app` (or at startup) rather than "after `setup_logging()`".

### F5 — Minor — `.env.example` does not document the new Compose/OTel variables

- **File:** `.env.example`.
- **Problem:** The Compose service references `${OTEL_COLLECTOR_GRPC_PORT:-4317}` and `${OTEL_COLLECTOR_HTTP_PORT:-4318}`, and the services read `APP_OTEL_*` variables, but none of these are listed in `.env.example` (which already documents the other Compose host-port and `APP_*` variables).
- **Impact:** Minor discoverability gap for local setup; defaults still work, so nothing breaks.
- **Recommendation:** Add commented `OTEL_COLLECTOR_GRPC_PORT`/`OTEL_COLLECTOR_HTTP_PORT` and `APP_OTEL_ENABLED`/`APP_OTEL_EXPORTER_ENDPOINT`/`APP_OTEL_EXPORTER_TYPE` entries to `.env.example` for consistency with the other infra variables.

## 6. Non-Defect Observations

- **N1 — `get_tracer`/`safe_attributes`/`truncate_attribute` are dormant utilities.** They are implemented and unit-tested, but no service calls `get_tracer` or `safe_attributes` yet. This is consistent with the roadmap: TASK-091 ("Distributed tracing") owns the actual span instrumentation and trace/correlation propagation. Observation, not a defect.
- **N2 — No end-to-end OTLP path test.** The unit suite covers the SDK-config logic, but there is no test that starts the Compose collector and asserts a trace is received/exported. This is acceptable for a "foundation" task (the local trace-viewing path is explicitly TASK-091), but it means the "observability artifacts are reproducible" claim is verified only by configuration, not by a live trace.
- **N3 — OTel is disabled by default.** `otel_enabled` defaults to `False`, so every service no-ops by default. This is a safe, correct foundation posture, but means the collector is only exercised when operators explicitly set `APP_OTEL_ENABLED=true` (Compose) or when the Helm path is actually wired (see F1).
- **N4 — OTLP exporter endpoint is logged.** The `opentelemetry_otlp_exporter_enabled` message includes `extra={"endpoint": …}`. Endpoint values here are host:port, so there is no secret exposure today; if an endpoint URL ever embeds credentials (`http://user:pass@host`), they would be emitted. Worth a future guard, but not a defect in the current shape.
- **N5 — Commit attribution.** The single commit is authored by `Workflow Test <workflow@example.invalid>`, the same automated identity noted in the TASK-088 (N1) and TASK-089 (N5) reviews. Worth confirming intended attribution before merge.

## 7. Verdict

**`APPROVED WITH NON-BLOCKING FINDINGS`**

The core deliverable is in place and correct. `libs/observability/otel_config.py` provides a shared, reusable OpenTelemetry setup with consistent resource identity (`service.name`/`service.version`/`deployment.environment`), configurable exporters (OTLP gRPC, console, none), bounded safe-attribute helpers (length + count caps, sensitive-key filtering), and a no-op fallback that guarantees instrumentation failure cannot affect processing. All six platform services are wired to initialize OTel on startup with distinct service names, the Compose collector configuration is correct and bounded (`memory_limiter` + `batch`, `debug` exporter), and the change introduces no secrets, no unrelated architecture changes, and only the three OpenTelemetry dependencies it directly uses.

Verification is solid at the unit level: all 24 OTel tests pass, and ruff (lint + format) and mypy are clean on the changed files — each independently executed by this reviewer. The one substantive gap is the Helm path: the `opentelemetry` values have no corresponding chart template and are not wired into any service env vars, so the documented `helm --set opentelemetry.enabled=true` flow does nothing (F1, Moderate). The remaining findings are Minor (an over-length truncation, over-aggressive substring filtering, factory-side-effect placement for the API, and a missing `.env.example` entry). None of these compromise correctness of the foundation or the event pipeline, and none block acceptance.
