# TASK-FIX-TASK-NAMING-DOCS

## Objective

Allow documentation/architecture task specifications using the
`TASK-DOCS-*` naming convention in the repository structure verifier.

## Scope

Update:

- `scripts/verify_repository_structure.py`
- relevant deterministic tests

Allow:

`TASK-DOCS-*.md`

in addition to the currently supported:

- `TASK-NNN-*.md`
- `TASK-FIX-*.md`
- `TASK-K8S-FIX-*.md`

Do not relax validation for arbitrary `TASK-*` filenames.

## Acceptance Criteria

- [ ] `TASK-DOCS-PLATFORM-INVENTORY-M13.md` is accepted.
- [ ] numbered task files remain accepted.
- [ ] `TASK-FIX-*` remains accepted.
- [ ] `TASK-K8S-FIX-*` remains accepted.
- [ ] arbitrary invalid names such as `TASK-WHATEVER.md` are still rejected.
- [ ] `tests/test_repository_structure.py` passes.
- [ ] repository quality checks pass.# TASK-FIX-TASK-NAMING-DOCS

## Required Tests

Add deterministic unit tests for the task filename policy.

At minimum verify:

- `TASK-114-measure-api-latency.md` → accepted
- `TASK-FIX-KAFKA-LAG-PROBE-TEST.md` → accepted
- `TASK-K8S-FIX-003.md` → accepted
- `TASK-DOCS-PLATFORM-INVENTORY-M13.md` → accepted
- `TASK-WHATEVER.md` → rejected

Prefer extracting the filename validation policy into a small testable
function instead of testing the behavior only through the full repository
structure subprocess check.

