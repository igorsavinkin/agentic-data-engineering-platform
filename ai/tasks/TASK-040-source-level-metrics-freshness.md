# TASK-040 — Source-Level Metrics and Freshness Tracking

## Objective
Add source-level observability for the initial adapters, including request outcomes, record counts, failures, and freshness.

## Required Metrics / State
- fetch attempts
- successful fetches
- failed fetches
- records collected/emitted
- fetch latency
- last successful fetch timestamp
- freshness age or enough state to calculate it

## Requirements
- Keep labels low-cardinality; source name is acceptable, event/product IDs and URLs are not.
- Distinguish source reachable with zero records, source failed, and source stale.
- Reuse existing metrics conventions.
- Metrics failure must not alter ingestion semantics.
- Prepare interfaces reusable by later data-quality/Airflow work without implementing Airflow now.
- Do not add dashboards yet.

## Tests Required
- success metrics
- failure metrics
- record counts
- latency observation
- freshness calculation
- zero-record success
- stale behavior if threshold logic belongs here

## Acceptance Criteria
Fake Store and Best Buy expose comparable operational signals and freshness can be determined programmatically.

## Agent Instructions
Implement TASK-040 only.
