# TASK-072 Review — Processor Deployment

## 1. Review Header

| Field | Value |
|---|---|
| Task ID | TASK-072 |
| Review date | 2026-09-19 |
| Reviewer | Qwen Code (independent review, no code modified) |
| Reviewed change set | `31812b210da1cd4631cdb7961529834429836ad6..79b05da8403c2465bf5ea7b4c029ad14bb0490f9` |
| Reviewed HEAD | `79b05da8403c2465bf5ea7b4c029ad14bb0490f9` on `feature/TASK-072` |
| Commits in range | `ccbb5dc70e13ad99ddc3a7f23ee5aeaa7b60eb10` feat(TASK-072): Kubernetes Deployment for Processor Service; `3c4e2831d67ce874c2e3625f7b1ef70b6d19f2a5` fix(TASK-072): add processor service entrypoint for K8s deployment; `79b05da8403c2465bf5ea7b4c029ad14bb0490f9` fix(TASK-072): use KafkaValidatedOutputProducer and KafkaDeadLetterProducer |
| Scope | Processor Deployment manifest, processor service entrypoint (`services/processor/__main__.py`), manifest tests, docs |
| Verdict | **APPROVED WITH NON-BLOCKING FINDINGS** |

Sources consulted: `ai/tasks/TASK-072-processor-deployment.md`, `ai/PROJECT.md` (§3–§5, §9), `ai/SPECIFICATION.md` (§6.2, §8, §19), `ai/ROADMAP.md` (Milestone 8), `docs/adr/ADR-001-kafka-topic-configuration.md`, `ai/AGENTS.md`, plus the implementation and the existing producer/consumer components and their tests.

Note: a prior review (of the range up to `3c4e283`) reported two **Critical** defects in the entrypoint — the validated sink passed an unsupported `topic=` keyword to `KafkaEventProducer.publish`, and the invalid sink bypassed delivery confirmation and serialized with `str()`. Commit `79b05da` reworks the entrypoint to use the canonical producer components, resolving both. This review covers the full range at HEAD `79b05da`.

## 2. Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| Add a processor Deployment | Met | `kubernetes/deployments/processor-deployment.yaml` (new `apps/v1` Deployment, namespace `ai-data-platform`, `replicas: 1`) |
| Preserve Kafka consumer group | Met | `APP_KAFKA_GROUP_ID: processor` matches ADR-001 (consumer group `processor` consumes `products.raw.v1`) and `KafkaConsumerSettings.kafka_group_id` |
| Preserve processing (raw → validated/invalid) | Met | `services/processor/__main__.py` wires `KafkaValidatedOutputProducer.publish` as the validated sink and `KafkaDeadLetterProducer.publish` as the invalid sink — exactly the canonical wiring in `tests/test_processor_integration.py::_build_pipeline` |
| Preserve graceful shutdown | Met | `run_consumer` uses `try/finally` to close consumer + both producers; `KafkaConsumer` registers SIGINT/SIGTERM handlers |
| Preserve offset semantics (at-least-once) | Met | Commit-after-process intent via `KafkaConsumer.process_next`; both producers confirm broker acknowledgement and raise `PublishError` on unconfirmed delivery, so the input offset is not committed on output failure |
| Externalize bootstrap/group config | Met | `APP_KAFKA_BOOTSTRAP_SERVERS`, `APP_KAFKA_GROUP_ID`, `APP_KAFKA_AUTO_OFFSET_RESET` follow the `APP_`-prefixed settings contract |
| Keep processor independent | Met | Own entrypoint and service-local wiring; no shared architecture altered |
| Documentation updated | Met | `kubernetes/README.md` documents processor deployment and image loading |
| No unrelated changes / no real secrets | Met | Diff scoped to 4 files; no secrets introduced |

## 3. Git Diff Review

Changed files (all in scope):

- `kubernetes/deployments/processor-deployment.yaml` (new, 54 lines) — processor Deployment. In scope.
- `services/processor/__main__.py` (new, 103 lines) — processor runtime entrypoint. In scope.
- `tests/test_kubernetes_manifests.py` (+44 lines) — `TestProcessorDeployment` manifest tests. In scope.
- `kubernetes/README.md` (+13/−1) — docs. In scope.

Assessment:

- **Scope correctness:** All changes belong to TASK-072. No unrelated files modified.
- **Architectural changes:** None to shared architecture. The entrypoint is service-local and now uses the existing, tested producer components (`KafkaValidatedOutputProducer`, `KafkaDeadLetterProducer`) rather than reaching into private internals.
- **Accidental changes / dead code / secrets:** None. No secrets, no debugging artifacts, no generated files.
- **Dependency/configuration changes:** No new dependencies. Manifest mirrors the ingestion Deployment's label/env conventions.
- **Branch/task isolation:** Correct — changes are on `feature/TASK-072` and match the three commits in the requested range.

## 4. Test and Verification Review

| Check | Result | Classification |
|---|---|---|
| `python -m pytest tests/test_kubernetes_manifests.py -q` | 22 passed | Independently verified |
| `python -m pytest tests/test_pipeline.py tests/test_failure_replay.py -q` | 30 passed | Independently verified |
| `python -m pytest tests/test_validated_producer.py tests/test_kafka_errors.py -q` | 34 passed, 1 deselected | Independently verified (confirms the exact producer components the entrypoint now uses) |
| `python -m ruff check services/processor/__main__.py tests/test_kubernetes_manifests.py` | All checks passed | Independently verified |
| Entrypoint import sanity | `import services.processor.__main__` succeeds; `python -m services.processor` resolves | Independently verified (not run against a live Kafka broker) |
| `python -m pytest -m integration` | Not run | Unverified (requires Docker/Kafka; per `ai/REVIEWER.md` this is a gap, noted below) |
| `mypy` | Not run | Unverified (note: `pyproject.toml` `[tool.mypy] files` excludes `services/`, so the new entrypoint is outside mypy coverage regardless) |

Test adequacy:

- The only added tests are **manifest-structure** tests (`TestProcessorDeployment`). They validate YAML shape (kind, namespace, labels, selector↔template match, `APP_KAFKA_*` env presence, absence of `ports`). They do **not** exercise `services/processor/__main__.py` at runtime.
- The runtime entrypoint has no dedicated unit test of its own. However, the wiring is a thin composition of already-tested components: `ProcessorPipeline` (`test_pipeline.py`), `KafkaValidatedOutputProducer` (`test_validated_producer.py`), `KafkaDeadLetterProducer` (`test_kafka_errors.py`), and `KafkaConsumer` (`test_failure_replay.py`). The previous round's defect (incorrect component wiring) is now prevented only by convention, not by an automated test — see Finding 3 recommendation below.
- Because TASK-072 touches Kafka and infrastructure boundaries, the absence of `python -m pytest -m integration` evidence is an incomplete verification per `ai/REVIEWER.md`. The existing `tests/test_processor_integration.py` demonstrates the canonical wiring but does not run the new `run_consumer` entrypoint.

## 5. Findings

### Finding 1 — MODERATE — Processor-level deduplication is effectively disabled in the deployed entrypoint

- **File:** `services/processor/__main__.py:59-63` (pipeline construction)
- **Problem:** `ProcessorPipeline` is constructed without `dedup_state` (defaults to `None`), and `process_next` feeds a single-message batch (`process=lambda msg: process_batch([msg], pipeline)`). With `state=None`, `deduplicate` only performs within-batch dedup, which can never trigger on a one-row batch; cross-batch dedup (re-delivery of an already-seen `event_id` within the same process) is fully disabled.
- **Impact:** A re-delivered duplicate `event_id` (e.g., offset commit failed but the process stayed up) is re-published to `products.validated.v1` instead of being skipped. This is within at-least-once semantics — the durable invariant is enforced downstream by PostgreSQL `UNIQUE(event_id)` (SPECIFICATION §13) — but it disables the processor's documented dedup step (PROJECT.md §4, SPECIFICATION §6.2).
- **Recommendation:** Instantiate `DeduplicationState()` and pass it (`ProcessorPipeline(..., dedup_state=DeduplicationState())`), matching the optional dedup-state wiring already supported by `tests/test_processor_integration.py::_build_pipeline`. Not blocking: dedup is documented as best-effort and durable dedup is enforced at the warehouse/serving layer.

### Finding 2 — MINOR — `process_batch` docstring overstates its behavior; structured log counts are dropped by the formatter

- **File:** `services/processor/__main__.py:36-54`
- **Problem:** (a) The docstring "Raises PublishError if any output publication fails" is inaccurate — `process_batch` only propagates the exception from `pipeline.process_batch`; it never raises on its own. (b) `logger.info("processor_batch_complete", extra={"valid": ..., "invalid": ..., "duplicates": ..., "conflicts": ...})` — the `basicConfig` format string (`"%(asctime)s %(levelname)s %(name)s %(message)s"`) does not reference the `extra` keys, so those counts are silently dropped from output.
- **Impact:** Cosmetic/observability — the batch-outcome counts are computed but never actually emitted.
- **Recommendation:** Correct the docstring to "Propagates `PublishError` from the pipeline so the caller does not commit the offset"; either fold the counts into the message or adopt a JSON formatter that renders `extra`.

### Finding 3 — MINOR — Processor producers report `client.id` "ingestion"

- **File:** `kubernetes/deployments/processor-deployment.yaml` (no `APP_KAFKA_CLIENT_ID`); `libs/common/kafka_producer.py:27` (`kafka_client_id: str = "ingestion"`)
- **Problem:** `KafkaValidatedOutputProducer` and `KafkaDeadLetterProducer` both read `KafkaProducerSettings.kafka_client_id`, which defaults to "ingestion". The manifest does not override it, so broker-side logs/metrics attribute the processor's producers to "ingestion" while its consumer group is "processor".
- **Impact:** Minor observability/log-correlation mismatch; no functional impact.
- **Recommendation:** Set `APP_KAFKA_CLIENT_ID: processor` in the manifest (and give ingestion its own distinct id if desired).

## 6. Non-Defect Observations

- **Canonical topics are fixed by ADR-001, not per-service env vars.** `products.raw.v1`, `products.validated.v1`, and `products.invalid.v1` are canonical versioned names managed centrally by `scripts/manage_kafka_topics.py`. Externalizing bootstrap/group config (rather than per-service topic env vars) satisfies the task's "externalize topics/bootstrap config" objective. Not a defect.
- **`APP_KAFKA_GROUP_ID=processor` and `auto.offset.reset=earliest`** are correct for the at-least-once + idempotent-processing semantics in PROJECT.md §5 and ADR-001.
- **Manifest conventions are consistent** with the ingestion Deployment: same `app.kubernetes.io` label scheme, `IfNotPresent` image pull, `python -m services.processor` command, `APP_`-prefixed env vars, and no inbound `ports`.
- **Graceful shutdown is correctly modeled** via `KafkaConsumer` signal handlers plus `try/finally` close of consumer and both producers — matching the raw-writer/lake-writer pattern.
- **Health probes are absent**, which is correct: `kubernetes/README.md` and `ai/ROADMAP.md` defer probes to TASK-079.
- **Resources are specified** (`requests`/`limits`) although `ai/ROADMAP.md` lists "resources" under TASK-079; this matches the TASK-071 ingestion precedent and is harmless.
- **Image `ai-data-platform/processor:dev`** follows the ingestion convention; no Dockerfile exists in-repo, so images are built/loaded out-of-band (documented in `kubernetes/README.md`). Not a defect for this task.
- **`ProcessorMetrics` is not wired** into the entrypoint, so processor-level counters are not recorded. The metrics module is in-memory with no exporter, and observability/probes are deferred to TASK-079; this is a low-priority gap rather than a defect.
- **No explicit `sys.path` insertion** (unlike `services/ingestion/__main__.py`). The entrypoint relies on `python -m` CWD resolution, which is fine for standard image layouts but slightly less defensive than the ingestion entrypoint.

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The manifest, documentation, and manifest tests are correct and appropriately scoped. The entrypoint at HEAD `79b05da` resolves the two Critical defects found in the prior round by wiring the canonical, tested producer components (`KafkaValidatedOutputProducer` for `products.validated.v1`, `KafkaDeadLetterProducer` for `products.invalid.v1`), preserving consumer-group, graceful-shutdown, and at-least-once offset semantics.

Remaining findings are non-blocking: processor-level deduplication is effectively disabled because no `DeduplicationState` is instantiated (Moderate — the durable invariant is still enforced downstream at PostgreSQL), plus two minor observability/docstring nits (Minor). None prevents the processor from performing its core consume → validate → publish contract in Kubernetes.
