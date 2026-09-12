# TASK-025 — Parquet Read / Query Utilities

## Objective
Provide focused Polars/PyArrow utilities for discovering and reading partitioned Bronze/Silver datasets.

## Context
This task belongs to **Milestone 3 — Data Lake**. The roadmap objective is to persist raw and processed data as Apache Parquet. Local object storage is MinIO; AWS later uses S3. Bronze is raw/minimally transformed data and Silver is validated/normalized data.

## Required Context Before Coding
Read the current repository versions of `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and relevant prior task implementations. If this task conflicts with a higher-authority repository document, stop and report the conflict.

## Scope / Requirements
Read by layer/source/time range; support column projection; prefer lazy scanning/predicate/projection pushdown where supported; predictable empty/missing behavior; avoid large Python list/dict materialization; remain read-only.

Preserve these project invariants:
- at-least-once delivery + idempotent processing; never claim exactly-once;
- Kafka is transport/replay infrastructure, not the analytical datastore;
- Parquet on MinIO/S3 is the data-lake layer;
- use Polars/PyArrow for columnar work where practical;
- no secrets in source control;
- do not implement later milestone functionality.

## Tests Required
Add deterministic unit/integration tests appropriate to the scope, including success, failure, nullable/edge cases, and replay/retry behavior where persistence is involved. Run on the final working tree:
- `python -m pytest` (unit tests)
- `python -m pytest -m integration` (integration tests, when Docker prerequisites are running)
- `ruff check .` and `ruff format --check .` (lint/format)
- `mypy src/` (type checks)

## Acceptance Criteria
Partitioned Bronze/Silver can be efficiently discovered/read and filtered; utilities are reusable by later warehouse/Airflow tasks; tests cover filters, projections, multiple files and missing partitions.

## Agent Instructions
Implement **TASK-025 only** on its dedicated branch. Do not redesign service boundaries or implement the next task. Inspect `git status`, `git diff --stat`, and the final diff before committing.
