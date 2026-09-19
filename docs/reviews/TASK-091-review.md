# TASK-091 Review — Distributed Tracing

## 1. Review Header

- **Task ID:** TASK-091
- **Review date:** 2026-09-20
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `e9391fc9796203f4536b45799d3e9ad4c2f9a0a7..e4eee9d707683b7e66312ca7029f81983a7e76dd`
- **Reviewed HEAD (commit):** `e4eee9d707683b7e66312ca7029f81983a7e76dd` on `feature/TASK-091`
- **Merge base / prior HEAD:** `e9391fc9796203f4536b45799d3e9ad4c2f9a0a7` (the TASK-090 merge commit)
- **Commits reviewed:**
  - `e4eee9d` — `feat(TASK-091): Distributed tracing with W3C Trace Context propagation`
- **Scope:** W3C Trace Context propagation across service/Kafka boundaries; Kafka header injection/extraction (`kafka_producer.publish(headers=...)`, `ConsumerMessage.headers`); per-service spans at publish/consume/HTTP boundaries; log-trace correlation via `correlation_id`/`trace_id`; Jaeger all-in-one in Docker Compose; OTel collector export to Jaeger; Grafana Jaeger datasource; `monitoring/README.md` distributed-tracing documentation; unit tests for the new helper functions.
- **Verdict:** `CHANGES REQUIRED`

Sources of authority consulted: `ai/tasks/TASK-091-distributed-tracing.md`; `ai/PROJECT.md` §10 ("Secrets must never be logged", "Major service boundaries must expose useful logs, metrics, and traces") and §2 ("OpenTelemetry for tracing"); `ai/SPECIFICATION.md` §20 ("OpenTelemetry should provide distributed traces across major service boundaries", logging should contain `trace_id`); `ai/ROADMAP.md` Milestone 10 (`TASK-091 Distributed tracing`); `ai/AGENTS.md` §6/§7/§9/§10; `ai/REVIEWER.md`. The sole ADR (`docs/adr/ADR-001-kafka-topic-configuration.md`) is not applicable to tracing. The prior `docs/reviews/TASK-090-review.md` was consulted for carried-over findings.

## 2. Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| Propagate trace/correlation context across meaningful service and Kafka boundaries | ⚠️ Partial | Ingestion → `products.raw.v1` headers, and `products.raw.v1` → processor/raw-writer are propagated. The processor → `products.validated.v1` → lake-writer hop is **not** propagated — see F1. |
| Provide a local trace viewing path | ✅ Met | `jaeger` service in `docker-compose.yml` (UI port 16686); OTel collector `otlp/jaeger` exporter; Grafana Jaeger datasource. |
| Document a representative trace | ⚠️ Partial | Documented in `monitoring/README.md`, but the diagram is inaccurate: it shows lake-writer linked to the ingestion trace, which does not happen (F1). |
| Correlate traces with metrics/logs | ⚠️ Partial | Processor sets `correlation_id` and logs `trace_id`; ingestion logs `trace_id`. Raw-writer and lake-writer set neither — contradicting the README (F3). |
| Observe architecture; do not redesign business flow | ✅ Met | No change to consumer loops, offset commits, at-least-once semantics, event contract, or service boundaries. |
| Reuse established health/freshness/data-quality/Kafka semantics | ✅ Met | Uses existing `KafkaEventProducer`, `KafkaConsumer`, structured logging, and `safe_attributes` from TASK-090. |
| Bounded, low-cardinality attributes | ✅ Met | All span attributes pass through `safe_attributes` (length + count caps, sensitive-key filtering). |
| Never expose secrets or sensitive payloads | ✅ Met | `safe_attributes` filters sensitive keys; only `source`, `event_id`, topic/partition/offset, HTTP method/target/scheme/status are set. No payload fields. |
| Instrumentation failure must not alter core semantics | ✅ Met | `inject_trace_context`/`extract_trace_context`/`get_current_trace_id`/`get_tracer` all degrade to no-ops/`None` on `ImportError`; `_NoOpTracer.start_as_current_span` accepts `*args/**kwargs`; producer publishes with `headers=None` when no context. |
| Dashboards/provisioning version-controlled and reproducible | ✅ Met | Compose, collector config, and Grafana datasource are all version-controlled. |
| Deterministic validation/tests | ⚠️ Partial | 8 new unit tests added (32 total OTel tests) and they pass, but the repository type check now fails (F2). |
| No unrelated architecture changes / secrets / unnecessary dependencies | ✅ Met | Changes are additive observability wiring only; no new Python dependencies; no secrets. |

## 3. Git Diff Review

**Range:** `e9391fc..e4eee9d` — 1 commit, 20 files, +535/−69.

Files changed:

- `docker-compose.yml` (+16) — adds `jaeger` (all-in-one 1.62) and an `otel-collector → jaeger` `depends_on`.
- `libs/common/kafka_consumer.py` (+7) — adds `ConsumerMessage.headers` and extracts headers from `msg.headers()`.
- `libs/common/kafka_producer.py` (+18/−2) — `publish()` accepts optional `headers` and forwards them via `produce(**kwargs)`.
- `libs/observability/__init__.py` (+6) — exports `inject_trace_context`, `extract_trace_context`, `get_current_trace_id`.
- `libs/observability/otel_config.py` (+69) — adds `inject_trace_context`, `extract_trace_context`, `get_current_trace_id`, `_DictSetter`, `_DictGetter`.
- `monitoring/README.md` (+109) — distributed-tracing architecture, flow, representative trace, log-trace correlation, configuration.
- `monitoring/grafana/datasources/prometheus.yml` (+10) — adds Jaeger datasource.
- `monitoring/otel-collector-config.yaml` (+6/−6) — adds `otlp/jaeger` exporter to the traces pipeline.
- `services/api/app.py` (+29/−6) — adds HTTP tracing middleware with `X-Trace-Id` response header.
- `services/ingestion/runner.py` (+97/−46) — wraps publish in `ingestion.publish` span, injects headers, logs `trace_id`.
- `services/lake-writer/consumer.py` (+22) — `lake-writer.process_message` span, extracts headers.
- `services/processor/__main__.py` (+50/−26) — `processor.process_batch` span, extracts headers, sets `correlation_id`.
- `services/raw-writer/consumer.py` (+22) — `raw-writer.process_message` span, extracts headers.
- `tests/test_difficult_source_integration.py`, `tests/test_ebay_integration.py`, `tests/test_ingestion_e2e.py`, `tests/test_pipeline_e2e.py`, `tests/test_retailer_integration.py` (+6 each) — `MockProducer.publish` signature gains optional `headers`.
- `tests/test_kafka_producer.py` (+4/−4) — adapts two assertions from positional `call.args` to `call.kwargs["topic"]`.
- `tests/test_otel_config.py` (+109) — 8 new tests for the new helpers.

**Scope correctness:** All changes belong to TASK-091. No unrelated task changes are mixed in.

**Unrelated/accidental changes:** None observed. The integration/e2e `MockProducer` signature updates are a necessary consequence of the new `publish(headers=...)` signature.

**Architectural changes:** None. Service boundaries, the canonical event contract, Kafka/persistence semantics, and data-lake/warehouse/API ownership are unchanged. The `services/warehouse-loader` service is intentionally not modified.

**Dependency/config changes:** No new Python dependencies. Compose and monitoring config changes are scoped to observability.

**Debug/temp/dead code/secrets:** No debug prints, temp files, or generated artifacts. No credentials or payload fields. The `debug` exporter retained in the collector config is an intentional local-development default from TASK-090.

**Branch and task isolation:** Reviewed HEAD is on `feature/TASK-091`; the range contains exactly one commit belonging to TASK-091. Working tree was clean at review time.

## 4. Test and Verification Review

**Tests added/changed:**

- `tests/test_otel_config.py` — 8 new tests: `inject_trace_context` (no-OTel no-op; populates carrier with `traceparent` bytes), `extract_trace_context` (no-OTel returns `None`; calls propagator; handles string values), `get_current_trace_id` (no-OTel `None`; no active span `None`; hex 32-char trace id). Total 32 tests in this file.
- `tests/test_kafka_producer.py` — two assertions adapted to the new `produce(**kwargs)` call shape; no new header-forwarding assertion.
- Five integration/e2e test files — `MockProducer.publish` signature updated to accept `headers`.

**Independently verified (executed by reviewer):**

- `python -m pytest tests/test_otel_config.py -q` → **32 passed in 0.58s**.
- `python -m pytest tests/test_otel_config.py tests/test_kafka_producer.py -q` → **62 passed, 2 deselected** (the deselected tests are the `@pytest.mark.integration` cases in `test_kafka_producer.py`).
- `python -m pytest tests/test_kafka_consumer.py -q` → **24 passed in 2.03s** (confirms the `msg.headers()` change does not regress existing consumer behavior; note the mock does not exercise header population — see F7).
- `python -m ruff check <11 changed Python files>` → **All checks passed**.
- `python -m ruff format --check <11 changed Python files>` → **11 files already formatted**.
- `python -m mypy libs` → **FAILED** — `libs\common\kafka_consumer.py:226: error: Unpacking a string is disallowed [str-unpack]` (1 error, 72 source files checked). See F2.

**Implementation evidence reviewed (not rerun):** None beyond the above; the commit message reports "8 new tests for trace propagation (32 total otel tests)", consistent with the 32 passing tests I executed.

**Unverified:**

- **`python -m pytest -m integration` was not run**, and no implementation evidence of such a run exists in the commit. The change touches Kafka (producer headers, consumer header extraction), so per `ai/REVIEWER.md` this should be verified. The unit tests that exist use mocks and do not exercise the real confluent-kafka header round-trip. Integration risk to existing semantics is low (headers are additive and optional), but it is unverified.
- **No end-to-end live trace test.** There is no test that starts the Compose collector + Jaeger and asserts a trace is received/exported. The "reproducible observability artifacts" claim is verified by configuration only, not by a live trace.

## 5. Findings

### F1 — High — Trace context is not propagated across the processor → `products.validated.v1` → lake-writer boundary

- **Files:** `services/processor/__main__.py` / `services/processor/pipeline.py` / `libs/common/kafka_validated_producer.py` / `services/lake-writer/consumer.py`; also `monitoring/README.md`.
- **Problem:** The processor extracts `traceparent` from the incoming raw message and creates a `processor.process_batch` child span, but it **never injects trace context into the validated output**. `KafkaValidatedOutputProducer.publish()` has no `headers` parameter, and `ProcessorPipeline._publish_valid_records()` calls the sink without any carrier. As a result, `products.validated.v1` messages carry no `traceparent`. Lake-writer's `extract_trace_context(message.headers)` therefore always returns `None`, and its `lake-writer.process_message` span becomes a disconnected root span rather than a child of the ingestion trace.
- **Impact:** A meaningful, canonical Kafka boundary (raw → validated → Silver) is not propagated, so end-to-end traces are truncated at the processor. The `monitoring/README.md` "Trace propagation flow" and "Representative trace" sections are factually inaccurate: they show lake-writer as a child span of the same trace and state lake-writer "extracts traceparent from Kafka headers". This is a direct gap against the task objective ("propagate trace/correlation context across meaningful service and Kafka boundaries") and against `SPECIFICATION.md` ("distributed traces across major service boundaries").
- **Recommendation:** Add header support to `KafkaValidatedOutputProducer.publish` (mirroring `KafkaEventProducer.publish`), inject the current trace context in the processor before publishing valid events, and update the README trace to reflect the actually-achieved propagation. Alternatively, explicitly document that validated-topic propagation is deferred to a follow-up task rather than implying it works today.

### F2 — High — `mypy` fails on the changed `libs/common/kafka_consumer.py` (breaks the required repository type check)

- **File:** `libs/common/kafka_consumer.py:226`.
- **Problem:** `python -m mypy libs` (the project's configured mypy scope per `pyproject.toml` `[tool.mypy] files = ["scripts", "tests", "libs"]`) now fails with `Unpacking a string is disallowed [str-unpack]` on `headers = {k: v for k, v in raw_headers if isinstance(v, bytes)}`. confluent-kafka 2.15 types `Message.headers()` as `Optional[HeadersType]`, where `HeadersType = Union[Dict[str, Union[str, bytes, None]], List[Tuple[str, Union[str, bytes, None]]]]`. The comprehension assumes the list-of-tuples form; mypy flags the dict branch (iterating a dict yields `str` keys, which cannot be unpacked into `k, v`).
- **Impact:** The repository's type-check gate fails. `ai/AGENTS.md` §7 (Definition of Done) requires repository checks to pass, and the TASK-090 review treated a clean `mypy` as an acceptance gate. Runtime behavior is correct today (the C extension `Message.headers()` returns a list of tuples), but the change does not type-check, and the code is silently vulnerable to the dict form described by the type contract (which would raise `ValueError` at runtime if it ever occurred).
- **Recommendation:** Normalize the headers defensively before unpacking (e.g. `dict(msg.headers() or [])` for the dict/list forms, then iterate `.items()`), or add a narrow type-level guard. Re-run `python -m mypy libs` to confirm a clean result.

### F3 — Moderate — Log-trace correlation is only implemented in the processor; raw-writer and lake-writer set no `correlation_id`/`trace_id`, contradicting the README

- **Files:** `monitoring/README.md` ("Log-trace correlation" section), `services/raw-writer/consumer.py`, `services/lake-writer/consumer.py`.
- **Problem:** The README states "Processor, raw-writer, and lake-writer set the structured log `correlation_id` field to the current trace ID." In fact, only `services/processor/__main__.py` calls `set_correlation_id(...)` and logs `trace_id`. Raw-writer and lake-writer only set span attributes; their structured logs (startup, lag sampling, DLQ, etc.) carry neither `trace_id` nor `correlation_id`. Ingestion logs `trace_id` in `event_published` (debug level) but does not set `correlation_id`.
- **Impact:** The "correlate traces with metrics/logs" objective is only partially met and the documentation overstates the implementation. Operators attempting to correlate a raw-writer/lake-writer log line with a trace will not find a `trace_id` field.
- **Recommendation:** Either add `trace_id`/`correlation_id` to raw-writer and lake-writer log records (e.g. via `get_current_trace_id()` inside `process_message`), or correct the README to accurately state that only the processor (and ingestion's `event_published` debug log) currently emit trace correlation fields.

### F4 — Moderate — Batch trace attribution uses only the first message's headers

- **File:** `services/processor/__main__.py:73-75`.
- **Problem:** `process_batch` derives the parent context (and hence `correlation_id`) solely from `messages[0].headers`. If a batch ever contains messages from multiple raw traces (each raw message carries its own `traceparent`), every message after the first loses its trace attribution and is lumped under the first message's trace.
- **Impact:** Latent correctness issue for the "correlate traces" objective. It is not currently triggered because `run_consumer` calls `process_batch([msg], pipeline)` (single-message batches), but the function is a general batch API and the mis-attribution would appear the moment batching is enabled.
- **Recommendation:** Either document/guarantee single-message batches for trace correctness, or instrument the pipeline at the per-message granularity (or add `SpanLinks`) when multi-message batches are processed.

### F5 — Minor — `correlation_id` ContextVar is set but never reset

- **File:** `services/processor/__main__.py` (via `set_correlation_id` in `libs/observability/logging_config.py`).
- **Problem:** `set_correlation_id(trace_id)` is called inside the span, but there is no corresponding `set_correlation_id(None)` when leaving the span or when a message has no trace. Because it is a `ContextVar` set without a reset token, the value persists into subsequent log records emitted outside the span in the same loop (lag sampling, sleeps, shutdown, etc.).
- **Impact:** Non-message log records can carry a stale `correlation_id` from a prior message, slightly degrading correlation accuracy. No security or correctness impact on processing.
- **Recommendation:** Reset the correlation id to `None` after the span (e.g. a `finally`), or use a context-manager/`ContextVar.reset(token)`.

### F6 — Minor — Hardcoded `"mimeType": "application/json"` span attribute in ingestion is meaningless

- **File:** `services/ingestion/runner.py` (inside `_publish_event`, the `safe_attributes({... "mimeType": "application/json" ...})` call).
- **Problem:** The span attribute `mimeType` is a static literal unrelated to the event being published and does not describe the Kafka publish boundary. It appears to be a copy-paste artifact.
- **Impact:** Adds a low-value, potentially confusing attribute to every ingestion span. Harmless but not meaningful telemetry.
- **Recommendation:** Remove it, or replace with a meaningful attribute (e.g. the event's `schema_version`/`source` are already present; nothing else is needed).

### F7 — Minor — No tests verify header forwarding/extraction at the producer/consumer boundary

- **Files:** `tests/test_kafka_producer.py`, `tests/test_kafka_consumer.py`.
- **Problem:** The core of this task (Kafka header injection/extraction) is only unit-tested at the OTel-helper level (`inject_trace_context`/`extract_trace_context` with mocked OTel). There is no test asserting that `KafkaEventProducer.publish(headers=[("traceparent", ...)])` forwards those headers to `Producer.produce(...)`, nor that `KafkaConsumer` populates `ConsumerMessage.headers` from `msg.headers()`. The `test_kafka_producer.py` changes only adapted assertions for the `produce(**kwargs)` change; the existing consumer mocks return an auto-`MagicMock` for `headers()`, which iterates to empty and does not exercise the extraction path.
- **Impact:** Coverage gap on the primary deliverable; a regression in header handling could pass the suite unnoticed.
- **Recommendation:** Add a focused unit test for `KafkaEventProducer.publish(headers=...)` and one for `ConsumerMessage.headers` population (e.g. mock `msg.headers()` to return `[("traceparent", b"...")]` and assert `headers == {"traceparent": b"..."}`).

### F8 — Minor — `.env.example` omits the new Jaeger (and prior OTel) Compose variables

- **File:** `.env.example`.
- **Problem:** `docker-compose.yml` now references `${JAEGER_UI_PORT:-16686}` and `${JAEGER_OTLP_GRPC_PORT:-4319}`, and (from TASK-090) `${OTEL_COLLECTOR_GRPC_PORT:-4317}`/`${OTEL_COLLECTOR_HTTP_PORT:-4318}` plus the `APP_OTEL_*` service variables, none of which are listed in `.env.example`.
- **Impact:** Minor discoverability gap for local setup; defaults still work. This extends the unresolved TASK-090 F5 finding.
- **Recommendation:** Add commented `JAEGER_UI_PORT`/`JAEGER_OTLP_GRPC_PORT` and the OTel collector/`APP_OTEL_*` entries for consistency with the other infra variables.

### F9 — Minor — Jaeger environment variable name appears non-standard/typo'd

- **File:** `docker-compose.yml` (Jaeger `environment`).
- **Problem:** `COLLECTOR_OTLP_ENABLED_HONOUR_ENVIRONMENT_VARIABLES: "true"` does not match the standard Jaeger flag (`COLLECTOR_OTLP_ENABLED`). The `_HONOUR_ENVIRONMENT_VARIABLES` suffix is not a recognized Jaeger configuration variable.
- **Impact:** Likely harmless because the Jaeger all-in-one (1.62) enables its OTLP receiver by default, so the collector → Jaeger export should still work; but the variable is misleading and gives a false impression that it is doing something.
- **Recommendation:** Remove it or replace with `COLLECTOR_OTLP_ENABLED: "true"`; verify the collector → Jaeger export actually works locally.

## 6. Non-Defect Observations

- **N1 — Trace coverage stops at Silver/lake-writer.** The warehouse-loader (Gold → PostgreSQL) and the Airflow batch layer (Silver → Gold) are not instrumented, so the "distributed traces across major service boundaries" span is incomplete end-to-end. This is consistent with the README's streaming-path focus and the absence of a Kafka boundary there, but worth noting for the overall observability goal.
- **N2 — Grafana datasource file naming.** The Jaeger datasource was added to `monitoring/grafana/datasources/prometheus.yml`, which is now a misnomer since it provisions both Prometheus and Jaeger. Renaming to `datasources.yml` (or splitting) would be cleaner. Cosmetic only.
- **N3 — API OTel initialization placement (carried from TASK-090 F4).** `setup_opentelemetry` is still invoked inside `create_app()` and now `tracer = get_tracer(__name__)` is a module-level proxy. It resolves lazily so spans work when enabled, but repeated `create_app()` calls (common in tests) re-initialize the global tracer provider. Harmless with OTel disabled by default.
- **N4 — OTel is disabled by default.** `otel_enabled` defaults to `False`, so all services no-op and the Jaeger path is only exercised with `APP_OTEL_ENABLED=true`. Safe posture, but means the tracing path is not active by default and has no automated live-trace test.
- **N5 — Commit attribution.** The single commit is authored by `Workflow Test <workflow@example.invalid>`, the same automated identity noted in the TASK-088/089/090 reviews. Worth confirming intended attribution before merge.

## 7. Verdict

**`CHANGES REQUIRED`**

The tracing foundation is in place and mostly correct: W3C Trace Context injection/extraction helpers are well-written with graceful `ImportError` fallbacks; the producer/consumer header plumbing is additive and does not disturb at-least-once delivery or offset-commit semantics; `safe_attributes` bounds every span attribute; Jaeger, the collector export, and the Grafana datasource provide a real local trace-viewing path; and the 8 new unit tests (32 OTel tests total) pass, with ruff lint/format clean.

Two findings block acceptance:

1. **F1 (High)** — the processor does not propagate trace context into `products.validated.v1`, so the lake-writer span is a disconnected root and the documented representative trace / propagation flow is inaccurate. This leaves a meaningful canonical Kafka boundary unpropagated, directly undercutting the task's core objective.
2. **F2 (High)** — the change breaks the repository's `mypy` type-check gate (`libs/common/kafka_consumer.py:226`, `str-unpack`), which is a required Definition-of-Done check.

The remaining findings are Moderate/Minor and mostly concern documentation accuracy (F3), batch trace attribution (F4), correlation-id lifecycle (F5), a stray attribute (F6), and test/`.env.example`/config hygiene (F7-F9). None of these alone block, but they should be addressed alongside the two High findings.
