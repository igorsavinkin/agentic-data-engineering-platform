# TASK-007 — Kafka Topic Configuration

## Status
Ready

## Objective
Establish the initial Kafka topics and configuration.

## References
- `ai/SPECIFICATION.md` — Kafka Architecture
- `ai/ROADMAP.md`

## Required Topics
```text
products.raw.v1
products.validated.v1
products.invalid.v1
pipeline.events.v1
data-quality.events.v1
```

## Requirements
Document partitions, retention, consumer groups, ordering assumptions, and naming/versioning conventions.

## Tests Required
Topics can be created and accessed reproducibly.

## Acceptance Criteria
Topic configuration matches the specification.
