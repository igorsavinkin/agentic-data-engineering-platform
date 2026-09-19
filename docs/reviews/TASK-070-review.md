# TASK-070 Review — kind Cluster and Namespaces

## 1. Review Header

- **Task ID:** TASK-070 — kind Cluster and Namespaces
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set (three-dot diff):** `3f91502ee7c84d0b4e0391bf4f071b0116efeb49...2c23f98c49de9ad17b14f0fdcc5caf984ee75da6`
- **Reviewed HEAD:** `2c23f98c49de9ad17b14f0fdcc5caf984ee75da6` (`2c23f98`) on `feature/TASK-070`
- **Commits in range (2-dot `3f91502..2c23f98` = 2 commits):**
  - `fe1ac9a623699afe6fc18b18a2f4fab9590b9a60` — `feat(TASK-070): kind cluster config and platform namespace`
  - `2c23f98c49de9ad17b14f0fdcc5caf984ee75da6` — `fix(TASK-070): add pyyaml to requirements-dev.txt`
- **Scope:** 7 files changed, 429 insertions, 1 deletion.
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

> **Note on the base commit.** The base `3f91502` ("Merge pull request #82 from igorsavinkin/feature/TASK-069") is the direct parent of `fe1ac9a`, so the history is linear and the three-dot diff equals the two-dot diff. Both show only the seven task-relevant files; there is no cross-task contamination. Commit `2c23f98` is a follow-up that declares the `PyYAML` test dependency identified as a blocking issue against the earlier `fe1ac9a` revision.

---

## 2. Requirements Coverage

Task objective: create a reproducible kind cluster config and platform namespace(s), and document create/delete/recreate, kubectl verification, and local-image loading — without deploying services.

| Requirement | Status | Evidence |
|---|---|---|
| Reproducible kind cluster config | ✅ Met | `kubernetes/kind/kind-config.yaml` (kind.x-k8s.io/v1alpha4 `Cluster`, single control-plane node, pinned `kindest/node:v1.31.0`, four `extraPortMappings`). |
| Platform namespace(s) | ✅ Met | `kubernetes/namespaces/platform-namespace.yaml` (`Namespace` `ai-data-platform` with `app.kubernetes.io/*` and pod-security labels). |
| Document create/delete/recreate | ✅ Met | `kubernetes/README.md` (§ Quick Start) and `scripts/kind-cluster.sh` (`create`/`delete`/`recreate`). |
| Document kubectl verification | ✅ Met | `kubernetes/README.md` (§ Verify, § Manual Commands, § Troubleshooting) and `cmd_verify` (cluster-info, nodes, namespace, events). |
| Document local-image loading | ✅ Met | `kubernetes/README.md` (§ Load local Docker images) and `cmd_load` (`kind load docker-image`). |
| Do not deploy services yet | ✅ Met | No Deployment/Service/Pod manifests; README § "What TASK-070 Does NOT Do" is explicit. |
| Declarative manifests, consistent labels | ✅ Met | YAML manifests with consistent `app.kubernetes.io/part-of` label; see Finding F2 for a label-value nuance. |
| Never commit real secrets | ✅ Met | No secrets; MinIO/Kafka values not embedded (port mappings only). |
| Validate manifests/tests | ✅ Met | `tests/test_kubernetes_manifests.py` (8 hermetic tests); test dependency now declared (see F1, resolved). |
| Remain compatible with later Helm (without implementing Helm) | ⚠️ Partial | No Helm implemented; but the `app.kubernetes.io/managed-by: kubectl` label will need to change to `Helm` under TASK-080 (F2). |
| Acceptance behavior demonstrated (Definition of Done) | ⚠️ Not evidenced | No evidence in the commit of a real `create`/`verify`/`delete` run; tests are hermetic structure checks (F3). |

---

## 3. Git Diff Review

- **Branch / isolation:** On `feature/TASK-070`; working tree clean except the untracked review report; two linear commits. No cross-task contamination.
- **Files changed (7):**
  - `kubernetes/README.md` (expanded, +129)
  - `kubernetes/kind/kind-config.yaml` (new, +41)
  - `kubernetes/namespaces/platform-namespace.yaml` (new, +22)
  - `pyproject.toml` (+1/-1, mypy `ignore_missing_imports` for `yaml`)
  - `requirements-dev.txt` (+1, `pyyaml>=6.0`)
  - `scripts/kind-cluster.sh` (new, +166)
  - `tests/test_kubernetes_manifests.py` (new, +69)
- **Out-of-scope / unrelated changes:** None. All seven files are directly attributable to TASK-070 (config, namespace, lifecycle script, docs, a manifest-validation test, plus the minimal mypy config and test dependency needed for that test).
- **Architectural changes:** None. No service boundaries, event contracts, or data-flow changes. `kubernetes/` content is additive and consistent with SPECIFICATION.md §19 and ROADMAP.md Milestone 8.
- **Accidental / debug / secrets / generated artifacts:** None found. No `.env`, credentials, cache files, or debugging code.
- **New dependencies:** `PyYAML` (`pyyaml>=6.0`) added to `requirements-dev.txt` — test-only, and now declared. See F1 (resolved).
- **Test weakening:** No existing tests modified, removed, or weakened. The new test file is additive.

---

## 4. Test and Verification Review

### Tests examined

`tests/test_kubernetes_manifests.py` — 8 tests across two classes:

- `TestKindConfig` (4): file exists; `kind`/`apiVersion` fields; control-plane role + `extraPortMappings`; per-mapping `containerPort`/`hostPort`/`protocol`.
- `TestNamespaceManifest` (4): file exists; `apiVersion`/`kind`; name `ai-data-platform`; `app.kubernetes.io/part-of` label.

The tests are hermetic YAML-structure checks (they parse the two manifests with `yaml.safe_load` and assert a handful of fields). They do **not** invoke `kind` or `kubectl`, and they do **not** exercise `scripts/kind-cluster.sh`.

### Verification status

| Check | Result | Classification |
|---|---|---|
| `python -m pytest tests/test_kubernetes_manifests.py -v` | 8 passed | **Independently verified** |
| `python -m ruff check tests/test_kubernetes_manifests.py` | All checks passed | **Independently verified** |
| `python -m ruff format --check tests/test_kubernetes_manifests.py` | 1 file already formatted | **Independently verified** |
| `python -m mypy tests/test_kubernetes_manifests.py` | Success: no issues found | **Independently verified** |
| `bash -n scripts/kind-cluster.sh` | Syntax OK | **Independently verified** |
| `python -c "import yaml; print(yaml.__version__)"` | `pyyaml 6.0.3` importable | **Independently verified** |
| `python -m pytest -m integration` | Not run | **Not run** — live-cluster integration is scoped to TASK-079; the task is structural and the default pytest run excludes integration tests. |
| Live `create`/`verify`/`delete` against a real kind cluster | Not performed | **Unverified** — `kind` is not installed in this environment (`command -v kind` empty; `kubectl` v1.34.1 and `docker` 29.2.1 are present), and the commit contains no recorded evidence of a successful run. |

Note: a `kubectl apply --dry-run=client` validation of the namespace manifest was attempted but requires a live API server (no cluster is running and `kind` is absent), so it could not be used for independent confirmation. YAML well-formedness was instead confirmed via the passing `yaml.safe_load` tests.

### Test adequacy notes

- The structural tests are a reasonable, cheap, hermetic guard for manifest shape and are consistent with the repository's test layout (`tests/*.py` at top level). They match the project convention of not requiring Docker for the default `pytest` run.
- A real behavioral test (create cluster → apply namespace → verify → delete) is not present. Given ROADMAP Milestone 8 explicitly defers "Kubernetes integration tests" to TASK-079, this omission is defensible — but see Finding F3 regarding the "acceptance behavior demonstrated" wording.
- The tests cover only two of the three deliverables directly; the lifecycle shell script is not tested at all (Finding F4).

---

## 5. Findings

### F1 — Resolved: `PyYAML` was an undeclared test dependency (fixed by `2c23f98`)

- **Severity:** High at the time of `fe1ac9a`; **now resolved**.
- **File / line:** `tests/test_kubernetes_manifests.py` line 19 (`import yaml`); `requirements-dev.txt`.
- **Problem:** The test imports `yaml` (PyYAML), and PyYAML is not part of the declared runtime dependencies (`requirements.txt` contains no `yaml`; none of its packages transitively depend on PyYAML). Because CI (`ci.yml`) installs only `requirements-dev.txt`, a clean runner would have failed the `pytest` step with `ModuleNotFoundError: No module named 'yaml'`.
- **Resolution:** Commit `2c23f98` adds `pyyaml>=6.0` to `requirements-dev.txt` (test-only, correct placement). Independently confirmed: `requirements-dev.txt` line 8 is `pyyaml>=6.0`, and `python -c "import yaml"` reports `6.0.3`. The companion `pyproject.toml` change (`ignore_missing_imports = true` for `yaml`) remains correct because PyYAML ships no type stubs.
- **Impact after fix:** None. CI installs the dependency; `pytest`, `ruff`, and `mypy` all pass on the test file (independently verified).

### F2 — Minor: `app.kubernetes.io/managed-by: kubectl` is a non-standard label value and will drift under Helm

- **Severity:** Minor.
- **File / line:** `kubernetes/namespaces/platform-namespace.yaml` (~line 19), label `app.kubernetes.io/managed-by: kubectl`.
- **Problem:** The `app.kubernetes.io/managed-by` label conventionally identifies the *tool that manages the resource* (e.g. `Helm`, `kustomize`). `kubectl` is not a recognized value. The task also requires staying "compatible with later Helm work without implementing Helm early"; when TASK-080+ takes over packaging, this label must change to `Helm` (or be dropped).
- **Impact:** Cosmetic/non-functional now, but it sets a value that is semantically non-standard and is guaranteed to drift under the upcoming Helm milestone.
- **Recommendation:** Drop `app.kubernetes.io/managed-by` for now (leave it to Helm), or document why `kubectl` is used. Keep `app.kubernetes.io/part-of` and the pod-security labels.

### F3 — Moderate: "Acceptance behavior is demonstrated" is not evidenced; no live cluster verification

- **Severity:** Moderate (non-blocking, given the roadmap).
- **File / line:** task Definition of Done (`ai/tasks/TASK-070-kind-cluster-and-namespaces.md`); the seven changed files contain no recorded run evidence.
- **Problem:** The task's Definition of Done includes "Acceptance behavior is demonstrated", and its "Human Kubernetes Practice" section asks for direct use of `kubectl get/apply/delete` and `kind`. The commit contains only manifests, a script, documentation, and structural tests; there is no evidence (test output, a documented manual run, or a `docs/` note) that `create`/`verify`/`delete`/`recreate`/`load` were ever exercised against a real kind cluster. The tests never invoke `kind` or `kubectl`.
- **Impact:** The config and script are validated only structurally. A defect that only manifests at runtime — e.g. an invalid `extraPortMappings` value, a broken `kind` flag, or a NodePort/service mismatch (the config assumes TASK-077/078/079 will expose NodePorts `30092`/`30090`/`30091`/`30080`) — would not be caught. The reviewer also could not independently verify because `kind` is not installed in this environment.
- **Recommendation:** Either record a short manual demonstration (create → verify → delete) in the task or README, or explicitly defer live-cluster verification to TASK-079 ("Kubernetes integration tests") with a note in the review/FOLLOWUPS. At minimum, document that the port-mapping assumptions (`hostPort 9092/9000/9001/8000` → NodePort `30092/30090/30091/30080`) are intentional and must be honored by TASK-077/078/079. Non-blocking because ROADMAP Milestone 8 defers Kubernetes integration tests to TASK-079 and this task is purely declarative.

### F4 — Minor: the lifecycle shell script has no automated test or lint coverage

- **Severity:** Minor.
- **File / line:** `scripts/kind-cluster.sh` (entire file, 166 lines).
- **Problem:** The script is the primary automation for create/delete/recreate/verify/load, but it is not exercised by any test and not covered by `shellcheck` or CI. The reviewer only ran `bash -n` (syntax) manually.
- **Impact:** A typo or logic error in the script (e.g. a wrong `kind`/`kubectl` flag, or the `grep -q "^${CLUSTER_NAME}$"` match breaking on a name with regex metacharacters) would not be caught by CI.
- **Recommendation:** At minimum add a `bash -n` (and ideally `shellcheck`) check to CI; a smoke test of `cmd_verify`/`cmd_load`'s "cluster does not exist" paths could run without a live cluster. Non-blocking.

---

## 6. Non-Defect Observations

- **Port mappings are internally consistent.** `kind-config.yaml` maps host `9092`/`9000`/`9001`/`8000` to NodePorts `30092`/`30090`/`30091`/`30080`, matching `docker-compose.yml` (Kafka `${KAFKA_HOST_PORT:-9092}`, MinIO `9000`/`9001`) and the API default `port: int = 8000` / `APP_API_PORT` default `8000` in `services/api/config.py`. All chosen NodePorts are within the valid `30000–32767` range. Minor nuance: `docker-compose.yml` does not yet deploy FastAPI, so "mirroring the Docker Compose layout" applies strictly to Kafka/MinIO; the `8000` mapping is forward-looking (API deployment is TASK-076) and consistent with the API's configured default port.
- **PSA labels are reasonable.** `pod-security.kubernetes.io/enforce: baseline` with `warn: restricted` is a sensible, conservative posture for a local dev namespace.
- **`ingress-ready=true` node label is harmless but unused.** It is standard kind boilerplate and matches kind's ingress docs; no ingress controller is deployed (and none is claimed by TASK-070). It can stay for TASK-080+.
- **Documentation is thorough and accurate.** `kubernetes/README.md` covers directory structure, prerequisites, create/verify/delete/recreate/load, manual `kind`/`kubectl` commands, the namespace, port mappings, an explicit "what this does not do" list, and troubleshooting. This aligns well with the task's documentation requirement.
- **Script quality is good.** `set -euo pipefail`, prerequisite checks, an overridable `KIND_CLUSTER_NAME`, and idempotent create/delete guards. The fixed namespace name (`ai-data-platform`) is consistent across the script, manifest, and README (the namespace name is intentionally not parameterized alongside `KIND_CLUSTER_NAME`, which is correct because the manifest fixes it).
- **Mypy config change is correctly additive.** Adding `yaml` to the existing `ignore_missing_imports` override is required (PyYAML has no stubs) and cannot regress other modules.
- **No secrets or sensitive values.** Only port mappings and non-secret labels are present; the README and manifests do not embed credentials.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The change is correctly isolated to TASK-070, additive, and architecturally neutral. The kind config, namespace manifest, lifecycle script, and documentation all satisfy the task's explicit deliverables. The follow-up commit `2c23f98` resolves the only blocking issue previously identified against `fe1ac9a` (undeclared `PyYAML` test dependency); `pyyaml>=6.0` is now declared in `requirements-dev.txt`, so the authoritative CI gate (`pip install -r requirements-dev.txt` → `pytest`) will succeed on a clean runner.

Independently verified by the reviewer:

- `pytest tests/test_kubernetes_manifests.py` → **8 passed**
- `ruff check` and `ruff format --check` on the new test file → **passed**
- `mypy` on the new test file → **no issues**
- `bash -n scripts/kind-cluster.sh` → **syntax OK**
- `import yaml` → **6.0.3 present**

Remaining findings are non-blocking:

- **F2 (Minor)** — `app.kubernetes.io/managed-by: kubectl` is non-standard and will drift under Helm (TASK-080+).
- **F3 (Moderate)** — no evidence of a real `create`/`verify`/`delete` demonstration (the "acceptance behavior demonstrated" clause); live-cluster verification is not covered by the tests and could not be independently confirmed (`kind` not installed). Defensible under the roadmap, which defers Kubernetes integration tests to TASK-079.
- **F4 (Minor)** — `scripts/kind-cluster.sh` has no automated test/lint coverage.

`python -m pytest -m integration` was not run and is not required for this structural task; live kind-cluster integration is scoped to TASK-079, and `kind` is not available in this environment.
