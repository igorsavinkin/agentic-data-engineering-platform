Warning: running headless with --yolo / approval-mode=yolo and no sandbox. All tool calls (shell, write, edit) auto-execute at this process's privilege level. Enable a sandbox via --sandbox / QWEN_SANDBOX, or set QWEN_CODE_SUPPRESS_YOLO_WARNING=1 to silence this notice.
I've completed the review against the spec, `ai/AGENTS.md`, TASK-027's `init.sql`, and the actual repository files (not just the diff, which had some rendering artifacts). Here are my findings.

## Verdict

**Not ready.** The migration framework is scaffolded correctly and the DDL is *mostly* faithful to TASK-027, but there are functional defects that break the acceptance criterion ("one documented migration command") and the test suite ("isolated test DB"). The most important is that `env.py` silently overrides the connection URL that both the CLI and tests inject, so the tests do not actually run against their isolated database.

---

## Findings by severity

### High

**1. `pipeline_runs.metadata` is `JSON`, not `JSONB` — schema mismatch with TASK-027**
`warehouse/migrations/versions/001_initial_schema.py` uses `sa.JSON()`, which renders as PostgreSQL `json`. TASK-027's `init.sql` defines `metadata JSONB`. These are different types (JSONB enables containment operators / GIN indexing / binary storage). The "matches TASK-027 exactly" requirement is not met, and the schema test doesn't catch it (see #5).

```python
sa.Column("metadata", sa.JSON(), nullable=True),  # should be postgresql.JSONB
```

**2. `env.py` clobbers the injected `sqlalchemy.url`, breaking test isolation**
`warehouse/migrations/env.py` unconditionally runs:

```python
config.set_main_option("sqlalchemy.url", _build_database_url())
```

`_build_database_url()` reads `WAREHOUSE_DB_NAME` (default `"warehouse"`). But the test fixture `alembic_cfg` injects a URL pointing at `WAREHOUSE_DB_NAME_MIGRATION` (default `"warehouse_migration_test"`), and `db_connection`/`clean_database` also operate on `warehouse_migration_test`. Because `env.py` runs after the fixture and overwrites the URL, every `command.upgrade/downgrade/stamp` in the tests actually targets `warehouse`, while the assertions query `warehouse_migration_test`. Result: `test_resulting_schema_matches_task027` and `test_stamp_version` will fail, and `clean_database` cleans a different DB than the one Alembic mutates. This violates "Tests must use an isolated PostgreSQL DB/schema" and means the tests cannot pass under the documented setup (`export WAREHOUSE_DB_NAME_MIGRATION=...` only).

**3. `test_misconfiguration_fails_clearly` is ineffective**
The test sets a deliberately bad URL, but `env.py` overwrites it with `_build_database_url()`, so the bad URL is never exercised. If ambient `WAREHOUSE_DB_*` env vars point to a reachable DB, `upgrade` succeeds and `pytest.raises(Exception)` *fails*; if unreachable, it passes for the wrong reason. The test does not verify what it claims.

**4. The documented migration command is broken**
README and `run_migrations.py` docstring say:

```
python -m warehouse.migrations run upgrade head
```

This fails on two counts:
- There is no `warehouse/migrations/__main__.py` (and no `warehouse/__init__.py` / `warehouse/migrations/__init__.py`), so `-m warehouse.migrations` cannot execute.
- `main()` parses `sys.argv[1]` as the Alembic subcommand (`upgrade`/`downgrade`/…), so the extra `run` token would hit the `Unknown command: run` branch even if `__main__.py` existed.

This directly violates the acceptance criterion "a clean PostgreSQL instance can be brought to the current schema version with one documented migration command."

### Medium

**5. `test_resulting_schema_matches_task027` is too weak to verify "matches exactly"**
It checks table existence, a handful of column types, one timestamp, and three FK pairs. It does **not** check:
- `metadata` type (which is why the JSONB regression in #1 slipped through)
- unique constraints (`sources.name`, `source_products(source_id, external_id)`)
- the `chk_price_non_negative` check constraint
- `ON DELETE` actions (`RESTRICT` vs `CASCADE` vs `SET NULL`)
- column comments
- that `id` columns are real sequences (`SERIAL`/`BIGSERIAL`), not just `integer`/`bigint`

**6. CI never exercises migrations**
`.github/workflows/ci.yml` runs `pytest` with default `addopts = "-m 'not integration'"` and provisions no PostgreSQL service. The migration tests are `integration`-marked, so they never run in CI. The acceptance criterion "reproducible in CI" is unmet.

**7. Typed environment/config pattern not followed**
The repository's established pattern (`libs/common/config.py`) is pydantic-settings `BaseAppSettings` + `load_settings()` with an `APP_` prefix and unknown-variable rejection. `env.py` instead uses raw `os.getenv` with ad-hoc `WAREHOUSE_DB_*` names. Additionally, the defaults don't match `docker-compose.yml`:

| Setting | `env.py` default | Compose default |
|---|---|---|
| user | `postgres` | `platform` |
| password | `""` | `platform-local` |
| database | `warehouse` | `platform` |

So a bare `upgrade head` will not hit the local Compose PostgreSQL. The spec requires "use existing typed environment/config patterns."

### Low / Minor

**8. Column comments missing** — `init.sql` has numerous `COMMENT ON COLUMN` statements; the migration only adds `create_table_comment`. Minor metadata divergence from TASK-027.

**9. `alembic.ini` placeholder URL** — `sqlalchemy.url = driver://user:pass@localhost/dbname` uses a non-driver `driver://` and a `user:pass` credential-looking string. Not a real secret, but misleading; it should be a clearly-inert placeholder.

**10. `test_misconfiguration_fails_clearly` uses bare `pytest.raises(Exception)`** — overly broad even independent of #3.

**11. Revision ID `"001"`** — non-standard (Alembic convention is 12-char hex), but functional. Cosmetic.

**12. `warehouse/` is outside mypy coverage** — `pyproject.toml` has `files = ["scripts", "tests", "libs"]`, so the migration code (which carries `# mypy: disable-error-code` comments) is never type-checked in CI.

---

## Check-by-check summary

| Requirement | Status |
|---|---|
| 1. Alembic framework configured | ⚠️ Partially — scaffold present, but env.py URL handling and CLI entry point are broken |
| 2. Initial migration matches TASK-027 exactly | ❌ `metadata` is `JSON` not `JSONB`; column comments missing |
| 3. Tests cover all required scenarios | ⚠️ All six test *functions* exist, but misconfig/isolated-DB/schema tests are ineffective |
| 4. No real secrets in source control | ✅ Only placeholders and dev defaults (`postgres`, `platform-local`, empty password) |
| 5. Migration code separate from runtime | ✅ Only DDL; no loader logic; isolated under `warehouse/migrations/` |
| 6. Documentation present | ⚠️ Present (`README.md`), but documents a non-working command and omits the `WAREHOUSE_DB_NAME` vs `WAREHOUSE_DB_NAME_MIGRATION` coupling |

---

## Recommended fixes (priority order)

1. Fix `env.py` to not clobber an already-provided URL — only build from env vars when the URL is still the placeholder, or read the injected `sqlalchemy.url` first. This alone unblocks #2 and #3.
2. Change `metadata` to `postgresql.JSONB` in `001_initial_schema.py` (and strengthen the schema test to assert `jsonb`).
3. Add `warehouse/migrations/__main__.py` and `__init__.py`, and reconcile the CLI: either drop the `run` subcommand from docs and make `python -m warehouse.migrations upgrade head` work, or parse `run` explicitly. Align README and docstring to the command that actually works.
4. Make `test_misconfiguration_fails_clearly` bypass `env.py`'s override (e.g., monkeypatch `WAREHOUSE_DB_*` to a bad value, or assert on the specific connection error), and use a narrower exception.
5. Strengthen `test_resulting_schema_matches_task027` to assert JSONB, unique constraints, the check constraint, and ON DELETE actions.
6. Add a Postgres service to CI and a step that runs `pytest -m integration` (or at minimum `alembic upgrade head` against the Compose DB) to satisfy "reproducible in CI."
7. Adopt the existing pydantic-settings config pattern (or at minimum align defaults with `docker-compose.yml`) for DB connection settings.
