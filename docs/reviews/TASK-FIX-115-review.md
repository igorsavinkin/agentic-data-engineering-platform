# TASK-FIX-115 Review — Correct Performance Evidence Provenance

## 1. Review Header

- **Task ID:** TASK-FIX-115 — Correct Performance Evidence Provenance
- **Review date:** 2026-09-25
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `75ed14ed47684564af280c0773655b28cf5a40a1...edd7bb46566dbf2b4ff151ee47bfe044d6637b65`
- **Reviewed commits:**
  - `edd7bb46566dbf2b4ff151ee47bfe044d6637b65` — `fix(TASK-FIX-115): correct Warehouse Loader evidence provenance classification`
- **Reviewed HEAD:** `edd7bb46566dbf2b4ff151ee47bfe044d6637b65` on `feature/TASK-FIX-115-EVIDENCE-PROVENANCE`
- **Scope:** Documentation-only correction to `docs/performance/bottleneck-analysis.md` — remove false attribution of uncommitted Warehouse Loader runtime observations to the TASK-115 task specification.
- **Verdict:** CHANGES REQUIRED

---

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
|---|---|---|
| False TASK-115 specification attribution is removed | **Not met** | The document retains, in five locations, statements that "the task specification documents …" the OOMKilled / exit 137 / ~55,361 / 134 values (lines 43–44, 412, 547–549, 583–585, 599–600, 639). The wording was re-framed from "reports" to "documents … manual runtime observations … not benchmark measurements", but the provenance claim — that these values originate from the TASK-115 task specification — is still asserted. See Finding 1. |
| `OOMKilled`, `137`, `55,361`, `134` removed from authoritative analysis **or** explicitly marked uncommitted/unverified | **Met** | Section renamed to "Manual Runtime Observations (Uncommitted)" (line 410) and the values are explicitly labeled "not benchmark measurements" and "not independently verifiable from committed benchmark artifacts" (lines 412–414, 547–549, 583–585). |
| Uncommitted observations do not support confirmed bottleneck claims | **Met** | The "Confirmed Bottlenecks" section contains only "Load Generator Producer-Call Duration". The Warehouse Loader is classified as "Observed limitation" (§4) and "Hypothesis" (§2), never a confirmed OOM bottleneck. |
| Warehouse Loader restart behavior remains an observed limitation | **Met** | §4 "Warehouse Loader Instability" is classified "Observed limitation" (line ~536). |
| Committed TASK-109–114 benchmark results unchanged | **Met** | Only `docs/performance/bottleneck-analysis.md` changed; no benchmark artifact modified. |
| TASK-114 API latency results unchanged | **Met** | API latency section untouched by the diff. |
| Throughput analysis unchanged unless correcting provenance | **Met** | Throughput analysis section untouched. |
| No runtime/code/configuration behavior changed | **Met** | Markdown-only change; no code, config, or infra files touched. |
| Final documentation remains internally consistent | **Partially met** | Internally the document is now consistent (all four values are consistently labeled uncommitted). However, the document is inconsistent with the *TASK-115 task specification itself*, which at the reviewed HEAD contains these values and asserts "The OOM condition is confirmed runtime evidence." See Finding 2. |
| Qwen review passes according to the normal review workflow | **This review** | See verdict. |

---

## 3. Git Diff Review

- **Range contents:** One commit (`edd7bb4`) modifying a single file: `docs/performance/bottleneck-analysis.md` (+31/−23).
- **Branch isolation:** Correct for the fix. `git merge-base HEAD main` is `75ed14e`; the feature branch contains exactly one commit beyond `main` — `edd7bb4`, the fix under review. The task spec (`ai/tasks/TASK-FIX-115-EVIDENCE-PROVENANCE.md`) was committed to `main` in `75ed14e`, which is the merge-base and therefore outside the reviewed range.
- **Scope correctness:** The change is confined to the single documentation file named in the task. No other file is touched.
- **Unrelated changes:** None within the reviewed commit.
- **Architectural changes:** None. No code, config, or dependency changes.
- **Dependency/configuration changes:** None.
- **Accidental changes:** None. No debugging code, temporary files, dead code, generated artifacts, or secrets.
- **Out-of-scope changes:** None within the reviewed commit. (Contextual note: the task spec itself and a *prior* amendment to the TASK-115 spec — commit `29e06a3` — are on `main`, not on this feature branch, and are addressed under Finding 2.)

The fix commit is a legitimate, in-scope documentation edit. Its re-wording is internally consistent: every occurrence of "reports" was changed to "documents … manual runtime observations … not benchmark measurements", the section heading was renamed, and explicit "not benchmark measurements" / "uncommitted" disclaimers were added. The fix does **not** touch the committed benchmark figures (30/35 restarts, 18,880/20,140 files, `read=20140 loaded=20140 failed=0`), which are already correct and independently verifiable.

---

## 4. Test and Verification Review

- **Tests examined:** None added or changed. This is a documentation-only task; no deterministic test surface applies (consistent with the task's "documentation-only" scope and prior docs-only tasks).
- **Integration tests:** Not applicable. The change does not touch Kafka, persistence, MinIO/S3, or infrastructure boundaries.
- **Independent verification performed by reviewer:**
  - Diff scope → **Independently verified**: `git diff 75ed14e...edd7bb4 --stat` shows exactly one file, `docs/performance/bottleneck-analysis.md` (+31/−23).
  - Authoritative restart counts → **Independently verified**: `30` (TASK-110) in `docs/benchmark-500-eps.md:51,62`; `35` (TASK-111) in `docs/benchmark-1000-eps.md:60,167`.
  - Silver Parquet counts → **Independently verified**: `file_count=18880` and `file_count = 20140` in `docs/e2e/E2E-SOURCE-TO-POSTGRESQL-2026-09-24.md` (§8 and §11).
  - Successful load cycle → **Independently verified**: `Load cycle complete: read=20140 loaded=20140 failed=0` in the E2E report (line 338).
  - Warehouse Loader classification → **Independently verified**: not present under "Confirmed Bottlenecks"; present under "Observed Limitations" and "Hypotheses Requiring Investigation".
- **Verification status:** Authoritative quantitative claims and diff scope — **Independently verified**. The provenance defect (Finding 1) and governance conflict (Finding 2) were identified by direct inspection of `docs/performance/bottleneck-analysis.md` and `ai/tasks/TASK-115-document-bottlenecks.md`.
- **Tests not rerun:** No test run was performed; the change is Markdown-only with no code/test surface.

---

## 5. Findings

### Finding 1 — High — "Task specification" attribution retained; core requirement "must not be attributed to the TASK-115 specification" not satisfied

- **Severity:** High
- **Affected file/reference:** `docs/performance/bottleneck-analysis.md` lines 43–44, 412, 547–549, 583–585, 599–600, 639
- **Problem:** The TASK-FIX-115 task specification states, in its "Classification" section, that the four uncommitted observations **"must not be attributed to the TASK-115 specification"**, and in "Required Changes" requires removing "any false attribution stating or implying that these values are contained in the TASK-115 task specification." The fix, however, retains the attribution to the task specification in five distinct places, changing only the verb and the surrounding disclaimer:

  - Line 43–44: *"The task specification documents manual runtime observations — OOMKilled termination, exit code 137, and higher restart and file counts …"*
  - Line 412: *"The TASK-115 task specification documents the following manual runtime observations from a separate inspection."*
  - Line 547–548: *"The TASK-115 task specification documents OOMKilled as the termination reason …"*
  - Line 583–584: *"The task specification documents OOMKilled as the termination reason with 134 restarts and ~55,361 files …"*
  - Line 639: *"The task specification documents OOMKilled as the termination reason in its manual runtime observations section …"*

  The fix correctly reclassifies the values as uncommitted manual observations and correctly prevents them from supporting any confirmed bottleneck. But it leaves "the TASK-115 task specification" named as the *source* of these values. That is precisely the provenance claim the task was created to remove.
- **Impact:** The task's primary acceptance criterion — "False TASK-115 specification attribution is removed" — is not met. A reader is still told that these figures appear in the TASK-115 specification, which is the exact misattribution the original TASK-115 review flagged. The provenance correction is therefore incomplete: the classification changed, but the attribution did not.
- **Recommendation:** Remove "the task specification documents …" phrasing and instead state that these values "originated during implementation as a manual runtime inspection and could not be traced to any committed source." The source of the values should not be named as the task specification (or any committed artifact), consistent with the task's "must not be attributed to the TASK-115 specification" rule. Alternatively, if the figures are unnecessary for investigation context, remove them entirely.

### Finding 2 — High — Governance conflict: the TASK-115 task specification now contains the values and asserts "The OOM condition is confirmed runtime evidence", contradicting TASK-FIX-115

- **Severity:** High (governance conflict — requires human decision)
- **Affected file/reference:** `ai/tasks/TASK-115-document-bottlenecks.md` (as amended by commit `29e06a3` "feat: Additional rules for perfrormance check", which is on `main` and an ancestor of the reviewed HEAD), specifically its "Additional Runtime Observation — Warehouse Loader" section
- **Problem:** The TASK-FIX-115 task spec is premised on the claim that the four observations "are not present in the committed task specification or committed benchmark artifacts." This premise is factually inaccurate at the reviewed HEAD. Commit `29e06a3` (on `main`, *before* the TASK-FIX-115 spec was written) amended `ai/tasks/TASK-115-document-bottlenecks.md` to add exactly these values — `OOMKilled`, exit code `137`, "approximately 55,361 Silver Parquet files", "134 pod restarts" — and further asserts **"The OOM condition is confirmed runtime evidence."**

  This creates a direct, unresolved conflict between two task specifications at the same authority level:
  - `TASK-115-document-bottlenecks.md` (§ Additional Runtime Observation): "The OOM condition is confirmed runtime evidence."
  - `TASK-FIX-115-EVIDENCE-PROVENANCE.md` (§ Classification): "Do NOT classify the Warehouse Loader as a confirmed OOM bottleneck based on the uncommitted runtime observation."

  The two documents cannot both be true. This conflict is not introduced by the fix, but it directly undermines the fix: because `29e06a3` planted the values into the TASK-115 spec *after* the original review, "the task specification documents …" is now technically true, which may be why the implementer retained that wording. The result is that the TASK-FIX-115 objective (stop presenting the values as task-spec content) cannot be cleanly satisfied until the TASK-115 spec's "confirmed runtime evidence" assertion is reconciled with TASK-FIX-115.
- **Impact:** The provenance correction is blocked on a contradictory upstream document. If left unresolved, the repository simultaneously asserts (a) in TASK-115 that OOM is "confirmed runtime evidence" and (b) in TASK-FIX-115 that OOM is an uncommitted, unverified manual observation. Any future reader will be unable to determine the authoritative provenance of these values.
- **Recommendation:** Escalate for a human architectural/process decision. Either (a) remove or re-word the "Additional Runtime Observation — Warehouse Loader" section (and the "confirmed runtime evidence" assertion) from `ai/tasks/TASK-115-document-bottlenecks.md` so it no longer claims these uncommitted values as task-spec content, or (b) formally decide that the amended TASK-115 spec is authoritative and update TASK-FIX-115 accordingly. This is not a change the reviewer is authorized to make.

---

## 6. Non-Defect Observations

- The fix is meticulous about the *classification* dimension of the task. Every authoritative quantitative claim (30/35 restarts, 18,880/20,140 files, the successful load cycle) remains correct and was independently verified against its committed source.
- The "Confirmed Bottlenecks" section is properly conservative: the only confirmed bottleneck is the well-evidenced producer-call-duration constraint, and the Warehouse Loader is consistently treated as an observed limitation / hypothesis.
- The re-wording is internally consistent within `bottleneck-analysis.md`: all four values are now uniformly labeled "uncommitted", "manual runtime observations", and "not benchmark measurements".
- The commit message for `edd7bb4` accurately describes the change (strengthen classification, rename heading, add disclaimers), even though it overstates the outcome relative to the task's "remove attribution" requirement.

---

## 7. Verdict

**CHANGES REQUIRED**

The fix correctly accomplishes the *classification* half of TASK-FIX-115: the four uncommitted values are now explicitly marked as "manual runtime observations … not benchmark measurements", the Warehouse Loader remains an observed limitation rather than a confirmed OOM bottleneck, and the committed benchmark figures are untouched and independently verified.

However, the task's primary *provenance* requirement is not met. The document still names "the TASK-115 task specification" as the source of these values in five places (Finding 1), in direct violation of the task's "must not be attributed to the TASK-115 specification" rule. This is compounded by an unresolved governance conflict (Finding 2): commit `29e06a3` amended `ai/tasks/TASK-115-document-bottlenecks.md` to contain these values and assert "The OOM condition is confirmed runtime evidence", contradicting the very premise of TASK-FIX-115.

Both findings must be resolved before acceptance: (1) remove or re-source the "task specification documents …" attributions in `docs/performance/bottleneck-analysis.md`, and (2) reconcile the TASK-115 spec's "confirmed runtime evidence" assertion with TASK-FIX-115 through a human decision.
