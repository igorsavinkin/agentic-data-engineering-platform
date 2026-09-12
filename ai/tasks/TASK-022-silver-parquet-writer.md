# TASK-022 — Silver Parquet Writer

## Objective
Implement the Lake Writer path that persists validated and normalized processor output as Silver Parquet.

## Context
This task belongs to **Milestone 3 — Data Lake**. The roadmap objective is to persist raw and processed data as Apache Parquet. Local object storage is MinIO; AWS later uses S3. Bronze is raw/minimally transformed data and Silver is validated/normalized data.

## Required Context Before Coding
Read the current repository versions of `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and relevant prior task implementations. If this task conflicts with a higher-authority repository document, stop and report the conflict.

## Scope / Requirements
Consume `products.validated.v1` or the current canonical validated path; persist normalized records; preserve analytical identity/timestamps; reject invalid/DLQ input; reuse storage primitives; document replay/idempotency limitations. No Gold transformations.

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
Validated normalized output produces readable Silver Parquet; invalid records do not enter Silver; normalized types survive read-back.

## Agent Instructions
Implement **TASK-022 only** on its dedicated branch. Do not redesign service boundaries or implement the next task. Inspect `git status`, `git diff --stat`, and the final diff before committing.
