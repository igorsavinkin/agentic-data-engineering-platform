# TASK-038 — End-to-End Tests

## Objective
Add deterministic end-to-end tests proving that both initial sources can be processed through the full platform.

## Required Scenarios
1. Fake Store observation through every layer.
2. Best Buy observation through every layer.
3. Multiple observations from both sources.
4. Historical observation for the same source product.
5. Invalid observation follows invalid/DLQ path and does not enter Silver/warehouse.
6. Source adapter failure does not corrupt downstream state.
7. Stable identifiers allow one observation to be traced across layers.

## Requirements
- No live external dependency in normal CI.
- Use deterministic source fixtures/mocked HTTP responses and real internal boundaries where practical.
- Validate stored data, not only process exit status.
- Keep tests isolated and repeatable.

## Acceptance Criteria
At least one observation from each initial source is traceable through every layer and both sources use the same downstream pipeline.

## Agent Instructions
Implement TASK-038 only.
