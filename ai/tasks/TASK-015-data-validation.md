# TASK-015 — Data Validation

## Objective
Add explicit data-quality validation for normalized processor records and deterministically separate valid and invalid outcomes while preserving diagnostic information.

## Dependencies
- TASK-014
- current `ai/SPECIFICATION.md` data-quality rules

## Requirements
1. Validate required fields and normalized types.
2. Validate price semantics according to the current contract.
3. Validate timestamps.
4. Validate availability enum values.
5. Validate schema version compatibility where processor-owned.
6. Preserve event identity/source and enough context for diagnostics.
7. Support deterministic multiple-error reporting where useful.
8. Never silently drop invalid records.
9. Expose valid/invalid counts to later metrics without coupling validation to Prometheus.
10. Use Pandera or another explicit validation layer if consistent with the current repository.

## Out of Scope
- Kafka DLQ publication
- deduplication
- persistence of data-quality results
- processor metrics implementation

## Tests Required
- missing required field
- invalid price
- invalid timestamp
- invalid availability
- unsupported schema version
- multiple simultaneous failures
- valid record path
- diagnostic context preserved

## Acceptance Criteria
- Batch deterministically splits into valid and invalid records.
- Every invalid record has diagnosable reason(s).
- No invalid event silently disappears.
- Tests and quality checks pass.

## Agent Instructions
Implement TASK-015 only. Keep the validation result interface suitable for TASK-017 routing.
