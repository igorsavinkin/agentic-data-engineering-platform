# TASK-074 Review — Lake Writer Deployment (Round 2)

## 1. Review Header

| Field | Value |
|---|---|
| Task ID | TASK-074 — Lake Writer Deployment |
| Review date | 2026-09-19 |
| Reviewer | Qwen Code (independent review, no code modified) |
| Reviewed change set / Git range | `b7ecd8b5c5ab2544cf4dad2a19158e7850b8d586..075621fe74f8dd1b5dc1a7046f59da8a10773a10` |
| Reviewed HEAD | `075621fe74f8dd1b5dc1a7046f59da8a10773a10` on `feature/TASK-074` |
| Commits in range | `e512992` feat(TASK-074): Kubernetes Deployment for Lake Writer Service<br>`11f67b3` fix(TASK-074): use hyphen module path and add manifest tests<br>`075621f` docs: Record TASK-074 Qwen review (CHANGES REQUIRED, round 1) |
| Scope | `kubernetes/deployments/lake-writer-deployment.yaml` (new), `kubernetes/README.md`, `services/lake-writer/README.md` (1-line fix), `tests/test_kubernetes_manifests.py` (+`TestLakeWriterDeployment`), `docs/reviews/TASK-074-review.md` (round 1, superseded by this report) |
| Round | 2 (re-review after fix commit `11f67b3` addressed the round-1 findings) |
| Verdict | **APPROVED WITH NON-BLOCKING FINDINGS** |

Sources of authority consulted: `ai/tasks/TASK-074-lake-writer-deployment.md`, `ai/PROJECT.md` (§4, §5, §6, §9), `ai/SPECIFICATION.md` (§6.4, §19), `ai/ROADMAP.md` (Milestone 8), `ai/AGENTS.md` (§4, §5, §7, §8), the lake-writer implementation (`services/lake-writer/consumer.py`, `libs/lake_writer/silver_writer.py`, `libs/common/config.py`, `libs/common/kafka_consumer.py`, `libs/common/minio_storage.py`), the sibling TASK-071/TASK-072/TASK-073 deployments, and the round-1 TASK-074 review report.

## 2. Requirements Coverage

Source of truth: `ai/tasks/TASK-074-lake-writer-deployment.md`; cross-checked against `ai/PROJECT.md`, `ai/SPECIFICATION.md` §6.4/§19, `ai/ROADMAP.md` Milestone 8, and `ai/AGENTS.md`.

| Requirement | Status | Implementation evidence |
|---|---|---|
| Add a Lake Writer Deployment | **Met** | `kubernetes/deployments/lake-writer-deployment.yaml` — new `apps/v1` `Deployment`, namespace `ai-data-platform`, `replicas: 1` |
| Preserve validated-event→Silver responsibility | **Met** | Targets `services/lake-writer/consumer.py`, which consumes `products.validated.v1` and persists Silver Parquet via `SilverWriter`; no PostgreSQL access, no architectural change |
| Preserve schema/partition/idempotency semantics | **Met (manifest-level)** | No runtime code change; the manifest runs the same commit-after-write entrypoint; deterministic `event_id`-derived S3 keys and Silver schema live in `libs/lake_writer/silver_writer.py` |
| Separate service boundary | **Met** | Own `Deployment`, own consumer group (`lake-writer`), no coupling to processor/raw-writer/warehouse |
| Externalize Kafka config | **Met** | `APP_KAFKA_BOOTSTRAP_SERVERS`, `APP_KAFKA_GROUP_ID` match the `APP_`-prefixed `KafkaConsumerSettings` contract |
| Externalize object-storage config | **Met** | `APP_MINIO_ENDPOINT`, `APP_MINIO_ACCESS_KEY`, `APP_MINIO_SECRET_KEY` match `MinIOSettings`; `APP_MINIO_BUCKET_SILVER` omitted, correctly relying on the `silver` default |
| Reference Secrets, never literal credentials | **Met** | MinIO credentials via `secretKeyRef` (name `lake-writer-secrets`, `optional: true`); no literal secrets committed |
| Consistent labels/selectors | **Met** | `app.kubernetes.io/name`/`part-of`/`component` labels; selector (`name`+`part-of`) is a valid subset of template labels |
| No inbound Service | **Met** | No `Service` manifest; no `ports` in the container spec |
| Declarative manifests | **Met** | Single declarative YAML; no imperative scripting |
| Runnable entrypoint (module resolves) | **Met** | `command: ["python", "-m", "services.lake-writer.consumer"]` uses the hyphenated package that exists on disk. Independently verified: `find_spec("services.lake-writer")` resolves to `services/lake-writer/__init__.py`, and `importlib.import_module("services.lake-writer.consumer")` succeeds. Round-1 Finding 1 resolved |
| Runnable pod (acceptance behavior demonstrated) | **Met (manifest-level)** | Entrypoint resolves and imports cleanly. Live `kubectl apply`/rollout remains unverified (no cluster available), but the round-1 `ModuleNotFoundError`/`CrashLoopBackOff` root cause is eliminated |
| Documentation updated | **Met** | `kubernetes/README.md` adds a Lake Writer section, directory-tree entry, and image-load entries; `services/lake-writer/README.md` run command corrected to hyphen |
| Validate manifests/tests | **Met** | `TestLakeWriterDeployment` added (9 tests) mirroring the TASK-073 `TestRawWriterDeployment` precedent, including a `command` assertion that pins the hyphenated module path. Round-1 Finding 2 resolved |
| No unrelated changes / no real secrets | **Met** | Diff scoped to the lake-writer manifest, its tests, and docs; no secrets, no new dependencies, no architectural change |

## 3. Git Diff Review

Changed files:

- `kubernetes/deployments/lake-writer-deployment.yaml` (new, 68 lines) — Lake Writer Deployment. In scope.
- `kubernetes/README.md` (+16/−4) — docs: directory tree + Lake Writer section + image-load entries. In scope.
- `services/lake-writer/README.md` (1 line) — run command corrected from `services.lake_writer.consumer` to `services.lake-writer.consumer`. In scope (fixes round-1 Finding 3).
- `tests/test_kubernetes_manifests.py` (+59) — adds `LAKE_WRITER_DEPLOYMENT` constant and `TestLakeWriterDeployment` (9 tests). In scope (fixes round-1 Finding 2).
- `docs/reviews/TASK-074-review.md` (new) — the round-1 review report, superseded by this round-2 report. In scope.

Assessment:

- **Scope correctness:** All changes belong to TASK-074. No unrelated files modified.
- **Architectural changes:** None. The manifest is a declarative wrapper around the existing lake-writer entrypoint; no service boundary, event contract, topic ownership, or consumer-group change.
- **Accidental changes / dead code / debugging artifacts / generated files / secrets:** None. No real secrets committed (`secretKeyRef` + `optional: true` only).
- **Dependency/configuration changes:** No new Python or tooling dependencies. Configuration is `APP_`-prefixed environment variables, consistent with `libs/common/config.py`.
- **Branch/task isolation:** Correct — all three commits are on `feature/TASK-074` and match the requested range. Working tree is clean apart from this review file.

## 4. Test and Verification Review

**Tests examined:** `tests/test_kubernetes_manifests.py` now contains `TestKindConfig`, `TestNamespaceManifest`, `TestIngestionDeployment`, `TestProcessorDeployment`, `TestRawWriterDeployment` (9 tests), and the newly added `TestLakeWriterDeployment` (9 tests). The new class mirrors the raw-writer precedent exactly: existence, apiVersion/kind, namespace, labels, selector↔template match, Kafka+MinIO env presence, MinIO secrets optional, no inbound ports, and a `command` assertion that pins `["python", "-m", "services.lake-writer.consumer"]`.

**Test adequacy:** Adequate. The `test_lake_writer_deployment_command_uses_module_invocation` assertion would have caught the round-1 underscore/hyphen defect and now locks the correct value in CI. Coverage now matches the established TASK-073 convention.

| Check | Result | Classification |
|---|---|---|
| `python -m pytest tests/test_kubernetes_manifests.py -q` | 40 passed | Independently verified |
| `python -m pytest tests/test_kubernetes_manifests.py -q -k LakeWriter` | 9 passed, 31 deselected | Independently verified |
| `python -m ruff check tests/test_kubernetes_manifests.py` | All checks passed | Independently verified |
| `python -m mypy tests/test_kubernetes_manifests.py` | Success: no issues found | Independently verified |
| `importlib.util.find_spec("services.lake-writer")` | Resolves to `services/lake-writer/__init__.py` | Independently verified |
| `importlib.util.find_spec("services.lake_writer")` | `None` (underscore path absent) | Independently verified |
| `importlib.import_module("services.lake-writer.consumer")` | Imports; `VALIDATED_TOPIC == "products.validated.v1"` | Independently verified |
| `kubectl apply --dry-run` / live cluster rollout | Not performed | Unverified (no `kind` cluster available) |
| `python -m pytest -m integration` | Not run | Unverified (requires Docker/Kafka/MinIO; the diff changes only a manifest, its test, and docs — lake-writer runtime is already covered by `tests/test_silver_writer_integration.py` from TASK-022) |

Note on integration tests: TASK-074 does not modify lake-writer runtime code, so the meaningful verification for this task is the manifest test suite and the entrypoint module resolution — both independently confirmed. The one remaining unverified check is a live `kubectl apply`/rollout; the round-1 blocking defect was reproducible without a cluster and is now confirmed resolved via `find_spec` + `import_module` + the pinning test.

## 5. Findings

### Round-1 findings — status

- **Finding 1 (was HIGH)** — Pod crash-loops on underscore module path → **RESOLVED.** `command` is now `["python", "-m", "services.lake-writer.consumer"]` (hyphen); independently verified via `find_spec` and `import_module`.
- **Finding 2 (was MODERATE)** — No manifest structure tests → **RESOLVED.** `TestLakeWriterDeployment` (9 tests) added; 40 manifest tests pass.
- **Finding 3 (was MINOR)** — Service README documented underscore module name → **RESOLVED.** `services/lake-writer/README.md` corrected to `python -m services.lake-writer.consumer`.

### Finding 1 — MINOR — Service README configuration table lists non-`APP_` environment variable names

- **File:** `services/lake-writer/README.md` (Configuration table, unchanged by this diff)
- **Problem:** The "Configuration" table documents `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET_SILVER`, `KAFKA_BOOTSTRAP_SERVERS`, and `KAFKA_GROUP_ID`. The actual settings contract (`libs/common/config.py`, `env_prefix="APP_"`) reads `APP_MINIO_ENDPOINT`, `APP_MINIO_ACCESS_KEY`, `APP_MINIO_SECRET_KEY`, `APP_MINIO_BUCKET_SILVER`, `APP_KAFKA_BOOTSTRAP_SERVERS`, and `APP_KAFKA_GROUP_ID`. The manifest itself uses the correct `APP_`-prefixed names, but a developer following the README's Configuration table would set non-`APP_` variables that the service silently ignores.
- **Impact:** Misleading local run instructions; the discrepancy could cause "why is my `MINIO_ENDPOINT` override ignored?" confusion. No impact on the Deployment, which is correct.
- **Recommendation:** Correct the Configuration table to the `APP_`-prefixed names (and note the `minioadmin`/`minioadmin-local` defaults). This is a pre-existing TASK-022 documentation inconsistency and is outside TASK-074's strict diff scope, so it is non-blocking.

## 6. Non-Defect Observations

- **The round-1 HIGH defect is fully closed.** `command` uses the hyphenated package; `find_spec("services.lake-writer")` resolves, `find_spec("services.lake_writer")` is `None`, and `import_module` of the full entrypoint succeeds (including all `libs.*` imports).
- **Cross-domain `APP_` config load is correct.** `libs/common/config.py` uses `extra="ignore"` and `env_prefix="APP_"`, so the manifest's combined Kafka + MinIO `APP_` variables load cleanly through `KafkaConsumerSettings` and `MinIOSettings` (both require `APP_ENVIRONMENT`, which the manifest sets to `production`).
- **`APP_MINIO_BUCKET_SILVER` is intentionally omitted**, relying on `MinIOSettings.minio_bucket_silver` default `silver` — correct and consistent with the sibling raw-writer Deployment.
- **`APP_KAFKA_GROUP_ID=lake-writer`** matches the service README's documented consumer group and the SPECIFICATION §6.4 boundary (consume `products.validated.v1`).
- **`APP_KAFKA_AUTO_OFFSET_RESET` is omitted**, relying on `KafkaConsumerSettings.kafka_auto_offset_reset` default `earliest` — correct for at-least-once + replay.
- **MinIO credentials via `secretKeyRef` with `optional: true`** correctly avoids a pod crash before TASK-078 creates `lake-writer-secrets`; when unset, `MinIOSettings` falls back to `minioadmin`/`minioadmin-local`.
- **`kafka:29092` and `http://minio:9000`** are forward references to the TASK-077 Kafka/MinIO Services, consistent with the sibling deployments.
- **`image: ai-data-platform/lake-writer:dev`** has no in-repo Dockerfile; consistent with the TASK-071/TASK-072/TASK-073 convention (image packaging deferred out of band).
- **No liveness/readiness/startup probes** — deliberately deferred to TASK-079 per `ai/ROADMAP.md` Milestone 8.
- **`APP_ENVIRONMENT=production`** for a local kind cluster follows the existing ingestion/processor/raw-writer precedent.
- **No inbound `ports` / no Service** — correct for a Kafka-consumer + object-storage-writer only.
- **Resources are specified** (`requests`/`limits`), matching the sibling deployments; harmless even though the roadmap lists resources under TASK-079.

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The round-1 blocking defect (underscore module path → `ModuleNotFoundError` → `CrashLoopBackOff`) is resolved: the manifest now invokes `python -m services.lake-writer.consumer` (hyphen), independently confirmed to resolve and import cleanly. The round-1 Moderate coverage gap is closed by the new `TestLakeWriterDeployment` (9 tests), and the round-1 Minor README nit is fixed. All 40 manifest tests pass, and `ruff`/`mypy` are clean.

The manifest is structurally correct and appropriately scoped: it targets the `ai-data-platform` namespace with consistent `app.kubernetes.io` labels/selectors, externalizes Kafka and MinIO configuration using the correct `APP_`-prefixed settings contract, sources credentials from an optional Secret without committing secrets, exposes no inbound ports, and preserves the lake-writer's validated-event→Silver responsibility and at-least-once/idempotent semantics unchanged.

The only remaining finding is a Minor, pre-existing, out-of-scope documentation inconsistency in `services/lake-writer/README.md` (Configuration table lists non-`APP_` variable names); it does not block acceptance. Live `kubectl apply`/rollout remains unverified pending a `kind` cluster, but the previously blocking entrypoint defect is conclusively eliminated.
