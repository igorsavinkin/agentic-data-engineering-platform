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
- [ ] repository quality checks pass.
