# TASK-091 Review — Distributed Tracing

## 1. Review Header

- **Task ID:** TASK-091 — Distributed Tracing
- **Review date:** 2026-09-20
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `e9391fc9796203f4536b45799d3e9ad4c2f9a0a7..d301e925b1248c43368aab737eeac641be9a2450`
- **Reviewed HEAD (commit):** `d301e925b1248c43368aab737eeac641be9a2450` on `feature/TASK-091`
- **Merge base / prior HEAD:** `e9391fc9796203f4536b45799d3e9ad4c2f9a0a7` (the TASK-090 merge commit)
- **Commits reviewed:**
  - `e4eee9d` — `feat(TASK-091): Distributed tracing with W3C Trace Context propagation`
  - `3c8a222` — `fix(TASK-091): Address Qwen review findings (round 2)`
  - `d301e92` — `fix(TASK-091): Fix mypy type error in extract_trace_context test (F10)`
- **Scope:** W3C Trace Context propagation across service and Kafka boundaries; Kafka header injection/extraction; per-service spans at publish/consume/HTTP boundaries; log-trace correlation via `correlation_id`/`trace_id`; Jaeger local trace viewing; OTel collector → Jaeger export; Grafana Jaeger datasource; `monitoring/README.md` tracing documentation; unit tests.
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

Sources of authority consulted: `ai/tasks/TASK-091-distributed-tracing.md`; `ai/PROJECT.md` §2 and §10; `ai/SPECIFICATION.md` §20; `ai/ROADMAP.md` Milestone 10; `ai/AGENTS.md` §6/§7/§9/§10/§14; `ai/REVIEWER.md`. The sole ADR (`docs/adr/ADR-001-kafka-topic-configuration.md`) concerns Kafka topic configuration and is not directly applicable to tracing. `ai/tasks/TASK-090-opentelemetry.md` was consulted as the immediate predecessor providing `otel_config.py` primitives.

## 2. Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| Propagate trace/correlation context across meaningful service and Kafka boundaries | ✅ Met | Ingestion → `products.raw.v1` (`_publish_event` injects `traceparent` via `inject_trace_context`); `products.raw.v1` → processor/raw-writer (header extraction); processor → `products.validated.v1` → lake-writer (`_publish_validated_with_trace` wrapper + `KafkaValidatedOutputProducer.publish(headers=...)`); API HTTP boundary. |
| Provide a local trace viewing path | ✅ Met | `jaeger` all-in-one in `docker-compose.yml` (UI 16686); `otlp/jaeger` exporter in `otel-collector-config.yaml`; Grafana Jaeger datasource. |
| Document a representative trace | ✅ Met | `monitoring/README.md` "Distributed Tracing (TASK-091)" documents architecture, propagation flow, a representative trace diagram, correlation, and configuration. |
| Correlate traces with metrics/logs without changing processing semantics | ✅ Met | Processor, raw-writer, lake-writer set `correlation_id` from `trace_id`; ingestion and processor log `trace_id`. Trace↔log correlation is explicit; trace↔metric correlation is not wired (no `trace_id` in metric labels), which is consistent with the low-cardinality metric-label rule. Processing semantics (offset-commit timing, at-least-once delivery, event contract) are unchanged. |
| Observe the established architecture; do not redesign business flow for telemetry | ✅ Met | No change to consumer loops, offset-commit timing, at-least-once semantics, event contract, or service boundaries. |
| Reuse established health/freshness/data-quality/Kafka semantics | ✅ Met | Reuses `KafkaEventProducer`, `KafkaConsumer`, `KafkaValidatedOutputProducer`, structured logging, and TASK-090 `safe_attributes`. |
| Keep metric labels and telemetry attributes bounded and low-cardinality | ✅ Met (with one Minor caveat — F11) | Every span attribute passes through `safe_attributes` (length + count caps, sensitive-key filter). `event_id` is a bounded-length but high-cardinality span attribute (see F11). |
| Never expose secrets or sensitive payloads | ✅ Met | Only `source`, `event_id`, topic/partition/offset, and HTTP method/target/scheme/status are set; no payload fields; `safe_attributes` filters sensitive keys. |
| Instrumentation failure must not alter core processing semantics | ✅ Met | `inject_trace_context`/`extract_trace_context`/`get_current_trace_id`/`get_tracer` degrade to no-ops/`None` on `ImportError`; `_NoOpTracer.start_as_current_span` accepts `*args/**kwargs`; producers publish with `headers=None` when no context is present. |
| Keep dashboards/provisioning version-controlled and reproducible | ✅ Met | Compose, collector config, and Grafana datasource are all version-controlled. |
| Add deterministic validation/tests | ✅ Met | 31 OTel-config tests remain (8 trace-context helpers added, 1 removed by F10); Kafka producer/consumer plumbing exercised through mocks. |
| Run repository quality checks | ✅ Met | `ruff check`, `ruff format --check`, and full `python -m mypy` all pass (independently verified, §4). Integration suite unverified (see §4). |
| No unrelated architecture changes / secrets / unnecessary dependencies | ✅ Met | Additive observability wiring only; no new Python dependencies (OpenTelemetry was introduced in TASK-090); no secrets; `pyproject.toml`/`requirements*.txt` untouched. |

## 3. Git Diff Review

**Range:** `e9391fc..d301e92` — 3 commits, 23 files, +734/−73 (including the review artifact `docs/reviews/TASK-091-review.md`, which was committed by `3c8a222`).

Code files changed (excluding the review artifact):

- `docker-compose.yml` (+14) — adds `jaeger` all-in-one (1.62) and `otel-collector → jaeger` `depends_on`; removes the non-standard `COLLECTOR_OTLP_ENABLED_HONOUR_ENVIRONMENT_VARIABLES` env var (round-2 F9).
- `libs/common/kafka_consumer.py` (+10) — adds `ConsumerMessage.headers`; extracts headers handling both `dict` and `list[tuple]` forms of `msg.headers()` (round-2 F2 mypy fix).
- `libs/common/kafka_producer.py` (+18/−2) — `publish()` accepts optional `headers` and forwards via `produce(**kwargs)`.
- `libs/common/kafka_validated_producer.py` (+16/−2) — `publish()` accepts optional `headers` (round-2 F1 fix).
- `libs/observability/__init__.py` (+6) — exports `inject_trace_context`, `extract_trace_context`, `get_current_trace_id`.
- `libs/observability/otel_config.py` (+69) — adds `inject_trace_context`, `extract_trace_context`, `get_current_trace_id`, `_DictSetter`, `_DictGetter`.
- `monitoring/README.md` (+109) — distributed-tracing architecture/flow/representative-trace/correlation/config.
- `monitoring/grafana/datasources/prometheus.yml` (+10) — adds Jaeger datasource.
- `monitoring/otel-collector-config.yaml` (+6/−6) — adds `otlp/jaeger` exporter to traces pipeline.
- `services/api/app.py` (+29/−6) — HTTP tracing middleware with `X-Trace-Id` response header.
- `services/ingestion/runner.py` (+96/−46) — `ingestion.publish` span, header injection, `trace_id` in logs; removed stray `mimeType` attribute (round-2 F6).
- `services/lake-writer/consumer.py` (+28) — `lake-writer.process_message` span, header extraction, `correlation_id` (round-2 F3).
- `services/processor/__main__.py` (+60/−26) — `processor.process_batch` span, header extraction, `correlation_id`, and `_publish_validated_with_trace` wrapper (round-2 F1).
- `services/raw-writer/consumer.py` (+28) — `raw-writer.process_message` span, header extraction, `correlation_id` (round-2 F3).
- `tests/*` — `MockProducer.publish` signatures gain optional `headers` in five test files; `test_kafka_producer.py` and `test_validated_producer.py` assertions adapted to `produce(**kwargs)`; `test_otel_config.py` gains 8 tests (then one removed by F10).

**Scope correctness:** All code changes belong to TASK-091. No unrelated task changes are mixed in.

**Unrelated/accidental changes:** None. The `MockProducer.publish` signature updates are a necessary consequence of the new `publish(headers=...)` signature.

**Architectural changes:** None. Service boundaries, canonical event contract, Kafka/persistence semantics, and data-lake/warehouse/API ownership are unchanged. `services/warehouse-loader` and the Airflow layer are intentionally not modified.

**Dependency/config changes:** No new Python dependencies. Compose and monitoring config changes are scoped to observability. `pyproject.toml`/`requirements*.txt` are untouched.

**Debug/temp/dead code/secrets:** No debug prints, temp files, or generated artifacts. No credentials or payload fields. The `debug` exporter retained in the collector config is the intentional local default from TASK-090.

**Branch and task isolation:** Reviewed HEAD is on `feature/TASK-091`; the range contains exactly three commits, all belonging to TASK-091. Working tree contains only the (now overwritten) review-file modification.

**Process note:** `docs/reviews/TASK-091-review.md` was committed into the feature branch as part of `3c8a222`, and a stale round-2 draft was left uncommitted in the working tree. Both reflected an earlier reviewed HEAD (`e4eee9d` / `3c8a222`) and a `CHANGES REQUIRED` verdict that is now superseded. A review report is a review artifact, not implementation code; this report overwrites those stale versions. See N6.

## 4. Test and Verification Review

**Tests added/changed:**

- `tests/test_otel_config.py` — trace-context helper tests: `inject_trace_context` (no-OTel no-op; populates carrier with `traceparent` bytes), `extract_trace_context` (no-OTel `None`; calls propagator), `get_current_trace_id` (no-OTel `None`; no active span `None`; hex 32-char trace id). 31 tests remain after F10 removed `test_extract_handles_string_values`.
- `tests/test_kafka_producer.py` — two assertions adapted to the `produce(**kwargs)` call shape; no header-forwarding assertion added.
- `tests/test_validated_producer.py` — one assertion adapted to `produce(**kwargs)`.
- Five test files — `MockProducer.publish` signature updated to accept `headers`.

**Independently verified (executed by reviewer):**

- `python -m pytest -q` → **1923 passed, 28 skipped, 135 deselected** in 95.55s (deselected = `integration` marker per `addopts = "-m 'not integration'"`).
- `python -m ruff check .` → **All checks passed**.
- `python -m ruff format --check .` → **393 files already formatted**.
- `python -m mypy` (full configured scope `files = ["scripts", "tests", "libs"]`) → **Success: no issues found in 182 source files** (F10 fix confirmed).

**Implementation evidence reviewed (not rerun):** None beyond the above; the three commit messages ("8 new tests … 32 total otel tests", "Address Qwen review findings (round 2)", "Fix mypy type error … (F10)") are consistent with the independently executed results.

**Unverified:**

- **`python -m pytest -m integration` was not verified.** An attempt was made by the reviewer but **timed out after 600s with no output**. The Docker data-plane services (Kafka, MinIO, PostgreSQL) were running, but the observability stack (`jaeger`, `otel-collector`, Prometheus, Grafana) was **not** running. No implementation evidence of a successful integration run exists in any of the three commits. The 135 integration tests are pre-existing infrastructure tests (predominantly PostgreSQL/warehouse); the tracing-specific header plumbing is exercised only through mocks in the unit suite.
- **No end-to-end live trace test.** No test starts the Compose collector + Jaeger and asserts a trace is received/exported, and no test round-trips a `traceparent` through a real Kafka produce/consume. The "reproducible observability artifacts" claim is verified by configuration and unit tests only.

## 5. Findings

### F4 — Moderate — Batch trace attribution uses only the first message's headers

- **File:** `services/processor/__main__.py` (`process_batch`).
- **Problem:** `process_batch` derives the parent context and `correlation_id` solely from `messages[0].headers`. If a batch contained messages from multiple raw traces, every message after the first would be mis-attributed to the first message's trace.
- **Impact:** Latent correctness gap for the "correlate traces" objective. Not currently triggered because `run_consumer` invokes `process_batch([msg], pipeline)` (single-message batches), but the function is a general batch API and mis-attribution would appear as soon as batching is enabled.
- **Recommendation:** Either document/guarantee single-message batches for trace correctness, or instrument at per-message granularity (or add `SpanLinks`) when multi-message batches are processed.

### F5 — Minor — `correlation_id` ContextVar is set but never reset

- **Files:** `services/processor/__main__.py`, `services/raw-writer/consumer.py`, `services/lake-writer/consumer.py` (via `set_correlation_id` in `libs/observability/logging_config.py`).
- **Problem:** `set_correlation_id(trace_id)` is called inside the span, but there is no corresponding reset to `None` when the span exits or when a message has no trace. `set_correlation_id` sets a `ContextVar` and does not return a reset token.
- **Impact:** Out-of-span log records (lag sampling, sleeps, shutdown, DLQ) can carry a stale `correlation_id` from a prior message, slightly degrading correlation accuracy. No security or processing-correctness impact.
- **Recommendation:** Reset to `None` after the span (e.g. in a `finally`), or have `set_correlation_id` return a token and use `ContextVar.reset(token)`.

### F7 — Minor — No unit tests verify header forwarding/extraction at the producer/consumer boundary

- **Files:** `tests/test_kafka_producer.py`, `tests/test_kafka_consumer.py`.
- **Problem:** The core of the task — Kafka header injection/extraction — is unit-tested only at the OTel-helper level (`inject_trace_context`/`extract_trace_context` with mocked OTel). No test asserts that `KafkaEventProducer.publish(headers=[("traceparent", ...)])` forwards those headers to `Producer.produce(...)`, nor that `KafkaConsumer` populates `ConsumerMessage.headers` from `msg.headers()`. The `test_kafka_producer.py` changes only adapted assertions for the `produce(**kwargs)` call shape.
- **Impact:** Coverage gap on the primary deliverable; a regression in header plumbing could pass the suite unnoticed.
- **Recommendation:** Add a focused unit test for `KafkaEventProducer.publish(headers=...)` and one for `ConsumerMessage.headers` population (e.g. mock `msg.headers()` to return `[("traceparent", b"...")]` and assert `headers == {"traceparent": b"..."}`).

### F8 — Minor — `.env.example` omits the new Jaeger and OTel Compose/service variables

- **File:** `.env.example`.
- **Problem:** `docker-compose.yml` references `${JAEGER_UI_PORT:-16686}` and `${JAEGER_OTLP_GRPC_PORT:-4319}`, and (from TASK-090) `${OTEL_COLLECTOR_GRPC_PORT:-4317}`/`${OTEL_COLLECTOR_HTTP_PORT:-4318}` plus the `APP_OTEL_*` service variables, none of which are listed in `.env.example`.
- **Impact:** Minor discoverability gap for local setup; defaults still work. Carries forward the TASK-090 `.env.example` gap.
- **Recommendation:** Add commented `JAEGER_UI_PORT`/`JAEGER_OTLP_GRPC_PORT`, the OTel collector ports, and `APP_OTEL_*` entries for consistency with the other infra variables.

### F11 — Minor — `event_id` span attribute is high-cardinality

- **File:** `services/ingestion/runner.py` (`_publish_event`).
- **Problem:** `event_id` is a unique-per-event identifier set as a span attribute (`safe_attributes({"source": ..., "event_id": ...})`). `safe_attributes` bounds length and count but does **not** bound cardinality, despite its docstring claiming to "prevent high-cardinality … attributes". The task's observability rule is "Keep metric labels and telemetry attributes bounded and low-cardinality."
- **Impact:** Distinct `event_id` values accumulate as span attribute values in the trace backend. Bounded in length, and a single attribute, but still high-cardinality; the risk is lower than for metric labels (no time-series explosion) but the implementation does not fully satisfy the letter of the low-cardinality rule.
- **Recommendation:** Either document that `event_id` is intentionally retained for trace→event correlation (a single bounded attribute), or hash/truncate it for the span and rely on `trace_id` for correlation.

### F12 — Minor — F10 fix removed a test, leaving the string-value branch of `extract_trace_context` untested

- **Files:** `tests/test_otel_config.py` (removed `test_extract_handles_string_values`); `libs/observability/otel_config.py` (`extract_trace_context`).
- **Problem:** `d301e92` resolved the mypy error by deleting the test that passed `dict[str, str]` to a function typed `dict[str, bytes]`. The function still contains an `else: headers[key] = str(value)` branch for non-`bytes` values, which is now untested (and is unreachable per the declared type). The commit's rationale is valid (the test exercised a path mypy prevents at compile time), but the resolution removes coverage rather than reconciling the signature with the implemented behavior.
- **Impact:** Minor coverage reduction; the defensive `str()` branch is dead under the current annotation. No runtime impact.
- **Recommendation:** Either broaden the signature to `dict[str, str | bytes]` and restore a test, or remove the now-dead `else` branch to keep code and type intent aligned.

## 6. Non-Defect Observations

- **N1 — DLQ path is not trace-propagated.** `KafkaDeadLetterProducer.publish` has no `headers` support, so invalid events routed to `products.invalid.v1` carry no `traceparent`. This is a diagnostic path rather than a major canonical-pipeline boundary, so it is noted rather than flagged.
- **N2 — Grafana datasource file naming.** The Jaeger datasource was added to `monitoring/grafana/datasources/prometheus.yml`, now a misnomer since it provisions both Prometheus and Jaeger. Cosmetic only.
- **N3 — Trace coverage ends at Silver/lake-writer.** The warehouse-loader (Gold → PostgreSQL) and the Airflow batch layer (Silver → Gold) are not instrumented. Consistent with the task's streaming-path focus and the absence of a Kafka boundary there, but relevant to the broader "distributed traces across major service boundaries" goal.
- **N4 — OTel disabled by default.** `otel_enabled` defaults to `False`, so the tracing path is inert unless `APP_OTEL_ENABLED=true`. Safe posture, but combined with the absence of a live-trace test, the end-to-end behavior is not exercised in CI.
- **N5 — Commit attribution.** All three commits are authored by `Workflow Test <workflow@example.invalid>`, consistent with prior TASK-088/089/090 reviews. Worth confirming intended attribution before merge.
- **N6 — Prior review reports committed into the branch.** The round-1 review was committed by `3c8a222`, and a stale round-2 draft was left uncommitted in the working tree. Review artifacts ideally live outside the feature branch; this file now contains the current review.
- **N7 — API inbound HTTP trace context is not extracted.** The API middleware creates a span per request and emits `X-Trace-Id` outbound, but does not extract an inbound `traceparent` from request headers. External callers therefore cannot continue an existing trace into the API. Not required by the task's Kafka-centric objective, but a natural extension for full HTTP-boundary propagation.
- **N8 — `services/` is outside the configured mypy scope.** `pyproject.toml` sets `[tool.mypy] files = ["scripts", "tests", "libs"]`, so the new service-level tracing code (`services/*`) is not type-checked by the repository's mypy gate. This is a pre-existing config choice (inherited from TASK-090), not a TASK-091 defect, but it means the new service code is verified only by ruff and the runtime (unit-mocked) tests.

## 7. Verdict

**`APPROVED WITH NON-BLOCKING FINDINGS`**

The distributed-tracing implementation is functionally complete and correctly scoped. W3C Trace Context propagation now spans all three canonical streaming Kafka boundaries (ingestion → `products.raw.v1` → processor/raw-writer, and processor → `products.validated.v1` → lake-writer) plus the API HTTP boundary. The round-2 and round-3 fixes correctly resolved all prior blocking findings — F1 (validated-topic propagation), F2 (`mypy libs` str-unpack), F3 (correlation in raw/lake-writer), F6 (stray `mimeType`), F9 (Jaeger env-var typo), and F10 (full `mypy` test-file type error). The helpers degrade gracefully when OTel is absent, every span attribute is bounded via `safe_attributes`, no secrets are exposed, and Jaeger + the OTel collector + Grafana provide a real local trace-viewing path.

All repository quality gates pass when independently executed: **1923 unit tests passed**, `ruff check`/`ruff format --check` are clean, and the full configured `python -m mypy` passes (182 files). The prior blocking mypy finding (F10) is resolved by `d301e92`.

The remaining findings are Moderate/Minor and non-blocking: F4 (batch trace attribution), F5 (correlation-id reset), F7 (header-plumbing test coverage), F8 (`.env.example`), F11 (`event_id` cardinality), and F12 (removed-test coverage). The integration suite (`pytest -m integration`) remains unverified (the reviewer's attempt timed out and the observability stack was not running), and there is no end-to-end live-trace test; these are verification gaps rather than code defects and are recommended follow-ups before or shortly after merge.
