# TASK-004 Review — Docker Compose Foundation

- **Task:** [TASK-004 — Docker Compose Foundation](../../ai/tasks/TASK-004-docker-compose-foundation.md)
- **Branch:** `feature/TASK-004-docker-compose`
- **Commit reviewed:** `b061009` — `feat(TASK-004): add local Docker Compose infrastructure`
- **Diff scope:** `main` (`ff24de6`) .. `HEAD` (`b061009`)
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Date:** 2026-09-08

> **Note on process:** `ai/REVIEWER.md` does not exist in this repository. This review
> follows the reviewer role and findings classification defined in
> `ai/AGENT_WORKFLOW.md` §3.3 and §7, plus the Definition-of-Done requirements in
> `ai/AGENTS.md` §7, §12 and §13.

## Verdict

**Approve.** No blockers or majors. The stack is correct, correctly scoped, documented,
and verified end-to-end by running it. The findings below are non-blocking documentation
and test-hygiene polish.

## Verification performed

| Check | Command | Result |
| ----- | ------- | ------ |
| Unit tests | `pytest` | **21 passed** |
| Integration tests | `pytest -m integration` | **7 passed in 84.76s** (real stack: start, reachability, restart persistence) |
| Lint | `ruff check .` | All checks passed |
| Type check | `mypy libs tests` | Success (6 source files) |
| Compose validation | `docker compose config --quiet` | Exit 0; full config renders correctly |
| Format | `ruff format --check .` | 1 pre-existing `.md` flagged (out of scope — see note) |

The integration suite was run against the real Docker daemon (Engine 29.2.1) with the
images already cached. It exercised, in one run:

- `test_all_services_report_healthy` — Kafka, MinIO, PostgreSQL all report `healthy`
  (confirms the Kafka/MinIO healthchecks work, including under the alternate host ports)
- `test_kafka_is_reachable_from_host` / `test_kafka_answers_api_calls`
- `test_minio_is_reachable_from_host` / `test_postgres_is_reachable_from_host`
- `test_postgres_accepts_queries`
- `test_data_survives_a_full_stack_restart` — topic, bucket, and table survive a full
  `compose restart`

Teardown was verified clean: no `ai-data-platform-it-*` containers, network, or volumes
remain, and the developer's separate `ai-data-platform` stack was left untouched (the
tests use a distinct Compose project, network name, and alternate host ports).

**Format note (out of scope):** `ruff format --check .` flags
`docs/reviews/TASK-003-review.md` (a Python code block in the prior review doc). This is
pre-existing on `main`, not introduced by TASK-004 — `git diff --stat main..HEAD` touches
only `.env.example`, `README.md`, `docker-compose.yml`, `docs/local-development.md`, and
`tests/test_docker_compose.py`, all of which are format-clean. It should be fixed
separately since CI runs `ruff format --check .`.

## Requirements coverage

| Criterion | Status | Evidence |
| --------- | ------ | -------- |
| Scope: Kafka, MinIO, PostgreSQL, shared network/config | ✅ | Three services + one named network + named volumes |
| Out of scope: Airflow, observability, app services, Kubernetes | ✅ | None present |
| Acceptance: start via documented procedure | ✅ | `docs/local-development.md` (`docker compose up -d --wait`) |
| Tests: start, reachability, restart behavior | ✅ | 7 integration tests, all passing |
| No credentials in Git (SPECIFICATION §21) | ⚠️ | Local-only defaults committed — see S1 |
| Separate dev/prod config (§21) | ✅ | Compose is `LOCAL DEVELOPMENT ONLY`; production is K8s (§19) |
| Kafka topics created explicitly (§8) | ✅ | `KAFKA_AUTO_CREATE_TOPICS_ENABLE=false` |

Architecture consistency: the three services match the platform topology
(`ai/SPECIFICATION.md` §6) — Kafka (event backbone), MinIO (raw/lake object storage,
§12), PostgreSQL (warehouse/metadata, §13) — and the shared network is the hook later
application services will join. No service boundary is collapsed.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR

**M1 — `README.md` does not surface the local infrastructure added by TASK-004.**

The primary entry point was updated to add a `### Configuration` section, but its
`## Development` section still shows only Python/venv setup and quality checks. There is
no `docker compose up` mention and no link to `docs/local-development.md`, so a developer
reading the README has no way to discover the Kafka/MinIO/PostgreSQL stack that this task
provides. The `## Status` line also reads
`Milestone 0 — Repository Foundation (TASK-001, TASK-002, TASK-003)` and omits TASK-004.

The acceptance criterion ("documented procedure") is met by `docs/local-development.md`,
so this is a discoverability gap, not a missed requirement. Recommend adding a
"Local infrastructure" subsection (or at minimum a link to `docs/local-development.md`)
to the README, and updating the status line.

### SUGGESTION

- **S1 — Local-only default credentials are committed.** `docker-compose.yml` and
  `.env.example` bake in `minioadmin-local` and `platform-local` as default passwords.
  This is acceptable — they are explicitly documented as local-only, production supplies
  real secrets (§21 "separate development and production configuration"), and `.env` is
  gitignored — but the weak, committed defaults will be flagged by generic secret
  scanners. Consider documenting the rationale more prominently or generating/forcing a
  `.env` value on first start.

- **S2 — `test_postgres_accepts_queries` is misnamed.** It only runs `pg_isready`
  (a reachability/connection check); the actual query execution is exercised inside
  `test_data_survives_a_full_stack_restart` via `psql`. The name overstates what it
  verifies; consider `test_postgres_accepts_connections` or fold it into the reachability
  test.

- **S3 — `_parse_ps` comment is inaccurate.** The comment claims "Recent Compose
  versions emit a JSON array; older ones emit JSON lines," but `docker compose ps
  --format json` emits one JSON object per line (JSON lines), not a JSON array. The code
  itself correctly handles both shapes, so this is a comment-only nit.

## Test quality assessment

The integration suite is well-designed:

- **Hermetic:** distinct Compose project (`ai-data-platform-it`), network name, and
  alternate host ports (`19092`/`19000`/`19001`/`15432`) so it never disturbs a running
  developer stack; fixed MinIO credentials keep it independent of any local `.env`.
- **Clean skip:** `_docker_available()` skips cleanly when the daemon is absent.
- **Cleanup:** session-scoped fixture runs `down --volumes --remove-orphans` before and
  after, scoped to the test project.
- **Meaningful assertions:** the restart test seeds a topic, a MinIO bucket, and a
  PostgreSQL table, restarts the whole stack, then asserts all three artifacts persist —
  a genuine restart-persistence check rather than a superficial one.

## Conclusion

TASK-004 delivers a correct, minimal, well-documented local infrastructure foundation.
The Compose configuration is sound (validated and exercised end-to-end), the scope
matches the task exactly, security is appropriately local-only with `.env` gitignored,
and the integration tests are hermetic and meaningful. The only actionable item is the
README discoverability gap (M1); the suggestions are polish and non-blocking.
