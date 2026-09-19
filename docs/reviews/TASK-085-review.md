# TASK-085 Review — Grafana Deployment

## 1. Review Header

- **Task ID:** TASK-085
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `e0fa82a95ec9827f698d29635fa5eadb8c4cc795...bc1709173d2f73fbf38527c91796709e54128b0d`
- **Reviewed HEAD:** `bc1709173d2f73fbf38527c91796709e54128b0d` on `feature/TASK-085`
- **Commits reviewed:**
  - `41b4cd034dbaec1a1fbb3c034023b81f629d794b` — `feat(TASK-085): Add Grafana deployment with Prometheus datasource`
  - `693b024dab0037014c69d8f080130c6148f35f42` — `docs: Record TASK-085 Qwen review (CHANGES REQUIRED round 1)`
  - `bc1709173d2f73fbf38527c91796709e54128b0d` — `fix(TASK-085): Fix credential encoding, provisioning mount paths, healthcheck`
- **Scope:** Grafana deployment via Docker Compose and Helm, Prometheus datasource provisioning, credential externalization, local-access documentation, and deterministic tests.
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

## 2. Requirements Coverage

Requirements sourced from `ai/tasks/TASK-085-grafana-deployment.md`, with context from `ai/PROJECT.md` (§10 Observability, §11 Security), `ai/SPECIFICATION.md` (§20 Observability, §21 Security, §26 Local Development Environment), `ai/ROADMAP.md` (Milestone 10), and `ai/AGENTS.md`.

| Requirement | Status | Evidence |
|---|---|---|
| Deploy/provision Grafana using established Kubernetes/Helm conventions | ✅ Met | Docker Compose `grafana` service (`docker-compose.yml`) and Helm templates (`helm/ai-data-platform/templates/monitoring/grafana-{configmap,deployment,secret,service}.yaml`). Mirrors the TASK-084 Prometheus structure; Secret now matches the `templates/secrets/minio-credentials.yaml` `\| quote` convention. |
| Connect Grafana reproducibly to Prometheus | ✅ Met | Compose datasource provisioning (`monitoring/grafana/datasources/prometheus.yml`) is correct. Helm datasource ConfigMap is now mounted into `/etc/grafana/provisioning/datasources/datasources.yml` (fixed in `bc17091`), so Grafana discovers it. |
| Externalize credentials (no secrets committed) | ✅ Met | Compose uses env vars (`GF_SECURITY_ADMIN_USER/PASSWORD`); Helm uses a Secret with base64 values and no double-encoding (fixed in `bc17091`). Only `admin`/`admin` placeholders, no real secrets. |
| Document local access | ✅ Met | `monitoring/README.md` documents Compose startup, default credentials, env-var overrides, Helm enablement, and `kubectl port-forward`. |
| Platform-specific dashboards deferred to later tasks | ✅ Met | Only provisioning scaffolding present; no dashboards added (correctly deferred to TASK-086+). |
| Keep dashboards/provisioning version-controlled and reproducible | ✅ Met | Provisioning files committed under `monitoring/grafana/` and a Helm ConfigMap. |
| Implement only this task; no unrelated changes/secrets | ✅ Met | Diff is scoped to Grafana + its tests + docs (see §3). |
| Deterministic validation/tests | ⚠️ Partial | Compose/provisioning tests are solid and pass. Helm rendering tests exist but are skipped locally (helm not installed); the mount-path fix (F1 round 1) is not covered by any regression test (F1 below). |

## 3. Git Diff Review

**Range:** `e0fa82a95ec9827f698d29635fa5eadb8c4cc795...bc1709173d2f73fbf38527c91796709e54128b0d` (3 commits, 12 files, +607/−1).

Files changed:

- `docker-compose.yml` — adds `grafana` service + `grafana_data` volume; healthcheck uses `wget` (fixed).
- `helm/ai-data-platform/templates/monitoring/grafana-configmap.yaml` (new)
- `helm/ai-data-platform/templates/monitoring/grafana-deployment.yaml` (new; mount paths fixed)
- `helm/ai-data-platform/templates/monitoring/grafana-secret.yaml` (new; double-encoding removed)
- `helm/ai-data-platform/templates/monitoring/grafana-service.yaml` (new)
- `helm/ai-data-platform/values.yaml` — adds `grafana` section (disabled by default, base64 credentials).
- `monitoring/README.md` — Grafana documentation.
- `monitoring/grafana/dashboards/dashboard.yml` (new)
- `monitoring/grafana/datasources/prometheus.yml` (new)
- `tests/test_grafana_deployment.py` (new)
- `tests/test_helm_chart.py` — adds Grafana structural + rendering tests.
- `docs/reviews/TASK-085-review.md` — the prior round-1 review record (replaced by this report).

**Scope correctness:** All changes belong to TASK-085. No unrelated task changes mixed in.

**Unrelated/accidental changes:** None observed.

**Architectural changes:** None. Grafana is added as an observability consumer alongside Prometheus; it does not touch the event pipeline, data-lake, or warehouse boundaries. Service-boundary ownership is preserved.

**Dependency/config changes:** No new Python dependencies. New container image `grafana/grafana:11.4.0` (consistent with Prometheus `prom/prometheus:v3.1.0`). Helm values add a `grafana` section disabled by default.

**Debug/temp/dead code/secrets:** None committed. No generated artifacts or real credentials.

### Round-1 findings resolution

The prior review (`CHANGES REQUIRED`) raised three findings, all of which are resolved in `bc17091`:

- **F1 (round 1) — Helm Secret double-encoding:** Resolved. The template now uses `{{ .Values.grafana.adminUser | quote }}` / `{{ .Values.grafana.adminPassword | quote }}` with base64 values (`YWRtaW4=`), matching the `minio-credentials` convention. Verified: `test_grafana_secret_contains_admin_credentials` decodes `YWRtaW4=` → `admin` and will pass.
- **F2 (round 1) — Helm provisioning ConfigMap mounted at wrong path:** Resolved. The Deployment now projects the two ConfigMap keys into the correct subdirectories (`/etc/grafana/provisioning/datasources/datasources.yml` and `/etc/grafana/provisioning/dashboards/dashboards.yml`) via per-key `items.path`.
- **F3 (round 1) — Compose healthcheck used `curl`:** Resolved. The healthcheck now uses `wget --spider -q http://localhost:3000/api/health`, matching the Prometheus service and the Alpine/busybox tooling.

## 4. Test and Verification Review

**Tests added/changed:**

- `tests/test_grafana_deployment.py` (new, 15 tests): validates the Compose service definition, provisioning file contents, and monitoring documentation. No Docker daemon required.
- `tests/test_helm_chart.py`: adds Grafana structural checks plus `TestHelmTemplate` cases (enabled/disabled, probes/resources, Secret credentials, ConfigMap datasource).

**Independently verified (executed by reviewer):**

- `python -m pytest tests/test_grafana_deployment.py tests/test_helm_chart.py -q` → **38 passed, 26 skipped**. The 26 skipped are `_helm_template`/`_helm_lint` tests (helm binary not installed in this environment).
- `python -m ruff check tests/test_grafana_deployment.py tests/test_helm_chart.py` → **All checks passed**.
- `python -m ruff format --check tests/test_grafana_deployment.py tests/test_helm_chart.py` → **2 files already formatted**.
- YAML parse of `docker-compose.yml` and `helm/ai-data-platform/values.yaml` → **valid**.

**Implementation evidence reviewed (not rerun):**

- CI workflow (`.github/workflows/ci.yml`) installs Helm (`azure/setup-helm@v4`) and runs `pytest`, so the Helm rendering/lint tests will execute in CI rather than being skipped as they are locally.

**Unverified:**

- Helm rendering/lint could not be executed locally (helm not available). The Helm templates were instead reviewed manually against Kubernetes mount semantics (see §5 F1 round 2). `mypy` was not rerun; the change set is YAML/docs/tests with no Python production-code changes, so type-check impact is nil.

**Integration tests:** Not applicable — TASK-085 is configuration/infrastructure only and does not touch Kafka, persistence, MinIO/S3, or other integration boundaries. The `-m integration` requirement does not apply.

## 5. Findings

### F1 — Moderate — Helm provisioning mount-path fix lacks a regression test

- **Files:** `tests/test_helm_chart.py`; `helm/ai-data-platform/templates/monitoring/grafana-deployment.yaml`.
- **Problem:** The round-1 F2 (datasource never loaded because the ConfigMap was mounted at the wrong path) was a High-severity functional defect. Its fix in `bc17091` changed the volume/volumeMount wiring, but no test was added to assert the mount target. `test_grafana_deployment_has_probes_and_resources` checks probes/resources/image only, and `test_grafana_configmap_has_datasource` checks the ConfigMap data only — neither asserts `volumeMounts`/`volumes`.
- **Impact:** A future regression in the mount path (e.g., reverting to mounting the whole ConfigMap at `/etc/grafana/provisioning`) would silently break datasource provisioning in the Helm path and would not be caught by the suite.
- **Recommendation:** Add a rendering assertion that the Grafana container mounts `provisioning-datasources` at `/etc/grafana/provisioning/datasources` (and the dashboard analog at the corresponding subdirectory), or that the rendered volumes project `items[].key`/`items[].path` correctly.

### F2 — Minor — `monitoring/README.md` Helm command enables Grafana but not Prometheus

- **File:** `monitoring/README.md` (Kubernetes section).
- **Problem:** The documented enable command is `helm upgrade --install ai-data-platform helm/ai-data-platform --set grafana.enabled=true`, but the provisioned datasource points to `http://prometheus:9090`, and Prometheus is also `enabled: false` by default.
- **Impact:** A user following the documented command literally gets a Grafana whose single Prometheus datasource is unreachable (no `prometheus` Service exists in the namespace), which looks broken even though the deployment is technically correct.
- **Recommendation:** Document enabling both, e.g. `--set prometheus.enabled=true --set grafana.enabled=true`, or add a note that the Prometheus datasource requires TASK-084's Prometheus deployment to be enabled in-cluster.

### F3 — Minor — `.env.example` does not document the new Grafana Compose variables

- **Files:** `.env.example`; `docker-compose.yml`.
- **Problem:** `docker-compose.yml` introduces `${GRAFANA_HOST_PORT:-3000}`, `${GRAFANA_ADMIN_USER:-admin}`, and `${GRAFANA_ADMIN_PASSWORD:-admin}`, but `.env.example` (which documents Compose-level variables) does not list them.
- **Impact:** Minor discoverability gap for credential/port overrides. The pattern is consistent with TASK-084, which likewise omitted `PROMETHEUS_HOST_PORT` from `.env.example`.
- **Recommendation:** Add commented entries for the Grafana (and, if desired, Prometheus) host-port and credential variables to `.env.example`, or confirm the Compose-level variables are intentionally documented only in `monitoring/README.md`.

## 6. Non-Defect Observations

- **Helm vs Compose dashboards source path discrepancy.** The Helm `dashboards.yml` provider points to `/var/lib/grafana/dashboards`, while the Compose `dashboard.yml` points to `/etc/grafana/provisioning/dashboards`. Harmless now (no dashboards exist yet), but TASK-086 should reconcile the two so a single dashboard directory works across both deployment modes.
- **Helm Grafana data uses `emptyDir` (ephemeral).** Matches the Prometheus precedent and is acceptable for local development; a PVC would be reasonable future hardening, not required by TASK-085.
- **ClusterIP service with no Ingress.** Local access is via `kubectl port-forward`, consistent with the local-first scope and documented in the README.
- **`grafana.adminUser`/`adminPassword` use camelCase.** Consistent with the existing `secrets.bestbuyApiKey` convention; not a defect.

## 7. Verdict

**`APPROVED WITH NON-BLOCKING FINDINGS`**

The three blocking findings from the round-1 review are all resolved in `bc17091`:

- Secret double-encoding removed (now matches the established base64 + `quote` convention).
- Provisioning ConfigMap mounted into the correct `datasources/` and `dashboards/` subdirectories.
- Compose healthcheck switched from `curl` to `wget`.

The Docker Compose path is correct and well-tested. The remaining items are non-blocking: one Moderate test-coverage gap (F1 — the mount-path fix is not regression-tested) and two Minor documentation gaps (F2, F3). These should be addressed in a follow-up but do not prevent acceptance of the current change set.
