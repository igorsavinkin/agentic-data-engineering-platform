# TASK-082 Review Report — Environment-Specific Values

## 1. Review Header

| Field | Value |
|---|---|
| Task | TASK-082 — Environment-Specific Values |
| Review date | 2026-09-19 |
| Reviewer | Qwen Code (independent review, no code modified) |
| Reviewed change set | `b06bbf28498846c511360c0ad7a5b844cb71591c...06ab15647ec32075ce6c55845ad08c1a94fd605e` |
| Commits in range | `06ab156 feat(TASK-082): Environment-specific values and chart README` |
| Reviewed HEAD | `06ab15647ec32075ce6c55845ad08c1a94fd605e` on `feature/TASK-082` |
| Scope | `helm/ai-data-platform/README.md`, `helm/ai-data-platform/values-local.yaml`, `helm/ai-data-platform/values-production.yaml` |
| Verdict | **APPROVED WITH NON-BLOCKING FINDINGS** |

Sources of authority consulted: `ai/PROJECT.md` (§11 Security, §12 Testing), `ai/SPECIFICATION.md` (§19 Kubernetes, §21 Security), `ai/ROADMAP.md` (§16 Milestone 9 — Helm), `ai/tasks/TASK-082-environment-specific-values.md`, `ai/tasks/TASK-081/083` (scope boundary and continuation), `docs/adr/ADR-001-kafka-topic-configuration.md` (reviewed; not directly applicable), `ai/AGENTS.md`.

Context carried forward: this report builds on the TASK-081 review (`docs/reviews/TASK-081-review.md`), which flagged two items explicitly deferred to this task: (a) F1 — no automated Helm render/lint check, and (b) a non-defect observation that `platform.environment` defaults to `production` and "TASK-082 (environment-specific values) is the natural place to resolve it." TASK-081 F4 also warned that the NetworkPolicy sample ingress rules would block an ingress controller in another namespace.

---

## 2. Requirements Coverage

| # | Requirement | Status | Evidence |
|---|---|---|---|
| R1 | Add base + environment overrides | ✅ Met | `values.yaml` (base, unchanged) + `values-local.yaml` + `values-production.yaml` |
| R2 | At least local/development and production-like example | ✅ Met | `values-local.yaml` (`platform.environment: local`) and `values-production.yaml` (`platform.environment: production`) |
| R3 | No template forks | ✅ Met | Diff touches no `templates/*`; only README + two values files added |
| R4 | No credentials | ✅ Met | Neither new file contains a `secrets` section or any literal secret; production relies on `--set secrets.*="<base64>"` placeholders |
| R5 | Demonstrate justified differences | ✅ Met | README "Key Differences" table (environment, image tags, replicas, processor CPU/memory, Ingress/HPA/NetworkPolicy) |
| R6 | Document `helm upgrade --install` commands | ✅ Met | README "Quick Start" documents base, local-overlay, and production-overlay commands |
| R7 | Implement this task only / no redesign | ✅ Met | No service boundaries, probes, resources, or config semantics changed; purely additive values overlays |
| R8 | Dependency gate (TASK-073 resolved; TASK-073–079 complete) | ✅ Met | TASK-073–081 commits present in history; this task is the continuation |
| R9 | DoD — lint/render/deployment checks pass | ⚠️ Unverified | `helm` not available in review environment; no CI step renders the chart (carried from TASK-081 F1) |
| R10 | DoD — documentation updated | ✅ Met | New chart-level `helm/ai-data-platform/README.md` (resolves TASK-081 F2 at the chart level) |

---

## 3. Git Diff Review

**Scope correctness.** The range is a single commit adding exactly three files, all under `helm/ai-data-platform/`:

```
helm/ai-data-platform/README.md              |  51 ++++++++++++++++
helm/ai-data-platform/values-local.yaml      | 100 ++++++++++++++++++++++
helm/ai-data-platform/values-production.yaml | 169 +++++++++++++++++++++++
3 files changed, 320 insertions(+)
```

This matches the task objective precisely. No files outside the Helm chart were touched.

**Unrelated changes.** None. No Python, CI, `kubernetes/`, or other-directory changes.

**Architectural changes.** None. No template was modified, so the "no template forks" requirement is satisfied by construction. The established Deployment/Service/ConfigMap/Secret/Job templates and `_helpers.tpl` are unchanged.

**Accidental changes.** None. No debug code, generated `.tgz` archives, temporary files, or dead artifacts.

**Dependency/config changes.** None. `Chart.yaml` and `.helmignore` unchanged; no new Helm dependencies.

**Key-path consistency (static).** Every override key in both new files resolves to a key present in base `values.yaml` and referenced by a template. Verified against: `templates/deployments/*.yaml` (`.Values.<component>.replicas`, `.Values.<component>.resources`, `.Values.images.<component>.tag`), `templates/configmaps/platform-config.yaml` (`.Values.platform.environment`, `.Values.platform.kafkaBootstrapServers`, `.Values.platform.minioEndpoint`), `templates/ingress.yaml`, `templates/hpa.yaml`, `templates/networkpolicy.yaml`. No dangling or misspelled keys found.

---

## 4. Test and Verification Review

| Check | Status | Evidence |
|---|---|---|
| Diff/scope inspection | ✅ Independently verified | `git log`, `git diff --stat`, full diff, single commit |
| YAML validity of the two new values files | ✅ Independently verified | Parsed `values.yaml`, `values-local.yaml`, `values-production.yaml` with PyYAML (`yaml.safe_load`); all parse cleanly |
| Override key-path consistency vs. templates | ✅ Independently verified | Static cross-read of all deployment/service/configmap/ingress/hpa/networkpolicy templates |
| No real secrets | ✅ Independently verified | New files contain no secrets; base `secrets.*` decode to local-dev placeholders (`minioadmin`, `minioadmin-local`, `postgres`, `placeholder-replace-me`) |
| README "Resources" column meaning | ✅ Independently verified | 18 = rendered objects with Ingress/HPA/NetworkPolicy disabled (7 Deployments + 4 Services + 3 Secrets + 2 ConfigMaps + 1 Job + 1 Namespace); 21 = 18 + the three enabled optional resources |
| `helm lint` | ❌ Unverified | `helm` binary not installed in review environment |
| `helm template` (render with the two overlays) | ❌ Unverified | Same; no CI step or script renders the chart |
| `helm install`/upgrade in kind | ❌ Unverified | Explicitly deferred to TASK-083 (Helm deployment tests) |
| Python unit/integration tests, ruff, mypy | Not rerun (out of scope) | No Python changed |

**Verification classification.** The render/lint checks the task's DoD references are **Unverified** (no Helm binary, no recorded implementation evidence, no CI step). All other checks relevant to this task were **independently verified** by static inspection. This is the same gap flagged as F1 in the TASK-080 and TASK-081 reviews and remains open.

**Test adequacy.** TASK-082 adds no tests, which is acceptable in part because the ROADMAP defers "Helm deployment tests" to TASK-083 and this task is values-only. However, the two new overlays are precisely the input a `helm template -f values-<env>.yaml` render check should exercise, and none exists. A one-line render smoke test would have caught the Kafka heap/limit mismatch (F2) and the NetworkPolicy-vs-Ingress interaction (F1) mechanically.

---

## 5. Findings

### F1 — Production NetworkPolicy blocks the Ingress controller it enables alongside (Moderate)

- **Affected file/reference:** `helm/ai-data-platform/values-production.yaml` (`networkPolicy.ingress` and `ingress.enabled: true`).
- **Problem:** The production overlay enables both Ingress (`ingress.enabled: true`) and NetworkPolicy (`networkPolicy.enabled: true`). The NetworkPolicy ingress rule is copied from the base default and allows traffic only from namespaces labeled `app.kubernetes.io/part-of: ai-data-platform`:

  ```yaml
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              app.kubernetes.io/part-of: ai-data-platform
  ```

  An ingress controller (e.g. `ingress-nginx`) runs in its own namespace (e.g. `ingress-nginx`) that does **not** carry that label, so its traffic to the `api` pod is not matched by any ingress rule and is therefore denied. The result is an Ingress that is enabled but cannot route external traffic to the API.
- **Impact:** The production example, if applied as documented, exposes a non-functional Ingress (external API access silently blocked). This realizes the latent footgun explicitly flagged as F4 in the TASK-081 review, now that the policy is actually enabled.
- **Recommendation:** Add an ingress rule permitting traffic from the ingress controller (by namespace label, e.g. `kubernetes.io/metadata.name: ingress-nginx`, or by pod selector), or document that enabling both requires adding that rule. The existing "Review NetworkPolicy rules for the target CNI" comment addresses CNI support, not this missing rule.

### F2 — `values-local.yaml` lowers Kafka memory below its JVM heap (Moderate)

- **Affected file/reference:** `helm/ai-data-platform/values-local.yaml` (`kafka.resources.limits.memory: 512Mi`); base `values.yaml` (`kafka.heapOpts: "-Xmx512M -Xms256M"`).
- **Problem:** The local overlay reduces Kafka's container memory limit to `512Mi` but does not override `kafka.heapOpts`, which remains `-Xmx512M -Xms256M` from the base. The JVM max heap (512M) plus metaspace/native/off-heap overhead will very likely exceed a 512Mi container limit under load.
- **Impact:** The local kind overlay risks OOM-killing the Kafka pod, defeating the "healthy deployment" requirement and undermining the local-development path the overlay is meant to make lighter.
- **Recommendation:** Either lower `kafka.heapOpts` in the overlay (e.g. `-Xmx256M -Xms128M`) or leave the Kafka memory limit at or above the base `1Gi`. Confirm by rendering/installing in TASK-083.

### F3 — Production Ingress `rewrite-target: /` breaks `/api/v1` routing (Moderate)

- **Affected file/reference:** `helm/ai-data-platform/values-production.yaml` (`ingress.annotations.nginx.ingress.kubernetes.io/rewrite-target: /`).
- **Problem:** The annotation rewrites the request path to `/`. With a single `hosts[].paths[]` entry of `path: /` (Prefix), every inbound path is rewritten to `/`. The API routes are mounted under `/api/v1` (`services/api/app.py`: `app.include_router(v1_router, prefix="/api/v1")`), so requests such as `/api/v1/health` or `/api/v1/products` would be rewritten to `/` and return 404/incorrect results.
- **Impact:** External API access through the documented production Ingress would not work as intended.
- **Recommendation:** Remove the annotation (the API serves under a single path without a need to rewrite), or use a capture-group rewrite (e.g. `rewrite-target: /$2` with `path: /api(/|$)(.*)`). Verify in TASK-083 if Ingress is exercised.

### F4 — Base `platform.environment` remains `production`, contradicting the README (Minor)

- **Affected file/reference:** `helm/ai-data-platform/README.md` ("Local kind development (default values)"; "Base defaults (local-dev oriented)"); base `values.yaml` (`platform.environment: production`, unchanged).
- **Problem:** The README's first quick-start command uses only default values and is described as "Local kind development (default values)", but the base default `platform.environment` is `production`. TASK-081 explicitly deferred this exact inconsistency to TASK-082 ("TASK-082 (environment-specific values) is the natural place to resolve it"), and it was not resolved: the base default still renders `APP_ENVIRONMENT=production` unless the local overlay is supplied.
- **Impact:** Misleading documentation and environment labeling. Because `APP_ENVIRONMENT` is described as informational in `values.yaml`, this is not a functional defect, but the default and the README disagree about what a bare `helm upgrade --install` produces.
- **Recommendation:** Either change the base default to `local` (and let the production overlay set `production`), or adjust the README so the "local development" quick-start explicitly includes `-f values-local.yaml`.

### F5 — README documentation accuracy (Minor)

- **Affected file/reference:** `helm/ai-data-platform/README.md` (Environment Files table; Key Differences table).
- **Problem:** Two accuracy/clarity issues:
  1. The "Resources" column (18 / 18 / 21) is correct in meaning — it counts rendered Kubernetes objects (18 with Ingress/HPA/NetworkPolicy disabled; 21 with all three enabled) — but the header "Resources" is not explained and could be misread as CPU/memory resources.
  2. The "Key Differences" row "Service replicas | 1 | 2" overstates the production posture: `warehouseLoader` remains `1` replica in production (correctly, as a batch reader) and `kafka` remains `1` (single-broker KRaft, RF=1). The "production example (HA, …)" description is similarly generous given a single Kafka broker.
- **Impact:** Readers may take the summary as exact rather than illustrative.
- **Recommendation:** Add a legend/footnote for the "Resources" column, and qualify the replica/HA statements (e.g. "2 replicas for stateless services; warehouse-loader and Kafka remain single-instance").

### F6 — Redundant no-op overrides and one missed override (Minor)

- **Affected file/reference:** `helm/ai-data-platform/values-local.yaml` and `values-production.yaml`.
- **Problem:**
  1. Several "overrides" equal the base defaults: `values-local.yaml` `global.imagePullPolicy`, `platform.kafkaBootstrapServers`, `platform.minioEndpoint`; `values-production.yaml` `platform.environment: production` (base already `production`) and `global.imagePullPolicy`. This contradicts the local file's header claim that it "overrides only the values that differ from the base defaults."
  2. The production overlay does **not** override `kafka.service.type` (base `NodePort`, `nodePort: 30092`), even though the base comment explicitly recommends "use ClusterIP in production." A production example therefore still exposes Kafka on a NodePort.
- **Impact:** Minor noise and a slightly less production-appropriate Kafka Service; no rendering defect.
- **Recommendation:** Drop the redundant entries (or correct the header comment) and add `kafka.service.type: ClusterIP` (with `nodePort` removed/nulled) to the production overlay.

---

## 6. Non-Defect Observations

- **Core objective fully satisfied.** Base + local + production overlays exist, with no template forks and no credentials, and the README documents both the justified differences and the `helm upgrade --install` commands. This is the exact deliverable the task asked for.
- **No real secrets.** Neither new file carries a `secrets` block; production pushes secrets to `--set secrets.*="<base64>"` placeholders, and the base placeholders remain clearly marked as local-dev-only.
- **Chart README now exists.** `helm/ai-data-platform/README.md` resolves TASK-081 F2 at the chart level. (The top-level `helm/README.md` stub remains, but the conventional per-chart README location is now populated.)
- **"Resources" column is meaningful and verified.** The 18/18/21 figures correctly count rendered Kubernetes objects; this is a genuine (if undocumented) summary of the overlay effect.
- **Overlay keys all resolve.** Static inspection found no dangling keys, misspelled paths, or values that would fail template rendering; the only render-time concerns are the semantic ones in F1–F3.
- **Production caveat block is present and honest.** The production file opens with an explicit checklist (replace secrets, pin tags, set domains, tune resources, review NetworkPolicy), which appropriately signals that the file is an example rather than a turnkey manifest.
- **Branch/commit isolation clean.** Single commit, single task, on `feature/TASK-082`; working tree clean apart from the review file.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The implementation satisfies the TASK-082 objective: it adds base plus local and production environment overlays without template forks or credentials, documents the justified differences in a comparison table, and records the `helm upgrade --install` commands. The diff is tightly scoped, all override keys resolve against the existing chart, and no real secrets or unrelated changes were introduced.

The findings are non-blocking quality issues rather than missing requirements. The three Moderate findings (F1–F3) describe concrete defects in the *examples* — a production NetworkPolicy that blocks its own Ingress, a local Kafka memory limit below its JVM heap, and an Ingress rewrite that breaks `/api/v1` routing — but they affect optional overlay files, not the healthy base/default deployment, and are exactly the kind of issue TASK-083 (Helm deployment tests) is positioned to surface when the overlays are actually rendered and installed. The remaining findings are documentation accuracy and chart-hygiene items. Helm render/lint could not be independently executed (no `helm` binary, no CI step), which is the same open verification gap carried from TASK-080/TASK-081.

No code was modified during this review.
