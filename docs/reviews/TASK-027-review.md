Warning: running headless with --yolo / approval-mode=yolo and no sandbox. All tool calls (shell, write, edit) auto-execute at this process's privilege level. Enable a sandbox via --sandbox / QWEN_SANDBOX, or set QWEN_CODE_SUPPRESS_YOLO_WARNING=1 to silence this notice.
## VERDICT: APPROVED

The two MAJOR blockers are resolved, and the schema conforms to the TASK-027 spec. No new MAJOR issues found.

### 1. M1 / M2 confirmation

| Finding | Status | Evidence |
|---|---|---|
| **M1** — psycopg2 missing from `requirements-dev.txt` | ✅ FIXED | `requirements-dev.txt` now contains `psycopg2-binary>=2.9` (committed in `2d48418`). The test imports `psycopg2`, which `psycopg2-binary` satisfies. |
| **M2** — tests missing integration marker | ✅ FIXED | `pytestmark = pytest.mark.integration` is present at module scope in `tests/warehouse/test_postgresql_schema.py`. The `integration` marker is registered in `pyproject.toml`, and `addopts = "-m 'not integration'"` keeps these out of the default hermetic run — consistent with the repo's other integration suites (e.g. `test_datalake_integration.py`, `test_bronze_writer_integration.py`). |

### 2. Schema conformance (all spec requirements met)

- **Tables/PKs/FKs/nullability/uniqueness/timestamps** — 6 tables, all with explicit PKs; FKs with deliberate `ON DELETE` semantics (`RESTRICT` on `sources`, `CASCADE` on `products`/`source_products`, `SET NULL` on quality results); `NOT NULL` where appropriate; `TIMESTAMPTZ` throughout.
- **Historical observations** — `product_observations` has no uniqueness on `source_product_id`; test inserts 3 observations for one listing. ✅
- **Source vs. canonical identity** — separated via `sources` + `products` + `source_products` junction. ✅
- **Exact money** — `NUMERIC(12,2)` with `CHECK (price IS NULL OR price >= 0)`. ✅
- **No speculative entities / no performance indexes** — only the required entities (plus the justified `source_products` mapping table); no explicit indexes beyond PK/UNIQUE constraints. ✅
- **Documentation** — `SCHEMA_DESIGN.md` covers relationships, rationale, and query patterns. ✅
- **All six required test categories present** (create, constraints, FK behavior, duplicate keys, multiple observations, price/timestamp types). ✅

FK column types are internally consistent (`SERIAL→INTEGER`, `BIGSERIAL→BIGINT` on every FK pair).

### 3. Remaining issues (minor, non-blocking)

1. **Factually incorrect doc claim** — `SCHEMA_DESIGN.md` (~line 191) states *"Foreign key indexes (implicit in PostgreSQL)"*. PostgreSQL does **not** auto-create indexes on FK columns; it only auto-indexes PK/UNIQUE constraints. The schema itself is correct (no extra indexes added, deferring to TASK-031), but this line is misleading and should be reworded.

2. **Test DB not provisioned** — tests default to `dbname=warehouse_test`, user `postgres`, password `postgres`, but `docker-compose.yml` only provisions the `platform` DB (`platform`/`platform-local`). No documented step creates `warehouse_test`, so the integration suite can't run out of the box without manual `CREATE DATABASE`. The test docstring lists it as a prerequisite, but there's no automation. (Opt-in integration tests, so not a spec blocker.)

3. **`products.canonical_name` is nullable and non-unique** — there is no unique constraint on the canonical logical key, so duplicate canonical products are not prevented at the DB level. Defensible (canonical identity is assigned by later dedup/loading tasks, and `canonical_name` may legitimately be NULL before processing), but worth an explicit note in the design doc.

4. **Directory convention** — the repo's existing `sql/README.md` states SQL schema/migrations live under `sql/`, but the schema was placed in `warehouse/schema/`. Internally consistent and the task spec is silent on location, so this is a mild convention deviation only.

5. **Timestamp-type test gap** — `test_timestamps_are_timestamptz` does not verify `pipeline_runs.started_at/finished_at` or `data_quality_results.checked_at` (they are `TIMESTAMPTZ` in the SQL but not covered by the test's column list/table set).

None of these invalidate the task's acceptance criteria. The schema is explicit, documented, testable, and supports historical observations and the downstream loader/API/analytics work without redesign.
