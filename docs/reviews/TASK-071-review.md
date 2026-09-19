# TASK-071 — Ingestion Deployment — Independent Review

## 1. Review Header

- **Task ID:** TASK-071 — Ingestion Deployment
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review; no code modified)
- **Reviewed change set / Git range:** `46f56948905633a4fff406d57a6a1f1edf56f624..ed19fd2f165b95a31b073e26b7dbcbe668125022`
- **Reviewed HEAD:** `ed19fd2f165b95a31b073e26b7dbcbe668125022` on `feature/TASK-071`
- **Commits in range:**
  - `e362e37` — feat(TASK-071): ingestion Kubernetes Deployment
  - `ed19fd2` — fix(TASK-071): use APP_-prefixed env vars matching Pydantic settings
- **Scope:** `kubernetes/deployments/ingestion-deployment.yaml` (new), `kubernetes/README.md` (+16), `tests/test_kubernetes_manifests.py` (+43)
- **Verdict:** **APPROVED WITH NON-BLOCKING FINDINGS**

---

## 2. Requirements Coverage

Source of truth: `ai/tasks/TASK-071-ingestion-deployment.md`; cross-checked against `ai/PROJECT.md`, `ai/SPECIFICATION.md` §6.1/§19, `ai/ROADMAP.md` Milestone 8, `docs/adr/ADR-001-kafka-topic-configuration.md`, `docs/configuration.md`, `docs/kafka-producer.md`, and the ingestion service implementation (`services/ingestion/__main__.py`, `libs/common/config.py`, `libs/common/kafka_producer.py`).

| Requirement | Status | Implementation evidence |
|---|---|---|
| Add a Kubernetes Deployment for ingestion | **Met** | `kubernetes/deployments/ingestion-deployment.yaml` — `apps/v1` `Deployment`, `replicas: 1`, `command: ["python", "-m", "services.ingestion"]`, resource requests/limits. |
| Externalize Kafka/source config | **Met** | Env vars `APP_KAFKA_BOOTSTRAP_SERVERS`, `APP_KAFKA_RAW_TOPIC`, `INGESTION_INTERVAL_SECONDS`, and `BESTBUY_API_KEY` (via `secretKeyRef`). The `APP_`-prefixed names match the `env_prefix="APP_"` contract in `libs/common/config.py`; the unprefixed ones match the adapter-local `os.environ.get(...)` pattern. Independently verified below. |
| Preserve adapter/publisher architecture | **Met** | Runs the existing entrypoint unchanged; no new component, no architectural change, no direct PostgreSQL access introduced. |
| Consistent labels/selectors | **Met** | `app.kubernetes.io/name`/`part-of`/`component` labels; selector (`name`+`part-of`) is a valid subset of template labels (which also carry `component`). |
| Observable logs | **Met** | The service already emits structured logs (`libs/observability`, runner logs); the manifest does not suppress or override logging. |
| No unnecessary inbound Service | **Met** | No `Service` manifest; no `ports` in the container spec. |

---

## 3. Git Diff Review

Cumulative diff across the range: 3 files, 119 insertions, 0 deletions.

- **Files changed:**
  - `kubernetes/deployments/ingestion-deployment.yaml` (+60, new)
  - `kubernetes/README.md` (+16)
  - `tests/test_kubernetes_manifests.py` (+43)
- **Scope correctness:** All changes belong to TASK-071. The README documents the new Deployment; the test file extends the existing TASK-070 manifest tests with a `TestIngestionDeployment` class.
- **Unrelated changes:** None.
- **Architectural changes:** None. The manifest is a declarative wrapper around the existing ingestion entrypoint; it does not alter service boundaries, the canonical data flow, or the adapter/publisher model.
- **Accidental changes / dead code / secrets / generated artifacts:** None. No real secrets are committed; `BESTBUY_API_KEY` is sourced from a `Secret` with `optional: true`.
- **Dependency/configuration changes:** No new Python dependencies. Configuration is environment-variable based, consistent with `docs/configuration.md`.
- **Fix commit (`ed19fd2`):** Correctly renames `KAFKA_BOOTSTRAP_SERVERS` → `APP_KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_RAW_TOPIC` → `APP_KAFKA_RAW_TOPIC`, adds the required `APP_ENVIRONMENT=production`, and updates the test assertion to the corrected name. This resolves the two functional defects present in `e362e37` (missing required `environment`, and silently ignored Kafka settings).

---

## 4. Test and Verification Review

**Tests examined:** `tests/test_kubernetes_manifests.py` — 7 `TestIngestionDeployment` tests (existence, apiVersion/kind, namespace, labels, selector-matches-template, Kafka env presence, no inbound ports), in addition to the pre-existing `TestKindConfig` and `TestNamespaceManifest` tests.

**Test adequacy:** Adequate for structural manifest validation. The env-var assertion was corrected in the fix commit to assert `APP_KAFKA_BOOTSTRAP_SERVERS`, so it no longer encodes the defect. Two residual coverage gaps are noted in Findings M1 and M2 (the test does not assert `APP_ENVIRONMENT` or `APP_KAFKA_RAW_TOPIC`).

**Independently executed by the reviewer:**
- `python -m pytest tests/test_kubernetes_manifests.py -v` → **15 passed** in 0.28s. Status: **Independently verified**.
- `python -m ruff check tests/test_kubernetes_manifests.py` → **All checks passed**; `python -m ruff format --check tests/test_kubernetes_manifests.py` → **already formatted**. Status: **Independently verified**.
- Configuration-contract probe: with `APP_ENVIRONMENT=production`, `APP_KAFKA_BOOTSTRAP_SERVERS=kafka:29092`, `APP_KAFKA_RAW_TOPIC=products.raw.v1`, `KafkaProducerSettings()` resolves to `environment=production`, `bootstrap=kafka:29092`, `topic=products.raw.v1`, `client_id=ingestion`. Status: **Independently verified** — confirms the manifest env names match the application settings exactly.

**Implementation evidence reviewed (not rerun):**
- Full unit suite and `python -m pytest -m integration` were **not** rerun. This change is a manifest + hermetic manifest-test change only; it touches no runtime Kafka/persistence code, so no integration test exercises it. No integration-test results for this specific manifest were present in the diff.

**Unverified:** A live `kubectl apply --dry-run` / cluster-side validation was not performed (no cluster/`kubectl` context was used). The YAML is structurally validated by the passing tests and by manual inspection.

---

## 5. Findings

### M1 — Minor — `APP_ENVIRONMENT=production` is hardcoded for a local kind deployment

- **File:** `kubernetes/deployments/ingestion-deployment.yaml` (`APP_ENVIRONMENT` env entry)
- **Problem:** The manifest pins `APP_ENVIRONMENT=production`, but this is a local `kind` cluster, and `.env.example`/`docs/configuration.md` use `development` for local setups. The value is valid (`Environment = Literal["development", "production"]`) and currently has no behavioral effect, but it mislabels local telemetry/logs as production.
- **Impact:** Low — no functional impact today (the `environment` field is stored but not branched on anywhere in application code). Minor consistency/observability concern.
- **Recommendation:** Use `development` for the local kind Deployment (or source the value from a ConfigMap in TASK-078) to match the local-first convention.

### M2 — Minor — Test asserts only one of the three application env vars

- **File:** `tests/test_kubernetes_manifests.py` (`test_ingestion_deployment_has_kafka_env`)
- **Problem:** The test asserts `APP_KAFKA_BOOTSTRAP_SERVERS` is present but does not assert `APP_KAFKA_RAW_TOPIC` or the required `APP_ENVIRONMENT`. The missing `APP_ENVIRONMENT` was exactly the crash-loop defect that `ed19fd2` had to fix, so the current test would not catch a regression that removes it.
- **Impact:** Low — the manifest is currently correct; this is a test-hardening gap rather than a live defect.
- **Recommendation:** Extend the assertion to require all three application-managed env vars (`APP_ENVIRONMENT`, `APP_KAFKA_BOOTSTRAP_SERVERS`, `APP_KAFKA_RAW_TOPIC`) so the test enforces the documented configuration contract.

---

## 6. Non-Defect Observations

- **`kafka:29092` bootstrap value is a forward reference.** It assumes TASK-077 creates a Service named `kafka` in `ai-data-platform` exposing port 29092. Consistent with the docker-compose internal listener (`PLAINTEXT://kafka:29092`) and the README, but TASK-071 alone cannot be verified against a live Kafka. Track for TASK-077.
- **`image: ai-data-platform/ingestion:dev` has no build path in the repo.** No `Dockerfile` exists and `docker-compose.yml` does not build an ingestion image; the README documents the manual `kind load docker-image` workflow. Image packaging is deferred outside TASK-071 scope; flag for the milestone/CI task that owns container builds.
- **`command: ["python", "-m", "services.ingestion"]` relies on the image's default `WORKDIR` being the project root** (so the `services` package is importable). Since the image is not yet defined, this is a packaging forward reference, not a TASK-071 defect.
- **No liveness/readiness/startup probes.** Deliberately deferred to TASK-079 per `ai/ROADMAP.md` Milestone 8.
- **`imagePullPolicy: IfNotPresent` with a mutable `:dev` tag** is acceptable for the local kind + manual `kind load docker-image` workflow.
- **`BESTBUY_API_KEY` via `secretKeyRef` with `optional: true`** correctly avoids a pod crash before TASK-078 creates the `ingestion-secrets` Secret; the adapter logs a warning and continues with the Fake Store source.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The Deployment is correct and functional as written for TASK-071: it targets the `ai-data-platform` namespace with consistent `app.kubernetes.io` labels/selectors, runs the existing ingestion entrypoint without architectural change, externalizes Kafka/source configuration using the correct `APP_`-prefixed (and adapter-local) environment variables, exposes no inbound ports, and sources the optional Best Buy API key from a Secret without committing secrets. The fix commit (`ed19fd2`) resolves the two functional defects that existed at `e362e37` (missing required `APP_ENVIRONMENT`, and incorrectly named Kafka env vars that would have been silently ignored). The manifest tests pass and lint clean.

The two findings are Minor and non-blocking: a cosmetic `APP_ENVIRONMENT=production` value for a local cluster, and a test-hardening gap that does not assert the full set of application env vars. The remaining observations are forward references to later tasks (TASK-077 Kafka Service, image packaging, TASK-079 probes).
