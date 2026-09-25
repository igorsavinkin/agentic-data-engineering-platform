# TASK-FIX-115 — Correct Performance Evidence Provenance

## Objective

Correct the evidence provenance in:

`docs/performance/bottleneck-analysis.md`

TASK-115 currently attributes several Warehouse Loader runtime observations
to the TASK-115 task specification, although those observations are not
present in the committed task specification or committed benchmark artifacts.

This is a documentation-only correction.

Do not modify runtime code, benchmark results, infrastructure, or architecture.


## Context

TASK-115 was implemented and merged in PR #143.

The final Qwen review identified one non-blocking Moderate finding:
the bottleneck report retains several runtime observations and incorrectly
attributes them to the TASK-115 task specification.

The affected observations are:

- `OOMKilled`
- exit code `137`
- approximately `55,361` Silver Parquet files
- `134` Warehouse Loader restarts

These values originated from a manual runtime inspection but were not
preserved in a committed benchmark artifact.

They must therefore NOT be presented as committed benchmark evidence or as
values contained in the TASK-115 task specification.


## Authoritative Evidence

The authoritative committed evidence currently includes:

- Warehouse Loader restart count: 30 during TASK-110 evidence
- Warehouse Loader restart count: 35 during TASK-111 evidence
- Silver Parquet file count: 18,880 in the committed E2E report
- Silver Parquet file count: 20,140 in the committed E2E report
- successful Warehouse Loader cycle:
  `read=20140 loaded=20140 failed=0`

Use the existing committed repository artifacts as the authoritative sources.

Do not invent or reconstruct missing benchmark evidence.


## Required Changes

Review all occurrences in:

`docs/performance/bottleneck-analysis.md`

of:

- `OOMKilled`
- exit code `137`
- `55,361`
- `134`
- references to "task specification runtime observations"

Remove any false attribution stating or implying that these values are
contained in the TASK-115 task specification.

Preferred approach:

Remove the unverifiable figures from the authoritative analysis where they
are unnecessary.

If retaining them provides useful investigation context, they must be
explicitly classified as uncommitted manual runtime observations that cannot
be independently verified from repository artifacts.

Such observations:

- must not support a confirmed bottleneck;
- must not be treated as benchmark measurements;
- must not be attributed to the TASK-115 specification;
- may only motivate further investigation.


## Classification

The Warehouse Loader restart behavior remains an:

`Observed limitation`

unless committed evidence demonstrates a specific root cause.

Do NOT classify the Warehouse Loader as a confirmed OOM bottleneck based on
the uncommitted runtime observation.

Possible explanations such as:

- Parquet file count
- Polars scanning behavior
- memory limit
- batch sizing
- MinIO behavior

remain hypotheses unless supported by profiling or committed runtime evidence.


## Scope

Allowed:

- update `docs/performance/bottleneck-analysis.md`;
- update the corresponding review artifact if required by the normal review
  workflow.

Not allowed:

- application code changes;
- Kubernetes changes;
- benchmark implementation changes;
- performance optimizations;
- architecture changes;
- new benchmark numbers;
- unrelated documentation changes.


## Verification

Verify that:

1. No statement falsely attributes the uncommitted Warehouse Loader runtime
   observations to the TASK-115 specification.

2. Authoritative quantitative conclusions use committed repository evidence.

3. The Warehouse Loader remains classified as an observed limitation unless
   stronger committed evidence exists.

4. Hypotheses remain clearly separated from verified facts.

5. No benchmark numbers are invented.

6. Existing valid TASK-115 conclusions are preserved.


## Acceptance Criteria

- [ ] False TASK-115 specification attribution is removed.
- [ ] `OOMKilled`, exit code `137`, `55,361`, and `134` are either removed
      from the authoritative analysis or explicitly marked as uncommitted,
      independently unverified runtime observations.
- [ ] Uncommitted observations do not support confirmed bottleneck claims.
- [ ] Warehouse Loader restart behavior remains an observed limitation.
- [ ] Committed TASK-109–114 benchmark results remain unchanged.
- [ ] TASK-114 API latency results remain unchanged.
- [ ] Throughput analysis remains unchanged unless correcting provenance.
- [ ] No runtime/code/configuration behavior is changed.
- [ ] Final documentation remains internally consistent.
- [ ] Qwen review passes according to the normal review workflow.
