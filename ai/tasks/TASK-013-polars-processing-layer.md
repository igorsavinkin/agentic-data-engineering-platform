# TASK-013 — Polars Processing Layer

## Objective
Create the processor-layer foundation that converts canonical product-observation events into Polars-based analytical records without prematurely implementing normalization, validation, deduplication, DLQ, or metrics policy.

## Context
Milestone 2 transforms Kafka events into normalized analytical records:

```text
Kafka → Consumer → Validation → Polars → Valid / Invalid
```

Preserve the platform invariant: **at-least-once delivery + idempotent processing**.

## References
Read current repository versions of `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and relevant TASK-006–012 implementations.

## Dependencies
- TASK-006 canonical event schema
- TASK-008 producer
- TASK-009/TASK-010 consumer foundation
- TASK-012 integration baseline before milestone completion

## Scope
- Establish processor package/service structure.
- Define explicit canonical-event → Polars boundaries.
- Add deterministic, pure transformation entry points.
- Preserve event/source/product identifiers and observation timestamps.
- Keep Kafka I/O outside the pure processing core.

## Requirements
1. Use Polars as the primary tabular processing library.
2. Convert one or more canonical events into a deterministic Polars representation.
3. Preserve event identity, source identity, external product identity, product fields, schema version, and current contract timestamps.
4. Avoid Python list/dict processing where Polars expressions are appropriate beyond boundary conversion.
5. Keep transformation logic independently unit-testable.
6. Do not write PostgreSQL or Parquet.
7. Do not publish validated output yet unless a minimal interface stub is explicitly required by current higher-authority docs.
8. Document processor entry points for TASK-014–018.

## Out of Scope
- normalization policy
- data validation
- deduplication
- DLQ routing
- processor metrics
- end-to-end processor integration
- data-lake persistence

## Tests Required
- canonical event → Polars row/DataFrame
- multi-event deterministic schema/columns
- exact identifier/timestamp preservation
- nullable/optional fields
- empty input
- deterministic behavior / no input mutation
- existing tests remain green

## Acceptance Criteria
- Canonical events convert into a documented Polars analytical representation.
- Processor core is transport-independent.
- No later-task policy is pulled forward.
- Unit tests, Ruff, format check, and mypy pass.

## Expected Deliverables
- processor package/service foundation
- Polars transformation module(s)
- unit tests
- concise processor docs/README if needed

## Agent Instructions
Implement TASK-013 only. If architecture is ambiguous, stop and report. Inspect the final Git diff before committing and do not implement TASK-014+.
