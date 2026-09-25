# TASK-DOCS-PLATFORM-INVENTORY-M13 Review — Platform Architecture Inventory after Milestone 13

## 1. Review Header

- **Task ID:** TASK-DOCS-PLATFORM-INVENTORY-M13 — Platform Architecture Inventory after Milestone 13
- **Review date:** 2026-09-25
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `033368089dba031767f29db5578863995f435806...5be6530d666628899cdd2c49f8e0c7e056f1b505`
- **Reviewed commit:** `5be6530d666628899cdd2c49f8e0c7e056f1b505` — `docs(TASK-DOCS-PLATFORM-INVENTORY-M13): evidence-based platform inventory after M13`
- **Reviewed HEAD:** `5be6530d666628899cdd2c49f8e0c7e056f1b505` on `feature/TASK-DOCS-PLATFORM-INVENTORY-M13`
- **Scope:** Documentation/architecture reconciliation. No production behavior is expected to change.
- **Verdict:** CHANGES REQUIRED

---

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
|---|---|---|
| M0–M13 implementation status accurately inventoried | **Met** | `platform-inventory-m13.md` §1 status matrix with evidence column; M14/M15 marked Planned/target only |
| Actual runtime data flow documented | **Met** | §2 flow diagram + "Key Differences from Conceptual Architecture" |
| Service boundaries match implementation | **Met** | §3 service inventory (ingestion, processor, raw-writer, lake-writer, warehouse-loader, api, agent) |
| Kafka producers/consumers/topics inventoried | **Met** | §4 topics (5), consumer groups (3), producers (4), DLQ, lag |
| Bronze/Silver/Gold semantics match implementation | **Met** | §5; Gold correctly documented as PostgreSQL-only, no Gold Parquet bucket |
| Warehouse Loader and Airflow roles correctly represented | **Met** | §6.2 + §13 — Warehouse Loader reads Silver; Airflow is batch processor over PostgreSQL, not a pipeline stage |
| FastAPI serving architecture documented | **Met** | §7.1 endpoint table, readiness/health, DB dependency |
| LangGraph Agent boundaries documented | **Met** | §7.2 graph flow, intents, read-only guarantees, in-process deployment |
| Kubernetes/Helm topology documented | **Met** | §8 — namespace, 7 Deployments, 2 StatefulSets, 2 Jobs, ConfigMaps/Secrets, Helm layout |
| Observability stack documented | **Met** | §9 Prometheus/Grafana/OTel/Jaeger, metrics inventory, implemented-vs-deployed split |
| Reliability/failure mechanisms documented | **Met** | §10 retries, idempotency, replay, DLQ, no circuit breakers (honestly stated) |
| TASK-108–115 evidence summarized without invented measurements | **Met** | §11 exact benchmark figures preserved; target vs actual vs % separated |
| Verified E2E paths distinguished from implemented | **Met** | §12 matrix separates Implemented / Tested / E2E verified / Performance measured |
| Runtime-vs-conceptual architecture differences documented | **Met** | §13 (Silver→Warehouse Loader, Airflow role, Gold storage, Agent boundaries) |
| M14/M15 remain future work | **Met** | §14 both marked Not started / Planned |
| Architecture DOT/source diagrams updated | **Met** | `container-view.dot`, `data-flow.dot` updated to M0–M13 |
| SVG diagrams regenerated from sources | **NOT MET** | SVGs are stale (see Finding 3) |
| Documentation contains repository evidence references | **Met** | Evidence Index + per-section evidence paths |
| No production behavior changed | **Met** | Diff is docs-only (6 files, all under `docs/`) |
| Architecture findings/follow-ups documented | **Met** | §15 Confirmed / Known limitations / Investigation / M14 / M15 |
| Findings distinguish facts, limitations, hypotheses | **Met** | §15 classification is disciplined |
| No architectural finding silently fixed | **Met** (see Finding 1 caveat) | C1–C9 reported rather than fixed |
| Relevant documentation/structure checks pass | **Unverified** | No docs lint target identified; not run |

---

## 3. Git Diff Review

**Range contents:** A single commit (`5be6530`). Net diff touches six files, all under `docs/`:

| File | Change |
|---|---|
| `docs/architecture-communication/README.md` | +14/−12 (M0–M13 status, M14/M15 next steps) |
| `docs/architecture-communication/container-view.dot` | +143/−72 (major rework: observability/k8s/perf/future clusters) |
| `docs/architecture-communication/data-flow.dot` | +35/−25 (PostgreSQL 16, group labels, 4 DQ checks, serving solid lines) |
| `docs/architecture/platform-inventory-m13.md` | **+1272 (new file)** — the primary deliverable |
| `docs/performance/bottleneck-analysis.md` | +51/−47 (provenance wording changes — see Finding 1) |
| `docs/reviews/TASK-FIX-115-review.md` | **−125 (deleted)** — see Finding 2 |

- **Scope correctness:** The primary deliverable (`platform-inventory-m13.md`) and the two DOT/README diagram updates are in scope. **Two changes are out of scope:** the modification of `docs/performance/bottleneck-analysis.md` and the deletion of `docs/reviews/TASK-FIX-115-review.md`.
- **Unrelated changes:** Yes — the deletion of `docs/reviews/TASK-FIX-115-review.md` removes a review artifact belonging to a different task (TASK-FIX-115-EVIDENCE-PROVENANCE).
- **Architectural changes:** None in code/config. All changes are documentation.
- **Accidental changes:** None (no secrets, debug code, temp files, or generated artifacts introduced).
- **Dependency/configuration changes:** None.
- **Branch isolation:** Correct. The commit sits on `feature/TASK-DOCS-PLATFORM-INVENTORY-M13`; working tree clean. No other TASK-* changes are included in the range.

---

## 4. Test and Verification Review

- **Tests added/changed:** None. This is a documentation-only task; there is no deterministic code/test surface (consistent with the task's "Do not change production behavior" constraint).
- **Integration tests:** Not applicable. No Kafka/persistence/MinIO/infrastructure code paths changed.
- **Independent verification performed by reviewer (spot checks against repository evidence):**
  - **Kafka topics** — `scripts/manage_kafka_topics.py` confirms 5 topics with partitions `3/3/1/1/1`, replication `1`, retention `7/7/7/3/3` days, matching §4.1 exactly. **Verified.**
  - **Unused topics (C9)** — `grep` for `pipeline.events` / `data-quality.events` in `libs/` and `services/` returns no producer references. **Verified.**
  - **Gold bucket absence (C1/C3)** — `libs/common/minio_storage.py` configures only `bronze` and `silver` buckets. **Verified.**
  - **Warehouse Loader reads Silver** — `services/warehouse-loader/runner.py:67` calls `loader.load_from_lake(PartitionFilter(layer=LakeLayer.SILVER))`. **Verified.**
  - **DQ check count** — `airflow/dags/daily_data_quality_dag.py` defines 4 checks (`required_fields`, `price_validity`, `freshness`, `duplicates`). The DOT change from "5 checks" to "4 checks" is correct. **Verified.**
  - **K8s topology** — `kubernetes/deployments/` contains 7 deployments; Helm `deployments/` = 7, `statefulsets/` = 2, `jobs/` = 2. §8 "7 Deployments, 2 StatefulSets, 2 Jobs" is correct. **Verified.**
  - **Migrations** — `warehouse/migrations/versions/` contains 6 files (`001`–`006`), matching "8 tables, 6 Alembic migrations". **Verified.**
  - **API endpoints** — `services/api/routes/v1/` exposes 15 route handlers; inventory table lists 14 (omits `GET /api/v1/pipelines/{run_id}`). "13+ endpoints" is accurate. **Verified (with a minor omission, see Finding 5).**
  - **PostgreSQL version discrepancy** — `docker-compose.yml` uses `postgres:17`; `kubernetes/deployments/postgresql-statefulset.yaml` uses `postgres:16`. The docs now uniformly assert 16. **Verified discrepancy (see Finding 4).**
  - **SVG staleness** — committed SVGs still contain `M0–M6`, `PostgreSQL 17`, `5 checks`, and `Observability (M10)` markers. **Verified stale (see Finding 3).**
- **Verification status:** Load-bearing factual claims **independently verified**; no test suite was run (no code surface changed).

---

## 5. Findings

### Finding 1 — High — Out-of-scope modification to `docs/performance/bottleneck-analysis.md` reverses the completed TASK-FIX-115 provenance fix

- **Affected file/reference:** `docs/performance/bottleneck-analysis.md` (sections "Manual Runtime Observations (Uncommitted)", "Root Cause Status", "Hypothesis", "Recommendations").
- **Problem:** The commit changes the provenance of the Warehouse Loader OOM observations from "uncommitted manual observations" back to "the task specification reports …". Specifically:
  - Section heading changed from **"Manual Runtime Observations (Uncommitted)"** to **"Task Specification Runtime Observations"**.
  - "Manual runtime observations from a separate inspection … are not benchmark measurements" → "**The task specification reports** an OOMKilled termination with exit code 137 …".
  - "uncommitted manual observations, not benchmark measurements" → "**The task specification reports** OOMKilled as the termination reason with 134 restarts and ~55,361 files …".

  This re-introduces the exact task-specification attribution that the just-completed `TASK-FIX-115-EVIDENCE-PROVENANCE` (commits `edd7bb4`/`00065fa`, branch `feature/TASK-FIX-115-EVIDENCE-PROVENANCE`) deliberately removed. The deleted review (Finding 2) records that TASK-FIX-115's resolution was to "no longer attribute the values to any task specification." The task under review (`TASK-DOCS-PLATFORM-INVENTORY-M13`) neither requires nor authorizes editing `bottleneck-analysis.md` — its performance requirement (§11) is to *summarize* TASK-108–115 in the new inventory, which it correctly does in `platform-inventory-m13.md`.
- **Impact:** Re-opens the cross-document governance conflict that TASK-FIX-115 was created to resolve: `ai/tasks/TASK-115-document-bottlenecks.md:123` asserts "The OOM condition is confirmed runtime evidence," while the reviewed wording now attributes the same values back to that spec. A future reader cannot determine authoritative provenance, and the previously-completed fix is silently undone.
- **Recommendation:** Revert the `bottleneck-analysis.md` provenance wording to the post-TASK-FIX-115 state (unattributed "manual runtime observations"), or obtain an explicit human architectural decision per AGENTS.md §13 / AGENT_WORKFLOW.md §7 that the amended TASK-115 spec is authoritative. This is not a change the reviewer is authorized to make.

### Finding 2 — Moderate — Deletion of `docs/reviews/TASK-FIX-115-review.md` is out of scope and removes review provenance

- **Affected file/reference:** `docs/reviews/TASK-FIX-115-review.md` (deleted, −125 lines).
- **Problem:** The commit deletes the review artifact for a different task (TASK-FIX-115-EVIDENCE-PROVENANCE). This file documents the governance conflict that Finding 1 re-opens. The current task's scope does not include removing other tasks' review records.
- **Impact:** Loss of auditable review history; combined with Finding 1, it erases the record of exactly the provenance decision being reversed.
- **Recommendation:** Restore the file (or, if a deliberate governance decision was made to supersede it, record that decision in an ADR/task note — which has not been done here).

### Finding 3 — High — SVG diagrams were not regenerated; committed SVGs contradict the updated DOT sources

- **Affected file/reference:** `docs/architecture-communication/container-view.svg`, `docs/architecture-communication/data-flow.svg`.
- **Problem:** The DOT sources were substantially updated (container-view +143 lines, data-flow +35 lines), but the corresponding `.svg` files were not touched by this commit. Both SVGs still render stale content: `M0–M6`, `PostgreSQL 17`, `5 checks`, `Observability (M10)` (the latter two are now factually wrong per Findings 4 and the 4-check correction). The task's Acceptance Criteria explicitly require "SVG diagrams are regenerated from their sources," and the task's "Architecture Artifacts" section requires updating "rendered SVG versions." The README even notes "SVGs require regeneration after DOT source updates when Graphviz is available" — but regeneration was not performed.
- **Impact:** The primary visual architecture artifacts are inconsistent with the DOT sources and the rest of the documentation; a reader viewing the SVGs receives stale/wrong information.
- **Recommendation:** Regenerate both SVGs from their DOT sources (Graphviz `dot` is not currently available in the review environment — `dot -V` fails — so this must be done in an environment with Graphviz). Until then, the diagrams deliverable is incomplete.

### Finding 4 — Minor — PostgreSQL version is documented as 16 without noting the docker-compose (17) discrepancy

- **Affected file/reference:** `container-view.dot`, `data-flow.dot`, `platform-inventory-m13.md` §8.3 ("PostgreSQL 16").
- **Problem:** The docs were changed from "PostgreSQL 17" to "PostgreSQL 16" (matching `kubernetes/deployments/postgresql-statefulset.yaml:38`, `image: postgres:16`). However, `docker-compose.yml:87` still pins `postgres:17`. The task's Source of Truth rule ("When documentation and implementation disagree, document the discrepancy") was not followed here — the docs now silently assert a single version while the two deployment paths disagree.
- **Impact:** Undocumented environment inconsistency; a reader assumes a uniform PostgreSQL 16 when the Compose-based local path runs 17.
- **Recommendation:** Document the version divergence explicitly (e.g., "Kubernetes/Helm: postgres:16; docker-compose: postgres:17") rather than silently selecting one.

### Finding 5 — Minor — Serving-layer endpoint table omits `GET /api/v1/pipelines/{run_id}`

- **Affected file/reference:** `platform-inventory-m13.md` §7.1 endpoint table.
- **Problem:** `services/api/routes/v1/pipelines.py:79` defines `GET /{run_id}` (`PipelineRunResponse`), which is absent from the endpoint inventory. The table lists 14 endpoints while 15 are implemented (the "13+ endpoints" figure remains technically correct).
- **Impact:** Incomplete endpoint inventory; minor accuracy gap.
- **Recommendation:** Add `GET /api/v1/pipelines/{run_id}` to the table.

---

## 6. Non-Defect Observations

- The primary deliverable, `platform-inventory-m13.md`, is thorough, well-structured, and evidence-indexed. Its central insight — that the actual data flow diverges from the conceptual architecture (Warehouse Loader reads Silver, Airflow operates over PostgreSQL, Gold exists only as PostgreSQL tables) — is accurate and independently confirmed against the codebase.
- The "Architecture Findings and Follow-ups" section (§15) is disciplined: confirmed facts (C1–C9), known limitations (L1–L4), hypotheses (H1–H3), and M14/M15 deferrals are clearly separated, and no hypothesis is presented as a confirmed defect. The honest "No circuit breakers are implemented" statement (C4) is a good example of not over-claiming.
- Performance figures (TASK-109/110/111: 95.55/305.88/333.43 eps; restart counts 30/35; file counts 18,880/20,140) are reproduced exactly and are correctly labeled producer-side only, with no invented measurements.
- The DOT diagram restructure (splitting Gold into three PostgreSQL analytical tables, adding Observability/Kubernetes/Performance/Future clusters) is a meaningful improvement over the M0–M6 version.
- The correction of the DQ check count from "5" to "4" matches the actual DAG implementation.

---

## 7. Verdict

**CHANGES REQUIRED**

The core deliverable is high-quality and the platform inventory is substantively accurate and well-evidenced. However, the commit cannot be accepted as-is for three reasons:

1. **High** — It modifies `docs/performance/bottleneck-analysis.md` out of scope, re-introducing task-specification attribution for the Warehouse Loader OOM observations and reversing the completed TASK-FIX-115 provenance fix (Finding 1).
2. **Moderate** — It deletes `docs/reviews/TASK-FIX-115-review.md`, removing another task's review provenance (Finding 2).
3. **High** — It fails an explicit acceptance criterion: the SVG diagrams were not regenerated, leaving committed SVGs that contradict the updated DOT sources (Finding 3).

Blocking actions (do not fix in this review): revert the `bottleneck-analysis.md` provenance change; restore `TASK-FIX-115-review.md` (or obtain an explicit governance decision); regenerate the SVGs from the DOT sources. Findings 4 and 5 are non-blocking accuracy fixes.
