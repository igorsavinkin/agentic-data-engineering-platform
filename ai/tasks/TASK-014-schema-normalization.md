# TASK-014 — Schema Normalization

## Objective
Implement deterministic normalization of processor records into the canonical analytical schema expected by validation and downstream Silver-layer processing.

## Dependencies
- TASK-013
- current canonical event contract

## Scope
Define and implement normalized field names, types, null handling, timestamps, numeric price representation, availability, and other supported canonical fields using Polars.

## Requirements
1. Define the normalized analytical schema in one reusable place.
2. Normalize types without silently corrupting invalid values.
3. Normalize timestamps to the project convention.
4. Preserve event ID, source ID, external product ID, schema version, and distinct producer/collection timestamps when defined.
5. Normalize availability only to allowed values.
6. Apply predictable string/null handling without changing semantic IDs/URLs unless specified.
7. Prefer Polars expressions.
8. Invalid/unparseable values must remain detectable by TASK-015.
9. No silent row dropping.
10. Document schema invariants.

## Out of Scope
- validation rejection policy
- deduplication
- DLQ publishing
- metrics
- Kafka orchestration

## Tests Required
- valid type normalization
- timestamp normalization
- nullable fields
- malformed values remain detectable
- availability enum handling
- exact ID preservation
- stable schema regardless of row order

## Acceptance Criteria
- Valid inputs normalize into one stable analytical schema.
- Failures are explicit and available for validation.
- No records silently disappear.
- Tests and quality checks pass.

## Agent Instructions
Implement TASK-014 only. Do not implement validation/deduplication/DLQ behavior.
