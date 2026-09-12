# TASK-020 — MinIO Integration

## Objective
Add MinIO as the local S3-compatible object-storage layer for the data lake.

## Context
This task belongs to **Milestone 3 — Data Lake**. The roadmap objective is to persist raw and processed data as Apache Parquet. Local object storage is MinIO; AWS later uses S3. Bronze is raw/minimally transformed data and Silver is validated/normalized data.

## Required Context Before Coding
Read the current repository versions of `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and relevant prior task implementations. If this task conflicts with a higher-authority repository document, stop and report the conflict.

## Scope / Requirements
Configure MinIO in the local stack; typed endpoint/credential/bucket configuration; reusable S3-compatible client; idempotent bucket initialization; health/readiness coverage.

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
Local MinIO starts; application code connects through the shared storage boundary; bucket initialization is idempotent; object put/get smoke test passes. Do not implement Parquet writing.

## Agent Instructions
Implement **TASK-020 only** on its dedicated branch. Do not redesign service boundaries or implement the next task. Inspect `git status`, `git diff --stat`, and the final diff before committing.
