# TASK-073 Review — Raw Writer Deployment

## 1. Review Header

| Field | Value |
|---|---|
| Task ID | TASK-073 — Raw Writer Deployment |
| Review date | 2026-09-19 |
| Reviewer | Qwen Code (independent review, no code modified) |
| Reviewed change set / Git range | `dc0a285725e1329030272afc4ee587e0e9322157..1237c69eeae6055b9e41d44fb4648d92dff9800a` |
| Reviewed HEAD | `1237c69eeae6055b9e41d44fb4648d92dff9800a` on `feature/TASK-073` |
| Commits in range | `dda10e1f48d1e977ec31fe69e6946c4aa8988fb6` feat(TASK-073): Kubernetes Deployment for Raw Writer Service; `1237c69eeae6055b9e41d44fb4648d92dff9800a` fix(TASK-073): use python -m module invocation for raw-writer entrypoint |
| Scope | `kubernetes/deployments/raw-writer-deployment.yaml` (new, 67 lines), `kubernetes/README.md` (+15/−2), `tests/test_kubernetes_manifests.py` (+54) |
| Verdict | **CHANGES REQUIRED** |

Sources of authority consulted: `ai/tasks/TASK-073-raw-writer-deployment.md`, `ai/PROJECT.md` (§3–§6, §9, §11), `ai/SPECIFICATION.md` (§6.3, §19, §21), `ai/ROADMAP.md` (Milestone 8), `docs/adr/ADR-001-kafka-topic-configuration.md`, `ai/AGENTS.md`, plus the raw-writer implementation (`services/raw-writer/consumer.py`, `libs/raw_writer/bronze_writer.py`, `libs/common/config.py`, `libs/common/kafka_consumer.py`, `libs/common/minio_storage.py`), the sibling TASK-071/TASK-072 deployments, and their prior review reports.

## 2. Requirements Coverage

Source of truth: `ai/tasks/TASK-073-raw-writer-deployment.md`; cross-checked against `ai/PROJECT.md`, `ai/SPECIFICATION.md` §6.3/§19, `ai/ROADMAP.md` Milestone 8, and `docs/adr/ADR-001-kafka-topic-configuration.md`.

| Requirement | Status | Implementation evidence |
|---|---|---|
| Add a Raw Writer Deployment | **Met** | `kubernetes/deployments/raw-writer-deployment.yaml` — new `apps/v1` `Deployment`, namespace `ai-data-platform`, `replicas: 1` |
| Preserve Kafka→Bronze responsibility | **Met** | Targets the existing raw-writer entrypoint (`services/raw-writer/consumer.py`), which consumes `products.raw.v1` and persists Bronze Parquet via `BronzeWriter`; no PostgreSQL access, no architectural change |
| Preserve idempotency / at-least-once | **Met (manifest-level)** | No runtime code change; the manifest runs the same commit-after-write entrypoint |
| Externalize Kafka config | **Met** | `APP_KAFKA_BOOTSTRAP_SERVERS`, `APP_KAFKA_GROUP_ID` match the `APP_`-prefixed settings contract (`KafkaConsumerSettings`) |
| Externalize object-storage config | **Met** | `APP_MINIO_ENDPOINT`, `APP_MINIO_ACCESS_KEY`, `APP_MINIO_SECRET_KEY` match `MinIOSettings` |
| Reference Secrets, never literal credentials | **Met** | MinIO credentials sourced via `secretKeyRef` (name `raw-writer-secrets`, `optional: true`); no literal secrets committed |
| Consistent labels/selectors | **Met** | `app.kubernetes.io/name`/`part-of`/`component` labels; selector (`name`+`part-of`) is a valid subset of template labels |
| No inbound Service | **Met** | No `Service` manifest; no `ports` in the container spec |
| Runnable entrypoint (module resolves) | **Met** | `command: ["python", "-m", "services.raw-writer.consumer"]` resolves via `find_spec`/`importlib.import_module` and reaches `run_consumer()` (fix commit `1237c69` corrects the earlier script-path defect) |
| Runnable pod (acceptance behavior demonstrated) | **NOT Met** | The pod crash-loops at startup: `run_consumer()` calls `load_settings(KafkaConsumerSettings)` then `load_settings(MinIOSettings)`, and each rejects the other domain's `APP_` env vars (Finding 1). Independently reproduced with the manifest's exact env set. |
| Documentation updated | **Partially Met** | `kubernetes/README.md` adds a Raw Writer section and tree entry, but the "Load local Docker images" quick-start omits the raw-writer image (Finding 3) |
| No unrelated changes / no real secrets | **Met** | Diff scoped to 3 files; no secrets, no new dependencies, no architectural change |

## 3. Git Diff Review

Changed files (all in scope):

- `kubernetes/deployments/raw-writer-deployment.yaml` (new, 67 lines) — Raw Writer Deployment. In scope.
- `kubernetes/README.md` (+15/−2) — docs: directory tree + Raw Writer section. In scope.
- `tests/test_kubernetes_manifests.py` (+54) — `TestRawWriterDeployment` manifest tests. In scope.

Assessment:

- **Scope correctness:** All changes belong to TASK-073. No unrelated files modified.
- **Architectural changes:** None at the manifest level. The manifest is a declarative wrapper around the existing entrypoint; no service boundary, event contract, topic ownership, or consumer-group change.
- **Accidental changes / dead code / debugging artifacts / generated files / secrets:** None. No real secrets are committed (`secretKeyRef` + `optional: true` only).
- **Dependency/configuration changes:** No new Python or tooling dependencies. Configuration is environment-variable based, consistent with `libs/common/config.py` and `docs/configuration.md`.
- **Branch/task isolation:** Correct — the two commits are on `feature/TASK-073` and match the requested range. Working tree is clean apart from this review file.

## 4. Test and Verification Review

**Tests examined:** `tests/test_kubernetes_manifests.py::TestRawWriterDeployment` — 8 tests (existence, apiVersion/kind, namespace, labels, selector↔template match, Kafka+MinIO env presence, MinIO secrets optional, no inbound ports). These are structural YAML assertions only; none exercises the container `command` or the runtime entrypoint.

**Test adequacy:** Adequate for manifest shape, **inadequate for runnability**. The added tests would not catch either the previous script-path command defect or the current config-loading crash (Finding 1), because they assert YAML keys and presence but never run the entrypoint or assert its `command`.

| Check | Result | Classification |
|---|---|---|
| `python -m pytest tests/test_kubernetes_manifests.py -q` | 30 passed | Independently verified |
| `python -m ruff check tests/test_kubernetes_manifests.py` | All checks passed | Independently verified |
| `python -m ruff format --check tests/test_kubernetes_manifests.py` | 1 file already formatted | Independently verified |
| `find_spec('services.raw-writer.consumer')` / `importlib.import_module(...)` | Resolves (hyphenated package is importable via importlib) | Independently verified |
| `python -m services.raw-writer.consumer` (no env) | Reaches `run_consumer()`; fails only on missing `APP_ENVIRONMENT` (expected) | Independently verified |
| `python -m services.raw-writer.consumer` with the manifest's full env set | Fails: `ConfigurationError: Unknown configuration variable(s): APP_MINIO_ACCESS_KEY, APP_MINIO_ENDPOINT, APP_MINIO_SECRET_KEY` | Independently verified (defect — Finding 1) |
| `python -m services.processor` with the TASK-072 manifest env set | Fails: `ConfigurationError: Unknown configuration variable(s): APP_KAFKA_AUTO_OFFSET_RESET, APP_KAFKA_GROUP_ID` | Independently verified (confirms the same defect is systemic, not TASK-073-specific) |
| `kubectl apply --dry-run` / live cluster validation | Not performed | Unverified (no cluster available: `kind` is not installed; `kubectl` has no reachable API server) |
| `python -m pytest -m integration` | Not run | Unverified (requires Docker/Kafka/MinIO; the diff changes only manifest/docs/tests, not runtime code — see note below) |

Note on integration tests: TASK-073 changes only a manifest, its README, and hermetic manifest tests; it does not modify the raw-writer runtime code (already covered by `tests/test_bronze_writer_integration.py` from TASK-020/TASK-021). The meaningful unverified check for this task is a live `kubectl apply`/rollout (which would surface Finding 1 immediately via `kubectl logs`). `pytest -m integration` would not have exercised the manifest or the `run_consumer` settings-loading path, so its absence is not the primary gap — the crash is reproducible without a cluster and would not be caught by any existing test.

## 5. Findings

### Finding 1 — HIGH — Pod crash-loops on startup: `load_settings` rejects cross-domain `APP_` variables

- **Files:** `kubernetes/deployments/raw-writer-deployment.yaml:43-60` (env vars) and `services/raw-writer/consumer.py:79-80` (`load_settings(KafkaConsumerSettings)` then `load_settings(MinIOSettings)`)
- **Problem:** The task requires externalizing *both* Kafka and object-storage config, so the manifest correctly sets `APP_KAFKA_*` and `APP_MINIO_*` together. But `services/raw-writer/consumer.py::run_consumer()` loads the two settings classes in separate `load_settings()` calls, and `libs/common/config.py::_unknown_app_variables()` rejects any `APP_` variable not declared on the specific class. The first call, `load_settings(KafkaConsumerSettings)`, therefore fails because `APP_MINIO_ENDPOINT`/`APP_MINIO_ACCESS_KEY`/`APP_MINIO_SECRET_KEY` are present but unknown to `KafkaConsumerSettings`. Independently reproduced: running `python -m services.raw-writer.consumer` with the manifest's exact env set exits immediately with `ConfigurationError: Unknown configuration variable(s): APP_MINIO_ACCESS_KEY, APP_MINIO_ENDPOINT, APP_MINIO_SECRET_KEY`.
- **Impact:** The Raw Writer pod fails at startup and enters `CrashLoopBackOff`. The task's core deliverable — a working Deployment — is non-functional as committed. This is independent of (and in addition to) the entrypoint fix in `1237c69`.
- **Recommendation:** The manifest cannot fix this alone; the defect is in the service's settings-loading pattern. Options (requiring coordination, not a manifest-only change): (a) introduce a combined settings class for the raw-writer service whose fields span both Kafka and MinIO, and load it once; or (b) relax/scope `_unknown_app_variables` so a service may load multiple settings classes without each call rejecting the other's vars. This is architecture/config-significant and should be escalated per `ai/AGENTS.md` §13 and the task's "Escalate architecture-significant or difficult Kubernetes issues" rule. Note: the same defect is systemic — it also crashes the already-merged TASK-072 processor Deployment (`Unknown configuration variable(s): APP_KAFKA_AUTO_OFFSET_RESET, APP_KAFKA_GROUP_ID`) and will crash the upcoming TASK-074 lake-writer Deployment (identical `KafkaConsumerSettings` + `MinIOSettings` pattern). Ingestion is unaffected because its manifest sets only a single settings class's variables.

### Finding 2 — MODERATE — Manifest tests do not assert the container command (or run the entrypoint)

- **File:** `tests/test_kubernetes_manifests.py` (`TestRawWriterDeployment`)
- **Problem:** The added tests assert YAML shape only (kind, namespace, labels, selector↔template, env presence, absence of `ports`). None asserts `container["command"]` and none executes the entrypoint, so neither the earlier script-path command defect nor the current config crash (Finding 1) would be caught by CI.
- **Impact:** Test-blindness to a crash-looping pod; the manifest test suite provides false confidence that the deployment is runnable.
- **Recommendation:** Add a test asserting `container["command"] == ["python", "-m", "services.raw-writer.consumer"]`, and a runtime sanity check (e.g., `importlib.util.find_spec("services.raw-writer.consumer") is not None`, or a subprocess invocation asserting it reaches config loading). More importantly, once Finding 1 is resolved, add a test that loads settings with both Kafka and MinIO env vars present so the cross-domain regression is locked in.

### Finding 3 — MINOR — README quick-start omits the raw-writer image

- **File:** `kubernetes/README.md` ("Load local Docker images" section)
- **Problem:** The Raw Writer section and directory tree were added, but the image-loading quick-start still lists only `ai-data-platform/ingestion:dev` and `ai-data-platform/processor:dev`; `ai-data-platform/raw-writer:dev` is missing from both the per-image and the combined multi-image examples.
- **Impact:** A user following the documented workflow will not load the raw-writer image into the kind cluster.
- **Recommendation:** Add `ai-data-platform/raw-writer:dev` to both examples.

### Finding 4 — MINOR — Service README documents an incorrect module name, compounding the command confusion

- **File:** `services/raw-writer/README.md:85`
- **Problem:** The service README documents `python -m services.raw_writer.consumer` (underscore), which fails (`ModuleNotFoundError`) because the package directory is `services/raw-writer` (hyphen). This pre-existing doc error (from TASK-021) now conflicts with the corrected manifest command `python -m services.raw-writer.consumer`.
- **Impact:** Divergent run instructions persist; only the hyphenated module form works.
- **Recommendation:** Correct the README to `python -m services.raw-writer.consumer` (hyphen) and align it with the manifest. (Correcting this file is implementation work, out of scope for this review.)

## 6. Non-Defect Observations

- **`APP_KAFKA_GROUP_ID=raw-writer`** correctly matches ADR-001 (consumer group `raw-writer` consumes `products.raw.v1`).
- **`APP_KAFKA_AUTO_OFFSET_RESET` is omitted**, relying on `KafkaConsumerSettings.kafka_auto_offset_reset` default `earliest`. Correct for at-least-once + replay; the processor Deployment sets it explicitly, so this is only a minor manifest-consistency difference.
- **`APP_MINIO_ACCESS_KEY`/`APP_MINIO_SECRET_KEY` via `secretKeyRef` with `optional: true`** correctly avoids a pod crash before TASK-078 creates `raw-writer-secrets`; when unset, `MinIOSettings` falls back to `minioadmin`/`minioadmin-local`, matching the local Docker Compose MinIO root credentials. (This only matters once Finding 1 is fixed, since startup currently fails before MinIO init regardless.)
- **`kafka:29092` and `http://minio:9000`** are forward references to the TASK-077 Kafka/MinIO Services, consistent with the docker-compose internal listeners and the sibling deployments.
- **`image: ai-data-platform/raw-writer:dev`** has no in-repo Dockerfile and `docker-compose.yml` builds no service images. Consistent with the TASK-071/TASK-072 convention; image packaging is deferred out of band.
- **No liveness/readiness/startup probes** — deliberately deferred to TASK-079 per `ai/ROADMAP.md` Milestone 8.
- **`APP_ENVIRONMENT=production`** for a local kind cluster follows the existing ingestion/processor precedent (flagged as Minor in the TASK-071 review). No functional impact today.
- **No inbound `ports` / no Service** — correct for a Kafka-consumer + object-storage-writer only.
- **Resources are specified** (`requests`/`limits`), matching the processor and exceeding the letter of the roadmap (which lists resources under TASK-079); harmless.

## 7. Verdict

**CHANGES REQUIRED**

The manifest is structurally correct and appropriately scoped: it targets the `ai-data-platform` namespace with consistent `app.kubernetes.io` labels/selectors, externalizes Kafka and MinIO configuration with the correct `APP_`-prefixed settings, sources credentials from an optional Secret without committing secrets, exposes no inbound ports, and preserves the raw-writer's Kafka→Bronze responsibility and at-least-once/idempotent semantics unchanged. Commit `1237c69` correctly fixes the previously reported script-path entrypoint defect, and `python -m services.raw-writer.consumer` now resolves.

However, the Deployment is still not runnable: with the manifest's Kafka *and* MinIO env vars present, `run_consumer()` fails at the very first `load_settings(KafkaConsumerSettings)` call because the config layer rejects the other domain's `APP_` variables (`Unknown configuration variable(s): APP_MINIO_ACCESS_KEY, APP_MINIO_ENDPOINT, APP_MINIO_SECRET_KEY`), independently reproduced. The pod will crash-loop. This is a blocking functional defect in the task's core deliverable, and it is systemic (it also affects the already-merged TASK-072 processor Deployment and will affect TASK-074). The fix is not achievable by editing the manifest alone and should be escalated as an architecture/config decision.

Blocking finding: **Finding 1 (High)**. Finding 2 (Moderate) should be addressed alongside it to prevent regression; Findings 3 and 4 are non-blocking documentation nits.
