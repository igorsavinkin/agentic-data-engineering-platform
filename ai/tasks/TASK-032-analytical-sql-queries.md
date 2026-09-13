# TASK-032 — Analytical SQL Queries

## Objective
Implement and test a focused analytical SQL layer demonstrating the PostgreSQL capabilities required by the roadmap.

## Dependencies
TASK-027–031.

## Required SQL Techniques
Use real queries involving CTEs, `ROW_NUMBER`, `RANK`, `LAG`, rolling averages, latest-record selection, price changes, and source statistics.

## Required Query Set
At minimum implement:
1. latest observation per product
2. product price history
3. absolute and/or percentage price change using `LAG`
4. products ranked by price increase using `RANK`
5. latest-record selection using `ROW_NUMBER`
6. rolling average over a defined observation/time window
7. source-level observation/statistics summary
8. one CTE-based analytical query
9. anomaly-style query only if the current specification defines enough deterministic semantics

## Requirements
- Parameterize query inputs.
- Keep SQL readable and explainable.
- Do not interpolate unsafe user-provided identifiers into SQL strings.
- Return stable/typed result shapes for later FastAPI use.
- Use explicit timezone semantics for time filters.
- Work with historical observation data.
- Do not add API endpoints.
- Do not hide required SQL techniques behind an ORM abstraction that makes them invisible.

## Tests Required
Deterministic fixtures must verify latest-record logic, ties/ranking, `LAG` changes, rolling averages, CTE results, source statistics, filters, and empty results.

## Acceptance Criteria
Required SQL techniques appear in real tested queries whose outputs are correct and reusable by later API/agent tasks. The developer should be able to explain every window function and CTE in an interview.

## Agent Instructions
Implement TASK-032 only.
