# TASK-DOCS-PLATFORM-INVENTORY-M13 Review — Platform Architecture Inventory after Milestone 13 (Round 2)

## 1. Review Header

- **Task ID:** TASK-DOCS-PLATFORM-INVENTORY-M13 — Platform Architecture Inventory after Milestone 13
- **Review date:** 2026-09-25
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `9381a297600974978f5cd61e667f33464eebc856...ce488259e305204282532e8cfec5e619c4560546` (three-dot; resolves to merge-base `d809de9e2210cff73ab824bf98f4d8664bfbf9f4`)
- **Reviewed commits (two-dot `9381a297..ce48825`):**
  - `5be6530d666628899cdd2c49f8e0c7e056f1b505` — `docs(TASK-DOCS-PLATFORM-INVENTORY-M13): evidence-based platform inventory after M13`
  - `ce488259e305204282532e8cfec5e619c4560546` — `docs(TASK-DOCS-PLATFORM-INVENTORY-M13): address review findings (round 2)`
- **Reviewed HEAD:** `ce488259e305204282532e8cfec5e619c4560546` on `feature/TASK-DOCS-PLATFORM-INVENTORY-M13`
- **Scope:** Documentation/architecture reconciliation. No production behavior is expected to change.
- **Verdict:** APPROVED WITH NON-BLOCKING FINDINGS

> **Round 2 context.** This review supersedes the round 1 report (previously stored in this file, committed in `ce48825`). Round 1 returned CHANGES REQUIRED with five findings. Round 2 verifies the fixes and re-bases the review on the correct, isolated change set.

---

## 2. Requirements Coverage

| Requirement (Acceptance Criterion) | Status | Implementation evidence |
|---|---|---|
| M0–M13 implementation status accurately inventoried | **Met** | `platform-inventory-m13.md` §1 status matrix + classification legend; M14/M15 marked Planned/target only |
| Actual runtime data flow documented | **Met** | §2 implemented data path + "Key Differences from Conceptual Architecture" |
| Service boundaries match current implementation | **Met** | §3 (ingestion, processor, raw-writer, lake-writer, warehouse-loader, api, agent) |
| Kafka producers/consumers/topics inventoried | **Met** | §4 — 5 topics, 3 consumer groups, 4 producers, DLQ, lag |
| Bronze/Silver/Gold semantics match implementation | **Met** | §5; Gold documented as PostgreSQL-only (no Gold Parquet) |
| Warehouse Loader and Airflow roles correctly represented | **Met** | §6.2 + §13 — Warehouse Loader reads Silver; Airflow is a batch processor over PostgreSQL, not a pipeline stage |
| FastAPI serving architecture documented | **Met** | §7.1 — endpoint table, readiness/health, DB dependency |
| LangGraph Agent boundaries documented | **Met** | §7.2 — graph flow, intents, read-only guarantees, in-process deployment |
| Kubernetes/Helm topology documented | **Met** | §8 — namespace, Deployments, StatefulSets, Jobs, ConfigMaps/Secrets, Helm layout |
| Observability stack documented | **Met** | §9 — Prometheus/Grafana/OTel/Jaeger, metrics, implemented-vs-deployed split |
| Reliability/failure mechanisms documented | **Met** | §10 — retries, idempotency, replay, DLQ, no circuit breakers (honestly stated) |
| TASK-108–115 evidence summarized without invented measurements | **Met** | §11 — exact benchmark figures preserved; target vs actual separated |
| Verified E2E paths distinguished from merely implemented | **Met** | §12 matrix separates Implemented / Tested / E2E verified / Performance measured |
| Runtime-vs-conceptual architecture differences documented | **Met** | §13 (Silver→Warehouse Loader, Airflow role, Gold storage, Agent boundaries) |
| M14/M15 remain future work | **Met** | §14 — both marked Planned / Target Only |
| Architecture DOT/source diagrams updated | **Met** | `container-view.dot`, `data-flow.dot` updated to M0–M13 |
| SVG diagrams regenerated from their sources | **Met** (round 2 fix) | Both SVGs regenerated in `ce48825`; content matches DOT sources (see §3) |
| Documentation contains repository evidence references | **Met** | Evidence Index + per-section evidence paths |
| No production behavior changed | **Met** | Diff is docs-only (7 files, all under `docs/`) |
| Architecture findings/follow-ups documented | **Met** | §15 — Confirmed / Known limitations / Investigation / M14 / M15 |
| Findings distinguish facts, limitations, hypotheses | **Met** | §15 classification is disciplined |
| No architectural finding silently fixed | **Met** | §15 reports findings rather than fixing them |
| Relevant documentation/structure checks pass | **Met** (independently verified) | `python scripts/verify_repository_structure.py` passes (see §4) |

---

## 3. Git Diff Review

**Change set:** Two commits (`5be6530`, `ce48825`). Net three-dot diff (merge-base `d809de9` → `ce48825`) touches seven files, all under `docs/`:

| File | Change |
|---|---|
| `docs/architecture-communication/README.md` | +14/−12 (M0–M13 status, M14/M15 next steps) |
| `docs/architecture-communication/container-view.dot` | +143/−72 (observability/k8s/perf/future clusters) |
| `docs/architecture-communication/container-view.svg` | regenerated |
| `docs/architecture-communication/data-flow.dot` | +35/−25 (PG version removed, 4 DQ checks, serving solid lines) |
| `docs/architecture-communication/data-flow.svg` | regenerated |
| `docs/architecture/platform-inventory-m13.md` | +1278 (primary deliverable) |
| `docs/reviews/TASK-DOCS-PLATFORM-INVENTORY-M13-review.md` | +151 (round 1 report committed) |

- **Scope correctness:** Correct. All changes are documentation. The primary deliverable (`platform-inventory-m13.md`) plus the DOT/SVG/README diagram updates are in scope.
- **Round 1 false positives confirmed.** Round 1 findings 1 and 2 claimed the task modified `docs/performance/bottleneck-analysis.md` and deleted `docs/reviews/TASK-FIX-115-review.md`. **Neither file is touched by either reviewed commit.** The round 1 report used a two-dot tree comparison against `03336808` (a commit on the unrelated `feature/TASK-FIX-115-EVIDENCE-PROVENANCE` side branch), which made the FIX-115 changes appear as "reverted" by the task. With the correct merge-base diff (`d809de9...ce48825`), those two files do not appear at all. **Findings 1 and 2 are false positives; no action required.**
- **Unrelated changes:** None.
- **Architectural changes:** None in code/config. All changes are documentation.
- **Accidental changes:** None (no secrets, debug code, temp files, or generated artifacts introduced beyond the intended SVGs).
- **Dependency/configuration changes:** None.
- **Branch isolation:** Correct. Both commits sit on `feature/TASK-DOCS-PLATFORM-INVENTORY-M13`; working tree clean. No other TASK-* changes are included in the range.

---

## 4. Test and Verification Review

- **Tests added/changed:** None. Documentation-only task; no deterministic code/test surface (consistent with the task's "Do not change production behavior" constraint).
- **Integration tests:** Not applicable. No Kafka/persistence/MinIO/infrastructure code paths changed.
- **Structure check (independently executed):** `python scripts/verify_repository_structure.py` → **passed** (24 directories, 5 governance documents, 139 task files).

### Independent verification performed by reviewer (round 2 focus)

- **Round 1 findings 1 & 2 false positives — Independently verified.** `git show --stat 5be6530` (4 files) and `git show --stat ce48825` (6 files) show neither `docs/performance/bottleneck-analysis.md` nor `docs/reviews/TASK-FIX-115-review.md` was touched. The three-dot diff `9381a297...ce48825` (merge-base `d809de9`) lists exactly 7 docs files and neither of those two.
- **SVG regeneration (round 1 Finding 3) — Independently verified by content inspection.** Both SVGs were modified at 22:36 on 2026-09-25 (matching `ce48825`), are complete (valid closing `</svg>`), and contain no stale markers. Specifically:
  - `container-view.svg` and `data-flow.svg` no longer contain `M0–M6`, `PostgreSQL 16`, `PostgreSQL 17`, `5 checks`, or `Observability (M10)` (parenthesized).
  - `container-view.svg` now renders `Реализовано (M0–M13) / Проектное состояние (M14+)`, `Observability [M10]`, `Kubernetes / Helm [M8/M9]`, `Performance Testing [M13]`, `Future: M14 Terraform/AWS [NOT IMPLEMENTED]`, `Terraform`, `AWS EKS`, `PostgreSQL` (no version).
  - `data-flow.svg` now renders `PostgreSQL` (no version), `(4 checks: required_fields, price_validity, freshness, duplicates)`, `(13+ endpoints)`, and the three `Gold:` tables.
  - **Limitation:** Graphviz `dot` is not available in the review environment (`dot: command not found`), so byte-for-byte regeneration and diff could not be performed. Consistency was verified by comparing SVG text labels against the DOT sources, which match.
- **PostgreSQL version discrepancy documented (round 1 Finding 4) — Independently verified.** `docker-compose.yml:87` pins `postgres:17`; `kubernetes/deployments/postgresql-statefulset.yaml:38` pins `postgres:16`; Helm `values.yaml` `postgresql.image.tag` = `"16"`. The inventory §8.3 now carries a "Version discrepancy" note stating exactly this, and both DOT labels were changed from `PostgreSQL 16` to `PostgreSQL` (version is deployment-dependent). Correct.
- **Missing endpoint added (round 1 Finding 5) — Independently verified.** `services/api/routes/v1/pipelines.py:79` defines `GET /{run_id}` (`PipelineRunResponse`). The §7.1 endpoint table now includes `GET /api/v1/pipelines/{run_id}`. A `grep` of all `services/api/routes/v1/*.py` route decorators returns exactly 15 handlers, matching the table's 15 rows (14 GET + 1 POST). The endpoint inventory is now complete.

### Remaining factual spot-checks (unchanged from round 1, re-confirmed)

- Kafka topics — 5 topics, partitions `3/3/1/1/1`, replication `1` (§4.1 matches `scripts/manage_kafka_topics.py`).
- Gold bucket absence — `libs/common/minio_storage.py` configures only `bronze` and `silver`.
- Warehouse Loader reads Silver — `services/warehouse-loader/runner.py` uses `LakeLayer.SILVER`.
- DQ check count — `airflow/dags/daily_data_quality_dag.py` defines 4 checks (matches the "4 checks" correction).
- K8s topology — 7 Deployments, 2 StatefulSets, 2 Jobs (§8 matches `kubernetes/deployments/` and Helm templates).

**Verification status:** Load-bearing factual claims and the round 2 fixes are **Independently verified**. No test suite was run (no code surface changed).

---

## 5. Findings

### Finding 1 — Moderate — Supplementary architecture-communication docs remain stale at M0–M6 and contradict the updated diagrams and inventory

- **Affected file/reference:** `docs/architecture-communication/reading-notes.md`, `docs/architecture-communication/architecture-communication-plan.md`, `docs/architecture-communication/delivery-summary.md`.
- **Problem:** These three files (dated 2026-09-18, "after TASK-062, Milestone 0–6") were not updated by either reviewed commit. They now contradict the corrected diagrams and the primary inventory:
  - `reading-notes.md` — its "Проектное состояние (M7+, не реализовано)" table lists FastAPI, Kubernetes/Helm, Observability, LangGraph Agent, Failure engineering, and Performance testing as **not implemented**; it also asserts `PostgreSQL 17` (line 112) and a "5 checks" quality framework (line 125), both now wrong (deployment-dependent version; 4 checks).
  - `architecture-communication-plan.md` — still frames the current state as "M0–M6 реализованы" and M7+ as roadmap.
  - `delivery-summary.md` — its status table lists FastAPI as "Следующий" and Kubernetes/Helm/Observability/Agent as "Roadmap".
  - The README's "Contents" table still lists these three files as current, so a reader following the README reaches stale material.
- **Impact:** The architecture-communication package is internally inconsistent: the entry point (`README.md`) and the diagrams/inventory correctly describe M0–M13, while the reading notes describe M7–M13 as unimplemented and repeat the incorrect "5 checks" / "PostgreSQL 17" claims. A reader using `reading-notes.md` as directed would be materially misled.
- **Recommendation:** Update these three files to the M0–M13 state (or clearly mark them superseded and point to `platform-inventory-m13.md`). This is a follow-up documentation change, not a production-code change. Non-blocking: the task's "at minimum" artifacts (container-view, data-flow, rendered SVGs) and the primary deliverable are all correct and updated.

> No other findings. Round 1 findings 1 and 2 are false positives (see §3); round 1 findings 3, 4, and 5 are resolved (see §4).

---

## 6. Non-Defect Observations

- The round 2 commit message accurately describes its four fixes and explicitly records the review transition ("CHANGES REQUIRED → fixes applied").
- Removing the hardcoded PostgreSQL version from the DOT labels (rather than asserting 16 vs 17 in the diagrams) is the correct treatment: the version is deployment-dependent, and the discrepancy is now documented once, in the inventory.
- The primary deliverable `platform-inventory-m13.md` remains thorough, evidence-indexed, and its central correction (Warehouse Loader reads Silver; Airflow operates over PostgreSQL; Gold is PostgreSQL-only) is independently confirmed against the codebase.
- The §15 "Architecture Findings and Follow-ups" classification (Confirmed / Known limitations / Investigation / M14 / M15) is disciplined and does not present hypotheses as confirmed defects.
- Performance figures (TASK-109/110/111: 95.55/305.88/333.43 eps; 30/35 restarts; 18,880/20,140 files) are reproduced exactly and correctly labeled producer-side, with no invented measurements.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

All three round 1 findings requiring action have been correctly resolved:

1. **SVG regeneration (was High)** — both SVGs regenerated from the DOT sources; content now matches and no stale markers remain.
2. **PostgreSQL version discrepancy (was Minor)** — documented explicitly in §8.3, and the hardcoded version removed from the diagrams.
3. **Missing endpoint (was Minor)** — `GET /api/v1/pipelines/{run_id}` added; the endpoint table now matches all 15 implemented route handlers.

Round 1 findings 1 and 2 were false positives caused by an incorrect diff base and are confirmed to not exist in the correct isolated change set.

The only remaining finding is non-blocking: three supplementary architecture-communication files (`reading-notes.md`, `architecture-communication-plan.md`, `delivery-summary.md`) still describe M0–M6 and list M7–M13 components as unimplemented. These are outside the task's "at minimum" required artifacts, and the primary deliverable and required diagrams are correct and up to date.

The repository structure check passes, the diff is strictly docs-only, and no production behavior is changed. The task is suitable for acceptance; the supplementary-docs consistency gap should be scheduled as a small follow-up.
