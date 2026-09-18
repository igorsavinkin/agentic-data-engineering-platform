# OCR vs Qwen Review Comparison — TASK-056, TASK-057, TASK-058

**Date:** 2026-09-18
**Method:** Post-merge Qwen reviews run against merged commits; compared against the OCR reviews that gated each PR.

---

## Executive Summary

| Task | OCR Verdict | Qwen Verdict | OCR High | Qwen High | OCR Medium | Qwen Medium |
|------|-------------|--------------|----------|-----------|------------|-------------|
| TASK-056 | APPROVED | APPROVED | 1 (fixed) | 0 | 2 | 3 |
| TASK-057 | APPROVED | CHANGES_REQUIRED | 0 | **1** | 2 | 4 |
| TASK-058 | APPROVED | CHANGES_REQUIRED | 0 | **1** | 2 | 3 |

**Two of three tasks would have been blocked by Qwen.** Real defects shipped to main that OCR approved:

1. **TASK-057 H1** — The persistence layer's default calling path silently drops data (replay key collision with no observability). This is the core deliverable of the task.
2. **TASK-058 H1** — `|| true` in `airflow-init` swallows `db migrate` failures, defeating the `service_completed_successfully` health gate.

---

## TASK-056: Data Quality Framework

### Findings Comparison

| # | Severity | OCR | Qwen | Status |
|---|----------|-----|------|--------|
| Row counting bug | High | Caught, fixed | Confirmed fixed | Resolved |
| Protocol `Any` | Medium | Flagged | Retained as Low | Acknowledged |
| Overlap with existing validation | Medium | Flagged (wrong module ref) | Corrected (event-contract/parquet-schema) | Acknowledged |
| Schema docstring mismatch | — | Missed | **M1** | Open |
| NaN blind spot | — | Missed | **M2** | Open |
| Null ignored by AllowedValuesCheck | — | Missed | **M3** | Open |
| Naive datetime crash | — | Missed | L1 | Open |
| Empty-DF inconsistency | — | Missed | L2 | Open |
| Freshness `failed_records` conflation | — | Missed | L3 | Open |
| Unused `SKIPPED`/`severity` surface | — | Missed | L6 | Open |

### Assessment

OCR caught the one correctness bug that mattered (row counting). Qwen went deeper on runtime edge cases (NaN, null handling) and spec alignment. The NaN and null gaps (M2, M3) are real data-quality blind spots but non-blocking for the framework's initial scope. The schema docstring mismatch (M1) should be reconciled before persistence wiring.

---

## TASK-057: Quality Result Persistence

### Findings Comparison

| # | Severity | OCR | Qwen | Status |
|---|----------|-----|------|--------|
| `WriteResult.written` counts attempted | Medium | Flagged | Retained as M3 | Acknowledged |
| UNIQUE on `replay_key` with `server_default=''` | Medium | Flagged | Retained as L1 | Acknowledged |
| Replay key collapse → silent data loss | — | Missed | **H1** | **Critical** |
| Spec §13 mismatch unresolved | — | Missed | **M1** | Open |
| JSON vs JSONB migration drift | — | Missed | **M2** | Open |
| psycopg2 hard import-time dependency | — | Missed | **M4** | Open |
| Empty `details` → NULL round-trip | — | Missed | L2 | Open |
| Integration tests break hermetic convention | — | Missed | L3 | Open |
| `latest_status` collapses contexts | — | Missed | L4 | Open |
| `:` delimiter unescaped in replay key | — | Missed | L5 | Open |

### Assessment

**The biggest gap.** OCR approved a persistence layer whose default calling path (`write_result(result)` with no context) silently loses data on replay — exactly the defect the task was designed to prevent. The replay key collapses to `"<check_name>:_:_:_"` when `pipeline_run_id`, `observation_id`, and `source` all default to `None`, and `ON CONFLICT DO NOTHING` drops the row with no signal to the caller.

Additionally, the spec §13 schema mismatch flagged in TASK-056's Qwen review as "must be reconciled before TASK-057" was never addressed — a process failure.

---

## TASK-058: Airflow Local Deployment

### Findings Comparison

| # | Severity | OCR | Qwen | Status |
|---|----------|-----|------|--------|
| Init SQL first-run-only | Medium | Flagged | Retained as M1 | Acknowledged |
| Empty `FERNET_KEY` default | Medium | Flagged | Retained as M2 | Acknowledged |
| `|| true` swallows `db migrate` failure | — | **Misread** | **H1** | **Critical** |
| PostgreSQL 17 outside Airflow support matrix | — | Missed | **M3** | Open |
| Redundant privilege SQL | — | Missed | L1 | Open |
| Superuser credential coupling | — | Missed | L3 | Open |
| Brittle string-matching tests | — | Missed | L4 | Open |
| Entrypoint override | — | Missed | L5 | Open |
| Webserver DAG-parse variable constraint | — | Missed | L6 | Open |

### Assessment

OCR explicitly misread the shell command: it described `|| true` as scoped to user creation and asserted "`db migrate` is inherently idempotent." In reality, `&&` and `||` are left-associative with equal precedence, so `|| true` applies to the entire chain. Qwen verified this with a shell probe. The fix is a one-line parenthesization.

---

## Root Cause Analysis: Why OCR Missed These

1. **No runtime verification.** OCR reviews the diff statically. Qwen ran shell probes, Polars runtime tests, and verified actual behavior. The NaN blind spot (TASK-056 M2), replay key collapse (TASK-057 H1), and shell precedence (TASK-058 H1) all require execution to catch.

2. **No cross-task context.** OCR reviewed each task in isolation. Qwen tracked the TASK-056→TASK-057 precondition (schema reconciliation) and caught that it was ignored.

3. **No spec cross-referencing.** OCR referenced the spec but didn't do field-by-field comparison. Qwen compared every model field against `ai/SPECIFICATION.md` §13 and found mismatches.

4. **Confirmation bias on "obvious" patterns.** The `|| true` pattern is common and looks correct at a glance. OCR accepted it; Qwen parsed the actual shell semantics.

---

## Recommendations

1. **Add runtime probes to OCR.** Even simple ones (shell precedence check, NaN test, null test) would have caught 2 of the 3 High findings.
2. **Require cross-task precondition checks.** When a prior review flags a precondition for a subsequent task, the next review must verify it was addressed.
3. **Field-by-field spec alignment check.** For persistence/schema tasks, compare every model field against the spec table definition.
4. **Consider dual-review for high-risk tasks.** TASK-057 (persistence) and TASK-058 (infrastructure) both had critical misses. A second review pass would have caught them.

---

## Files

- `docs/reviews/TASK-056-review.md` — OCR review
- `docs/reviews/TASK-056-qwen-review.md` — Qwen review
- `docs/reviews/TASK-057-review.md` — OCR review
- `docs/reviews/TASK-057-qwen-review.md` — Qwen review
- `docs/reviews/TASK-058-review.md` — OCR review
- `docs/reviews/TASK-058-qwen-review.md` — Qwen review
