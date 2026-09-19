# TASK-085 Review — Grafana Deployment

## 1. Review Header

- **Task ID:** TASK-085
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `e0fa82a95ec9827f698d29635fa5eadb8c4cc795...41b4cd034dbaec1a1fbb3c034023b81f629d794b`
- **Reviewed HEAD:** `41b4cd034dbaec1a1fbb3c034023b81f629d794b` on `feature/TASK-085`
- **Commits reviewed:** `41b4cd0` (`feat(TASK-085): Add Grafana deployment with Prometheus datasource`)
- **Scope:** Grafana deployment via Docker Compose and Helm, Prometheus datasource provisioning, credential externalization, local-access documentation, and deterministic tests.
- **Verdict:** `CHANGES REQUIRED`

## 2. Requirements Coverage

Requirements sourced from `ai/tasks/TASK-085-grafana-deployment.md`, with context from `ai/PROJECT.md`, `ai/SPECIFICATION.md` (§20 Observability, §26 Local Development), `ai/ROADMAP.md` (Milestone 10), and `ai/AGENTS.md`.

| Requirement | Status | Evidence |
|---|---|---|
| Deploy/provision Grafana using established Kubernetes/Helm conventions | ⚠️ Partial | Docker Compose service (`docker-compose.yml`) and Helm templates (`helm/ai-data-platform/templates/monitoring/grafana-*.yaml`). Follows the Prometheus (TASK-084) structure, but see F1/F2. |
| Connect Grafana reproducibly to Prometheus | ❌ Partial (Helm broken) | Compose datasource provisioning is correct; Helm datasource is mis-mounted and never loaded (F2). |
| Externalize credentials (no secrets committed) | ⚠️ Partial | Compose uses env vars (`GF_SECURITY_ADMIN_USER/PASSWORD`); Helm uses a Secret, but the Secret double-encodes the value so the documented default does not work (F1). Defaults are placeholders (`admin`/`admin`), not real secrets. |
| Document local access | ✅ Met | `monitoring/README.md` documents Compose startup, default credentials, env-var overrides, Helm enablement, and `kubectl port-forward`. |
| Platform-specific dashboards deferred to later tasks | ✅ Met | Only provisioning scaffolding is present; no dashboards added (correctly deferred to TASK-086+). |
| Keep dashboards/provisioning version-controlled and reproducible | ✅ Met | Provisioning files committed under `monitoring/grafana/` and Helm ConfigMap. |
| Implement only this task; no unrelated changes/secrets | ✅ Met | Diff is scoped to Grafana + its tests + docs (see §3). |
| Deterministic validation/tests | ⚠️ Partial | Compose/provisioning tests are solid; Helm rendering tests exist but are skipped locally and one would fail in CI (F1, §4). |

## 3. Git Diff Review

**Range:** `e0fa82a...41b4cd0` (1 commit, 11 files, +448/−1).

Files changed:

- `docker-compose.yml` — adds `grafana` service + `grafana_data` volume.
- `helm/ai-data-platform/templates/monitoring/grafana-configmap.yaml` (new)
- `helm/ai-data-platform/templates/monitoring/grafana-deployment.yaml` (new)
- `helm/ai-data-platform/templates/monitoring/grafana-secret.yaml` (new)
- `helm/ai-data-platform/templates/monitoring/grafana-service.yaml` (new)
- `helm/ai-data-platform/values.yaml` — adds `grafana` section.
- `monitoring/README.md` — Grafana documentation.
- `monitoring/grafana/dashboards/dashboard.yml` (new)
- `monitoring/grafana/datasources/prometheus.yml` (new)
- `tests/test_grafana_deployment.py` (new)
- `tests/test_helm_chart.py` — adds Grafana structural + rendering tests.

**Scope correctness:** All changes belong to TASK-085. No unrelated task changes were mixed in.

**Unrelated/accidental changes:** None observed.

**Architectural changes:** None. Grafana is added as an observability consumer alongside Prometheus; it does not touch the event pipeline, data-lake, or warehouse boundaries. Service boundary ownership is preserved.

**Dependency/config changes:** No new Python dependencies. New container image `grafana/grafana:11.4.0` (consistent with Prometheus `prom/prometheus:v3.1.0`). Helm values add a `grafana` section disabled by default.

**Debug/temp/dead code/secrets:** None committed. No generated artifacts or real credentials.

## 4. Test and Verification Review

**Tests added/changed:**

- `tests/test_grafana_deployment.py` (new, 15 tests): validates the Compose service definition, provisioning file contents, and monitoring documentation. No Docker daemon required.
- `tests/test_helm_chart.py`: adds Grafana entries to the structural checks plus `TestHelmTemplate` cases for Grafana rendering (enabled/disabled, probes/resources, Secret credentials, ConfigMap datasource).

**Independently verified (executed by reviewer):**

- `python -m pytest tests/test_grafana_deployment.py -q` → **15 passed**.
- `python -m pytest tests/test_helm_chart.py -q` → **23 passed, 26 skipped** (Helm CLI not installed locally; all `_helm_template`/`_helm_lint` tests are skipped).
- `python -m ruff check tests/test_grafana_deployment.py tests/test_helm_chart.py` → **passed**.

**Implementation evidence reviewed (not rerun):**

- CI workflow (`.github/workflows/ci.yml`) installs Helm (`azure/setup-helm@v4`, v3.16.0) and runs `pytest`. Therefore the Helm rendering tests will execute in CI, not be skipped.

**Critical observation on test adequacy:**

- The new `test_grafana_secret_contains_admin_credentials` asserts the rendered Secret decodes to `admin`. Given the double-encoding defect (F1), this test **will fail in CI** — it is a correct regression test whose expectation the implementation does not satisfy. The author's local environment lacks `helm`, so the Helm rendering path was never actually exercised against the committed values.
- No test verifies the ConfigMap mount location for provisioning files, so F2 (datasource never loaded) is not caught by any test.

**Integration tests:** Not applicable — TASK-085 is configuration/infrastructure only and does not touch Kafka, persistence, MinIO/S3, or other integration boundaries. The `-m integration` requirement does not apply.

**Unverified:** `mypy` and full `ruff format --check` were not independently rerun; the change set is YAML/docs/tests with no Python production code changes, so type-check impact is nil.

## 5. Findings

### F1 — High — Helm Secret double-encodes Grafana admin credentials

- **Files:** `helm/ai-data-platform/templates/monitoring/grafana-secret.yaml` (lines 14–15); `helm/ai-data-platform/values.yaml` (`grafana.adminUser`/`grafana.adminPassword`).
- **Problem:** `values.yaml` stores the credentials already base64-encoded (`adminUser: YWRtaW4=` = base64 of `admin`), but the template applies `b64enc` a second time:

  ```yaml
  admin-user: {{ .Values.grafana.adminUser | default "admin" | b64enc | quote }}
  ```

  `b64enc("YWRtaW4=")` yields `WVdSdGFXND0=`, which Kubernetes decodes to the literal string `YWRtaW4=`, not `admin`. The `default "admin"` fallback is never triggered because the value is non-empty.
- **Impact:** A Helm-deployed Grafana cannot be logged into with the documented default (`admin`/`admin`). This breaks the credential-externalization objective for the Kubernetes path and contradicts `monitoring/README.md`. Additionally, `test_grafana_secret_contains_admin_credentials` (which asserts the decoded value equals `admin`) will fail in CI.
- **Recommendation:** Align with the existing `templates/secrets/*.yaml` convention, which stores base64 values and only `quote`s them. Change the template to:

  ```yaml
  admin-user: {{ .Values.grafana.adminUser | default "admin" | quote }}
  admin-password: {{ .Values.grafana.adminPassword | default "admin" | quote }}
  ```

  and keep the base64 values in `values.yaml` (this also keeps `test_no_plaintext_passwords_in_values` passing). Update the README so the documented `--set grafana.adminUser=<base64>` semantics match.

### F2 — High — Helm provisioning ConfigMap is mounted at the wrong path; Prometheus datasource is never loaded

- **Files:** `helm/ai-data-platform/templates/monitoring/grafana-deployment.yaml` (volumeMount/volumes); `helm/ai-data-platform/templates/monitoring/grafana-configmap.yaml`.
- **Problem:** The ConfigMap defines flat keys `datasources.yml` and `dashboards.yml`, and the Deployment mounts the whole ConfigMap at `/etc/grafana/provisioning`. This produces files `/etc/grafana/provisioning/datasources.yml` and `/etc/grafana/provisioning/dashboards.yml`. Grafana reads provisioning from *subdirectories*: `/etc/grafana/provisioning/datasources/*.yml` and `/etc/grafana/provisioning/dashboards/*.yml`. Files at the top level are not scanned.
- **Impact:** A Helm-deployed Grafana starts with no Prometheus datasource and no dashboard provider, so the core objective "connect it reproducibly to Prometheus" is not met for the Kubernetes path. The Compose path is correct (host dirs mounted into the subdirectories), so the defect is specific to Helm and is not caught by any test.
- **Recommendation:** Mount each ConfigMap key into the correct subdirectory, e.g. via `subPath`:

  ```yaml
  volumeMounts:
    - name: datasources
      mountPath: /etc/grafana/provisioning/datasources/datasources.yml
      subPath: datasources.yml
    - name: dashboards
      mountPath: /etc/grafana/provisioning/dashboards/dashboards.yml
      subPath: dashboards.yml
  ```

  (or split into two ConfigMaps mounted at the `datasources/` and `dashboards/` subdirectories).

### F3 — Moderate — Docker Compose Grafana healthcheck uses `curl`, likely absent from the Grafana image

- **File:** `docker-compose.yml` (`grafana.healthcheck`).
- **Problem:** The healthcheck is `curl --fail http://localhost:3000/api/health`. The `grafana/grafana:11.4.0` image is Alpine-based and ships busybox `wget`, not `curl`. The sibling `prometheus` service in the same file (TASK-084, same author) correctly uses `wget --spider -q …`.
- **Impact:** If `curl` is absent, the healthcheck fails with exit 127 and Grafana is reported unhealthy (the container itself still runs). Any future `depends_on: grafana: condition: service_healthy` chain would also break.
- **Recommendation:** Switch to `wget --spider -q http://localhost:3000/api/health` to match the Prometheus service and the image's available tooling, or explicitly verify `curl` is present in the pinned image tag.

## 6. Non-Defect Observations

- Grafana data in Helm uses `emptyDir` (ephemeral). This matches the Prometheus precedent and is acceptable for local development; a PVC would be a reasonable future hardening step, not required by TASK-085.
- The Helm `dashboards.yml` provider points at `/var/lib/grafana/dashboards`, while the Compose `dashboard.yml` points at `/etc/grafana/provisioning/dashboards`. Harmless now (no dashboards exist yet), but TASK-086 should reconcile these two paths.
- Grafana is exposed as a `ClusterIP` Service with no Ingress; local access is via `kubectl port-forward`. This is consistent with the local-first scope and is documented.
- `grafana.adminUser`/`adminPassword` use camelCase, which is consistent with the existing `secrets.bestbuyApiKey` convention (not a defect).

## 7. Verdict

**`CHANGES REQUIRED`**

Blocking findings:

- **F1 (High):** Helm Secret double-encodes credentials — the documented `admin`/`admin` default does not work in the Helm path, and the new CI test `test_grafana_secret_contains_admin_credentials` fails against the committed values.
- **F2 (High):** Helm provisioning ConfigMap is mounted at the wrong path — the Prometheus datasource is never auto-provisioned, defeating the task's core "connect reproducibly to Prometheus" objective for the Kubernetes deployment path.

The Docker Compose path is correct and well-tested; the defect is concentrated in the Helm rendering/mounting, which was not exercised locally because the Helm binary is absent. Fix F1 and F2 (and ideally F3), then rerun the Helm rendering tests with `helm` installed (or in CI) before acceptance.
