# TASK-037 — End-to-End Pipeline

## Objective
Connect the complete platform so observations from both initial sources flow through ingestion, Kafka, processing, Parquet, and PostgreSQL.

## Required Flow
```text
Fake Store API ─┐
                 ├→ Source Adapter → Canonical Event → Kafka → Processor → Parquet → PostgreSQL
Best Buy API   ─┘
```

## Requirements
- Wire adapters into ingestion entrypoints.
- Publish canonical events to the existing raw topic.
- Reuse existing processor, data-lake, loader, and warehouse boundaries.
- Preserve event/source/external-product identity and timestamps for traceability.
- No source-specific branching downstream of adapter/normalization boundaries.
- Do not bypass Kafka or the data lake.
- Add structured logs and local run documentation.

## Tests Required
- Fake Store event reaches Kafka
- Best Buy event reaches Kafka
- processor accepts both without source-specific branches
- final PostgreSQL observation exists for each source where practical

## Acceptance Criteria
At least one observation from each source can traverse the complete pipeline using the same downstream path.

## Agent Instructions
Implement TASK-037 only.
