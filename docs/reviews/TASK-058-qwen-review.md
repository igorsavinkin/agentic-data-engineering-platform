# TASK-058 Qwen Post-Merge Review Report

**Task:** TASK-058 — Airflow Local Deployment
**Merge commit:** `fd15b3b` (`Merge pull request #71 from igorsavinkin/feature/TASK-058`)
**Parents:** `f9b2f3c` (first parent, `Merge pull request #70`) ← `0741a1c` (second parent, `fix: Remove PyYAML dependency from airflow deployment tests`)
**Review method:** Post-merge diff review (Qwen). Reviewed diff is `f9b2f3c..fd15b3b`.
**Verdict:** CHANGES_REQUIRED

## Scope

`f9b2f3c..fd15b3b` is 7 files, +338 / −3 lines:

| File | Kind | Lines |
|---|---|---|
| `docker-compose.yml` | modified | +88 / −3 |
| `airflow/init/01-create-airflow-db.sql` | new | +7 |
| `airflow/README.md` | modified | +42 |
| `airflow/dags/.gitkeep` | new | 0 |
| `.env.example` | modified | +10 |
| `tests/test_airflow_deployment.py` | new | +119 |
| `docs/reviews/TASK-058-review.md` | new (OCR review artifact) | +75 |

The six code/config/test files are the review target. The feature branch tip is the second parent `0741a1c`; the merge commit itself adds no code beyond the review-report file, so `f9b2f3c..fd15b3b` correctly captures the whole TASK-058 change.

## Verification Performed

- `python -m pytest tests/test_airflow_deployment.py -q` → **24 passed** (note: the OCR review reports "21 unit tests"; the actual count is 24 — 18 in `TestAirflowComposeServices` + 6 in `TestAirflowDirectoryLayout`).
- `python -m ruff check tests/test_airflow_deployment.py` → **All checks passed**.
- `python -m ruff format --check tests/test_airflow_deployment.py` → **1 file already formatted**.
- Shell precedence probe confirming the `airflow-init` finding below:
  - `false && echo migrated || echo INIT_REPORTED_SUCCESS` → prints `INIT_REPORTED_SUCCESS`, exit 0.
- Verified against upstream sources: `apache/airflow:2.10.4` installs `curl` (in `RUNTIME_APT_DEPS`) and its final `USER` is `AIRFLOW_UID` (50000); Airflow 2.10.4 officially supports PostgreSQL **12–16** (17 not listed).

## Findings

### High

**H1 — `airflow-init` `|| true` swallows a `db migrate` failure due to `&&`/`||` precedence (`docker-compose.yml`, `airflow-init.command`)**

```yaml
command:
  - -c
  - |
    airflow db migrate &&
    airflow users create \
      --username admin --password admin \
      --firstname Admin --lastname Admin \
      --role Admin --email admin@example.com || true
```

`&&` and `||` are left-associative and equal in precedence, so this parses as `(airflow db migrate && airflow users create …) || true`. The `|| true` therefore applies to the **entire** `&&` chain, not just the `users create` step. Consequence: if `airflow db migrate` fails (e.g. the `airflow` database does not exist because the init SQL never ran against an existing volume), the container still exits 0. The `depends_on: service_completed_successfully` gate on `airflow-scheduler`/`airflow-webserver` then sees a false "success" and starts both services against an unmigrated or missing schema, producing confusing downstream crash-loops instead of a clear init failure.

The OCR review mischaracterizes this — it reads `|| true` as scoped to user creation ("`db migrate` is inherently idempotent"). The intent (idempotent user creation) is correct; the implementation is not. Confirmed by shell probe: `false && echo migrated || true` exits 0.

Fix (one line, preserve intent):
```bash
airflow db migrate &&
(airflow users create --username admin ... || true)
```

This is local-dev scoped (no data corruption, no secret exposure), but it defeats the deliberate correctness control that `airflow-init` + `service_completed_successfully` exists to provide, so it warrants a fix before relying on the deployment.

### Medium

**M1 — Init SQL only executes on first PostgreSQL volume initialization (`airflow/init/01-create-airflow-db.sql`)**

`/docker-entrypoint-initdb.d/` scripts run only when the `postgres_data` volume is empty. Developers with an existing volume will not get the `airflow` database (and therefore hit exactly the failure mode H1 masks). Documented in `airflow/README.md`, but still a real first-run-only gotcha. Retained from the OCR review (its Medium #1). Non-blocking for local development where volume recreation is routine.

**M2 — Empty `AIRFLOW_FERNET_KEY` default (`docker-compose.yml`, `.env.example`)**

`AIRFLOW__CORE__FERNET_KEY: ${AIRFLOW_FERNET_KEY:-}` defaults to empty. Airflow falls back to a session-scoped temporary key, so any encrypted connection/variable values written to the metadata DB will not decrypt after a container restart. Non-blocking for local development with no sensitive metadata; retained from the OCR review (its Medium #2).

**M3 — PostgreSQL 17 is outside Airflow 2.10.4's supported matrix (`docker-compose.yml`)**

Airflow 2.10.4's documented prerequisites list PostgreSQL **12–16**; 17 is not tested/supported. The Airflow services share the platform's `postgres:17` instance for their metadata DB. The psycopg2 client speaks the wire protocol and this will almost certainly work in practice, but it is an explicitly unsupported configuration against the pinned image — worth either pinning a supported Postgres for Airflow or confirming 17 in the Airflow support matrix before treating this as a stable local baseline. Not caught by the OCR review.

### Low

**L1 — Redundant privilege statements in the init SQL (`airflow/init/01-create-airflow-db.sql`)**

```sql
ALTER USER platform CREATEDB;
GRANT ALL PRIVILEGES ON DATABASE airflow TO platform;
```

`platform` is `POSTGRES_USER` and is created as the cluster **superuser** by the official `postgres` image, so it already has `CREATEDB` (and `SUPERUSER`, and by extension all database privileges). Both statements are no-ops, and the file comment ("Grants the platform user CREATEDB so airflow-init can manage its own DB") implies they are load-bearing when they are not. Harmless, but the misleading rationale should be corrected so a future reader doesn't infer the platform user was reduced to a non-superuser role.

**L2 — Hardcoded admin credentials and weak default secret key (local-dev only)**

`airflow users create --username admin --password admin …` and `AIRFLOW__WEBSERVER__SECRET_KEY` default `airflow-local-secret-key` are hardcoded local defaults. Acceptable and clearly documented for a local-only stack (the compose header states "LOCAL DEVELOPMENT ONLY"), but both should be treated as mandatory overrides in any non-local deployment. Retained/expanded from the OCR review.

**L3 — Airflow metadata DB shares the platform superuser credentials**

`AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` defaults to `AIRFLOW_DB_USER=platform`, the same role/password as the main warehouse DB and the Postgres superuser. No dedicated `airflow` role exists. Fine for local development, but it couples Airflow's DB access to a superuser and would not carry forward to a least-privilege deployment.

**L4 — String-matching tests are brittle (`tests/test_airflow_deployment.py`)**

The commit `0741a1c` ("Remove PyYAML dependency") replaced a real YAML parse with substring assertions over the raw compose text (e.g. `assert "- platform" in content`, `assert "AIRFLOW_HOST_PORT:-8080}:8080" in content`). These validate presence, not structure — a malformed YAML file (bad indentation, wrong nesting) would still pass. They are fast, dependency-free, and appropriate as smoke checks, but they do not verify that `docker-compose.yml` actually parses, and none of them cover the `airflow-init` command semantics (the source of H1). Acceptable trade-off; noted as a coverage limitation.

**L5 — `airflow-init` overrides the standard entrypoint (`docker-compose.yml`)**

`entrypoint: /bin/bash` bypasses the image's `dumb-init -- /entrypoint` wrapper (home-directory/`AIRFLOW_UID` setup). Because the image's final `USER` is already `AIRFLOW_UID` (50000), the init runs non-root and this is safe for a one-shot that only writes to Postgres, but it is non-idiomatic relative to the image's intended entrypoint.

**L6 — `AIRFLOW_VAR_*` are set on the scheduler only (forward-looking, TASK-059+)**

The platform-connectivity variables exist only on `airflow-scheduler`. Tasks run by `LocalExecutor` execute in the scheduler, so this is correct for TASK-058. However, in Airflow 2.x the webserver also parses DAGs; if a future DAG calls `Variable.get(...)` at DAG-parse time (top level) rather than inside a task, the webserver will fail to load it. Worth noting as a constraint for TASK-059+ DAG authoring ("resolve Variables inside tasks, not at module import").

## Comparison Summary

The bundled OCR review (`docs/reviews/TASK-058-review.md`, reviewed commit `0592070` on the feature branch) reached **APPROVED** with two Medium findings and no High findings. My review of the merged commit confirms:

- **OCR Medium #1 (init SQL first-run-only)** — confirmed, retained as M1.
- **OCR Medium #2 (empty `FERNET_KEY`)** — confirmed, retained as M2.
- **OCR's stated test count is off** — it reports 21 tests; the file actually contains 24.
- **OCR misread the `airflow-init` command semantics** — it describes `|| true` as scoped to user creation and asserts "`db migrate` is inherently idempotent." The actual `&&`/`||` precedence makes `|| true` mask a `db migrate` failure as well, which is the new High finding H1.

New findings not caught by the OCR review: the `|| true` precedence bug (H1), the Postgres 17 / Airflow 2.10.4 support-matrix mismatch (M3), the redundant `CREATEDB`/`GRANT` statements (L1), the superuser-credential coupling (L3), the brittle string-matching test strategy (L4), the entrypoint override (L5), and the forward-looking webserver DAG-parse variable constraint (L6).

The change otherwise satisfies the TASK-058 objective: reproducible local Airflow deployment using existing Compose conventions; `LocalExecutor` for single-machine development; DAG discovery via a mounted `airflow/dags/`; health/readiness on the webserver; platform connectivity via `AIRFLOW_VAR_*`; business DAGs correctly deferred to TASK-059+ (out of scope here, per spec). No secrets are committed (all values are documented local defaults), the image is pinned (`apache/airflow:2.10.4-python3.12`), and the dependency chain `postgres (healthy) → airflow-init → {scheduler, webserver}` is sound apart from the H1 masking defect.

## Verdict

**CHANGES_REQUIRED.** The implementation is functionally complete and well-tested for the happy path, but H1 — `|| true` masking a `db migrate` failure and defeating the `service_completed_successfully` gate — is a genuine correctness defect that should be fixed before this deployment is treated as a reliable local baseline. The fix is a one-line parenthesization. M1/M2 are documented local-dev trade-offs (non-blocking); M3 should be confirmed or pinned; the Low items are polish and forward-looking constraints.
