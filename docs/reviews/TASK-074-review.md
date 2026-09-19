# TASK-074 Review — Lake Writer Deployment

## 1. Review Header

| Field | Value |
|---|---|
| Task ID | TASK-074 — Lake Writer Deployment |
| Review date | 2026-09-19 |
| Reviewer | Qwen Code (independent review, no code modified) |
| Reviewed change set / Git range | `b7ecd8b5c5ab2544cf4dad2a19158e7850b8d586..e5129928d673078976c27dc6baa28be36d2474ec` |
| Reviewed HEAD | `e5129928d673078976c27dc6baa28be36d2474ec` on `feature/TASK-074` |
| Commits in range | `e5129928d673078976c27dc6baa28be36d2474ec` feat(TASK-074): Kubernetes Deployment for Lake Writer Service |
| Scope | `kubernetes/deployments/lake-writer-deployment.yaml` (new, 68 lines), `kubernetes/README.md` (+16/−4) |
| Verdict | **CHANGES REQUIRED** |

Sources of authority consulted: `ai/tasks/TASK-074-lake-writer-deployment.md`, `ai/PROJECT.md` (§3–§6), `ai/SPECIFICATION.md` (§6.4, §19), `ai/ROADMAP.md` (Milestone 8), `ai/AGENTS.md` (§5–§11), plus the lake-writer implementation (`services/lake-writer/consumer.py`, `libs/lake_writer/silver_writer.py`, `libs/common/config.py`, `libs/common/kafka_consumer.py`, `libs/common/minio_storage.py`), the sibling TASK-071/TASK-072/TASK-073 deployments, and the TASK-073 review report.

## 2. Requirements Coverage

Source of truth: `ai/tasks/TASK-074-lake-writer-deployment.md`; cross-checked against `ai/PROJECT.md`, `ai/SPECIFICATION.md` §6.4/§19, `ai/ROADMAP.md` Milestone 8, and `ai/AGENTS.md`.

| Requirement | Status | Implementation evidence |
|---|---|---|
| Add a Lake Writer Deployment | **Met** | `kubernetes/deployments/lake-writer-deployment.yaml` — new `apps/v1` `Deployment`, namespace `ai-data-platform`, `replicas: 1` |
| Preserve validated-event→Silver responsibility | **Met** | Targets the lake-writer entrypoint (`services/lake-writer/consumer.py`), which consumes `products.validated.v1` and persists Silver Parquet via `SilverWriter`; no PostgreSQL access, no architectural change |
| Preserve schema/partition/idempotency semantics | **Met (manifest-level)** | No runtime code change; the manifest runs the same commit-after-write entrypoint; deterministic `event_id`-derived keys and Silver schema live in `libs/lake_writer/silver_writer.py` |
| Separate service boundary | **Met** | Own `Deployment`, own consumer group (`lake-writer`), no coupling to processor/raw-writer/warehouse |
| Externalize Kafka config | **Met** | `APP_KAFKA_BOOTSTRAP_SERVERS`, `APP_KAFKA_GROUP_ID` match the `APP_`-prefixed `KafkaConsumerSettings` contract |
| Externalize object-storage config | **Met** | `APP_MINIO_ENDPOINT`, `APP_MINIO_ACCESS_KEY`, `APP_MINIO_SECRET_KEY` match `MinIOSettings` |
| Reference Secrets, never literal credentials | **Met** | MinIO credentials via `secretKeyRef` (name `lake-writer-secrets`, `optional: true`); no literal secrets committed |
| Consistent labels/selectors | **Met** | `app.kubernetes.io/name`/`part-of`/`component` labels; selector (`name`+`part-of`) is a valid subset of template labels |
| No inbound Service | **Met** | No `Service` manifest; no `ports` in the container spec |
| Declarative manifests | **Met** | Single declarative YAML; no imperative scripting |
| Runnable entrypoint (module resolves) | **NOT Met** | `command: ["python", "-m", "services.lake_writer.consumer"]` uses an underscore package name that does not exist on disk; the real package is `services.lake-writer` (hyphen). `importlib.util.find_spec("services.lake_writer")` returns `None` (Finding 1) |
| Runnable pod (acceptance behavior demonstrated) | **NOT Met** | The pod fails at startup with `ModuleNotFoundError: No module named 'services.lake_writer'` and enters `CrashLoopBackOff` (Finding 1). Independently reproduced |
| Documentation updated | **Met** | `kubernetes/README.md` adds a Lake Writer section, directory-tree entry, and image-load entries |
| Validate manifests/tests | **Partially Met** | The diff adds no manifest structure tests; the TASK-073 precedent (`TestRawWriterDeployment`, 8 tests) is not mirrored (Finding 2) |
| No unrelated changes / no real secrets | **Met** | Diff scoped to 2 files; no secrets, no new dependencies, no architectural change |

## 3. Git Diff Review

Changed files (both in scope):

- `kubernetes/deployments/lake-writer-deployment.yaml` (new, 68 lines) — Lake Writer Deployment. In scope.
- `kubernetes/README.md` (+16/−4) — docs: directory tree + Lake Writer section + image-load entries. In scope.

Assessment:

- **Scope correctness:** All changes belong to TASK-074. No unrelated files modified.
- **Architectural changes:** None at the manifest level. The manifest is a declarative wrapper around the existing lake-writer entrypoint; no service boundary, event contract, topic ownership, or consumer-group change.
- **Accidental changes / dead code / debugging artifacts / generated files / secrets:** None. No real secrets are committed (`secretKeyRef` + `optional: true` only).
- **Dependency/configuration changes:** No new Python or tooling dependencies. Configuration is environment-variable based, consistent with `libs/common/config.py` and `docs/configuration.md`.
- **Branch/task isolation:** Correct — the single commit is on `feature/TASK-074` and matches the requested range. Working tree is clean apart from this review file.

## 4. Test and Verification Review

**Tests examined:** `tests/test_kubernetes_manifests.py` contains `TestKindConfig`, `TestNamespaceManifest`, `TestIngestionDeployment`, `TestProcessorDeployment`, and `TestRawWriterDeployment` (8 tests), but **no `TestLakeWriterDeployment`**. No test was added or changed by this commit. The existing `TestRawWriterDeployment.test_raw_writer_deployment_command_uses_module_invocation` asserts `["python", "-m", "services.raw-writer.consumer"]` (hyphen), which is the correct convention and the one the lake-writer manifest should have mirrored.

**Test adequacy:** The lake-writer manifest is untested. A structural test asserting the container `command` (analogous to the raw-writer test) would have caught the underscore/hyphen defect immediately. The absence of any lake-writer manifest test is a coverage regression relative to the TASK-073 precedent.

| Check | Result | Classification |
|---|---|---|
| `python -m pytest tests/test_kubernetes_manifests.py -q` | 31 passed | Independently verified (note: no lake-writer tests exist in this set) |
| `importlib.util.find_spec("services.lake_writer")` | `None` | Independently verified (defect — Finding 1) |
| `importlib.util.find_spec("services.lake-writer")` | Resolves to `services/lake-writer/__init__.py` | Independently verified |
| `python -m services.lake_writer.consumer` | `ModuleNotFoundError: No module named 'services.lake_writer'` | Independently verified (defect — Finding 1) |
| `python -m services.lake-writer.consumer` (hyphen, no env) | Reaches `run_consumer()`; fails only on missing `APP_ENVIRONMENT` (expected) | Independently verified |
| `kubectl apply --dry-run` / live cluster validation | Not performed | Unverified (no `kind` cluster available; `kubectl` present but no reachable API server) |
| `python -m pytest -m integration` | Not run | Unverified (requires Docker/Kafka/MinIO; the diff changes only a manifest and its README, not runtime code — see note below) |

Note on integration tests: TASK-074 changes only a manifest and its README; it does not modify the lake-writer runtime code (already covered by `tests/test_silver_writer_integration.py` from TASK-022). The meaningful unverified check for this task is a live `kubectl apply`/rollout, which would surface Finding 1 immediately via `kubectl logs`. The defect is reproducible without a cluster and would not be caught by any existing test (because no lake-writer manifest test exists).

## 5. Findings

### Finding 1 — HIGH — Pod crash-loops on startup: entrypoint uses an underscore module path that does not exist

- **File:** `kubernetes/deployments/lake-writer-deployment.yaml:40`
- **Problem:** `command: ["python", "-m", "services.lake_writer.consumer"]` uses `services.lake_writer` (underscore), but the package directory on disk is `services/lake-writer` (hyphen). Independently verified: `importlib.util.find_spec("services.lake_writer")` returns `None`, and `python -m services.lake_writer.consumer` exits with `ModuleNotFoundError: No module named 'services.lake_writer'`. The correct invocation is `python -m services.lake-writer.consumer` (hyphen), which is exactly the form already used and validated by the sibling raw-writer Deployment (`services.raw-writer.consumer`) after TASK-073's fix commit `1237c69`. The author copied the underscore form from the pre-existing (incorrect) service README (`services/lake-writer/README.md:40`) instead of the working raw-writer manifest convention.
- **Impact:** The Lake Writer pod fails at startup and enters `CrashLoopBackOff`. The task's core deliverable — a working Deployment — is non-functional as committed. This is the same class of entrypoint defect that TASK-073's `1237c69` fixed for raw-writer.
- **Recommendation:** Change the command to `["python", "-m", "services.lake-writer.consumer"]` (hyphen), matching the on-disk package name and the raw-writer manifest.

### Finding 2 — MODERATE — No manifest structure tests added for the Lake Writer Deployment

- **File:** `tests/test_kubernetes_manifests.py` (unchanged by this commit)
- **Problem:** TASK-073 established the pattern of adding a dedicated manifest test class (`TestRawWriterDeployment`, 8 tests: existence, apiVersion/kind, namespace, labels, selector↔template match, Kafka+MinIO env presence, MinIO secrets optional, no inbound ports, and a `command` assertion). TASK-074 adds the lake-writer Deployment but no `TestLakeWriterDeployment`. The existing suite passes (31 tests) precisely because nothing exercises the new manifest, so the underscore/hyphen defect (Finding 1) is invisible to CI.
- **Impact:** The manifest is unvalidated; a regression like Finding 1 cannot be caught. This under-delivers on the task's "Validate manifests/tests" rule and the established test convention.
- **Recommendation:** Add a `TestLakeWriterDeployment` class mirroring `TestRawWriterDeployment`, including a `test_lake_writer_deployment_command_uses_module_invocation` that asserts `container["command"] == ["python", "-m", "services.lake-writer.consumer"]` (hyphen).

### Finding 3 — MINOR — Service README documents an incorrect module name, which misled the manifest

- **File:** `services/lake-writer/README.md:40`
- **Problem:** The service README documents `python -m services.lake_writer.consumer` (underscore), which fails with `ModuleNotFoundError` because the package directory is `services/lake-writer` (hyphen). This pre-existing doc error (from TASK-022) is the direct source of the manifest's incorrect `command`. It mirrors the same README-vs-manifest inconsistency flagged for raw-writer in the TASK-073 review (Finding 4).
- **Impact:** Divergent run instructions persist; only the hyphenated module form works. Future deployment work (or a developer following the README) will reproduce the same defect.
- **Recommendation:** Correct the README to `python -m services.lake-writer.consumer` (hyphen) and align it with the raw-writer README and both manifests. (Correcting this file is implementation work, out of scope for this review.)

## 6. Non-Defect Observations

- **Cross-domain `APP_` config load is no longer a problem.** The TASK-073 review's Finding 1 (unknown `APP_` variables rejected when loading `KafkaConsumerSettings` + `MinIOSettings` sequentially) was resolved by commit `361612e`, and the current `libs/common/config.py` uses `extra="ignore"`. With the module path corrected, the lake-writer manifest's combined Kafka + MinIO env vars load correctly.
- **`APP_KAFKA_GROUP_ID=lake-writer`** matches the service README's documented default consumer group and the SPECIFICATION §6.4 boundary (consume `products.validated.v1`).
- **`APP_KAFKA_AUTO_OFFSET_RESET` is omitted**, relying on `KafkaConsumerSettings.kafka_auto_offset_reset` default `earliest`. Consistent with the raw-writer Deployment; correct for at-least-once + replay. The processor Deployment sets it explicitly, so this is only a minor manifest-consistency difference.
- **`APP_MINIO_ACCESS_KEY`/`APP_MINIO_SECRET_KEY` via `secretKeyRef` with `optional: true`** correctly avoids a pod crash before TASK-078 creates `lake-writer-secrets`; when unset, `MinIOSettings` falls back to `minioadmin`/`minioadmin-local`, matching the local Docker Compose MinIO root credentials.
- **`kafka:29092` and `http://minio:9000`** are forward references to the TASK-077 Kafka/MinIO Services, consistent with the docker-compose internal listeners and the sibling deployments.
- **`image: ai-data-platform/lake-writer:dev`** has no in-repo Dockerfile and `docker-compose.yml` builds no service images. Consistent with the TASK-071/TASK-072/TASK-073 convention; image packaging is deferred out of band.
- **No liveness/readiness/startup probes** — deliberately deferred to TASK-079 per `ai/ROADMAP.md` Milestone 8.
- **`APP_ENVIRONMENT=production`** for a local kind cluster follows the existing ingestion/processor/raw-writer precedent (flagged as Minor in the TASK-071 review). No functional impact today.
- **No inbound `ports` / no Service** — correct for a Kafka-consumer + object-storage-writer only.
- **Resources are specified** (`requests`/`limits`), matching the sibling deployments. The roadmap lists resources under TASK-079, but including them early is harmless and consistent with prior tasks.

## 7. Verdict

**CHANGES REQUIRED**

The manifest is structurally correct and appropriately scoped: it targets the `ai-data-platform` namespace with consistent `app.kubernetes.io` labels/selectors, externalizes Kafka and MinIO configuration using the correct `APP_`-prefixed settings contract, sources credentials from an optional Secret without committing secrets, exposes no inbound ports, and preserves the lake-writer's validated-event→Silver responsibility and at-least-once/idempotent semantics unchanged. The `kubernetes/README.md` documentation is complete and consistent.

However, the Deployment is not runnable: its container `command` references `services.lake_writer.consumer` (underscore), a module path that does not exist on disk — the actual package is `services/lake-writer` (hyphen). Independently verified via `find_spec` and `python -m`, the pod will exit with `ModuleNotFoundError: No module named 'services.lake_writer'` and crash-loop. This is a blocking functional defect in the task's core deliverable and is trivially fixable by aligning the command with the on-disk package name and the already-correct raw-writer manifest.

Blocking finding: **Finding 1 (High)**. Finding 2 (Moderate) should be addressed alongside it (add `TestLakeWriterDeployment` so this class of defect is caught by CI); Finding 3 (Minor) is a non-blocking documentation nit.
