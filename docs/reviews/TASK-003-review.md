# TASK-003 Review — Configuration and Environment Handling

- **Task:** [TASK-003 — Configuration and Environment Handling](../../ai/tasks/TASK-003-configuration-and-environment.md)
- **Branch:** `feature/TASK-003-configuration`
- **Commit reviewed:** `b35ec4e` — `feat(TASK-003): add typed application configuration`
- **Diff scope:** `b35ec4e` vs `ec70da9` (Initial commit)
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Date:** 2026-09-07

> **Note on process:** `ai/REVIEWER.md` does not exist in this repository. This review
> follows the reviewer role and findings classification defined in
> `ai/AGENT_WORKFLOW.md` §3.3 ("Independent Reviewer") and §7, plus the review and
> Definition-of-Done requirements in `ai/AGENTS.md` §7, §12 and §13.

## Verdict

**Approve with changes.** The implementation is well-structured, typed, well-tested, and
satisfies every TASK-003 requirement and acceptance criterion. No blockers were found.
One forward-looking design gap (MAJOR) and a few minor items should be addressed before
the configuration contract is extended by the first service-specific subclass.

## Verification performed

| Check | Command | Result |
| ----- | ------- | ------ |
| Unit tests | `.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_tmp` | **16 passed** |
| Lint | `.venv\Scripts\python.exe -m ruff check .` | All checks passed |
| Format | `.venv\Scripts\python.exe -m ruff format --check .` | 48 files already formatted |
| Type check | `.venv\Scripts\python.exe -m mypy libs tests` | Success (5 source files) |

Environment note: running `pytest` with the default temp directory produced a
`PermissionError` during session teardown
(`...\Temp\pytest-of-igors\pytest-current`), a known Windows `pytest` tmpdir/symlink
cleanup issue. Re-running with `--basetemp=.pytest_tmp` confirms all 16 tests pass
cleanly; this is a tooling/environment artifact, not a defect in the TASK-003 code.

## Requirements coverage

| Requirement | Status | Evidence |
| ----------- | ------ | -------- |
| No credentials in Git | ✅ | `.env` / `.env.*` gitignored with `!.env.example`; only `.env.example` committed |
| Typed configuration | ✅ | `AppSettings` / `BaseAppSettings` (Pydantic v2 + `pydantic-settings`) |
| `.env.example` | ✅ | Committed, documented, only non-secret defaults |
| Clear handling of missing required settings | ✅ | `ConfigurationError` raised at startup; `test_missing_required_configuration` |
| Separation of configuration from code | ✅ | No config values in code; env + `.env` only |
| Map cleanly to containers/Kubernetes later | ⚠️ | Env-var model is clean; see MINOR-3 re: `libs` packaging |
| Secrets never logged | ✅ | `SecretStr` redaction + `format_validation_error` strips input values |
| **Acceptance: documented and testable** | ✅ | `docs/configuration.md` + 16 deterministic tests |

## Findings

### BLOCKER

None.

### MAJOR

**MAJOR-1 — Unknown-`APP_`-variable rejection is not available to service subclasses.**

`libs/common/config.py` documents `BaseAppSettings` as the extension point for
service-specific settings, and `docs/configuration.md` states that
"service-specific variables are added by the service that owns them, as subclasses of
`BaseAppSettings`". However, the unknown-`APP_`-variable safety check is only wired into
`load_settings()`, which is hardcoded to `AppSettings`:

```python
def load_settings() -> AppSettings:          # no cls parameter
    unknown = _unknown_app_variables(AppSettings)   # <-- hardcoded
```

A subclass instantiated directly (e.g. a future `KafkaSettings(BaseAppSettings)`) uses
`extra="ignore"` and therefore silently accepts a typo like `APP_BOOTSTRAP_SERVERS`.
The `BaseAppSettings` docstring promises "unknown `APP_` variables fail startup", but
that promise is not actually delivered by the class itself — only by the
`AppSettings`-specific `load_settings()`.

**Why it matters:** the documented extension path does not receive the safety property
the documentation claims. This is a correctness/config-hygiene gap that will bite the
first service that introduces its own `APP_` variables (TASK-008 Kafka producer, etc.).
It also collides with a shared Docker Compose `.env`: a service calling `load_settings()`
against a shared `.env` containing another service's `APP_` variables would reject them
as "unknown".

**Recommended fix:** make the loader generic, e.g. `load_settings(cls=AppSettings)` that
calls `_unknown_app_variables(cls)` and returns `cls()`, or expose a documented helper
that subclass authors must call. Resolve before the first service subclass is introduced.
Not a blocker for TASK-003 itself — no subclass exists in scope and all current acceptance
criteria pass.

### MINOR

**MINOR-1 — `_dotenv_keys` mishandles a single `Path`/`os.PathLike` `env_file`.**

In `_dotenv_keys`, a string `env_file` is wrapped in a list, but a single `Path` value
falls into the `else` branch and is iterated directly (`for p in raw`), which would raise
`TypeError` at runtime. The `# type: ignore[union-attr]` suppresses this at type-check time
rather than fixing it. It is currently latent because the only configured value is the
string `".env"`, but the helper is written as if it supports `Path`/list forms that
`pydantic-settings` itself accepts.

**Recommended fix:** normalize a single `os.PathLike` the same way a single `str` is
handled (e.g. `if isinstance(env_file, (str, os.PathLike)): files = [env_file]`), and drop
the `type: ignore`.

**MINOR-2 — Duplicate unknown-variable lines possible across `os.environ` and `.env`.**

`_unknown_app_variables` builds `candidates` as a set of exact-case strings, then applies
`.upper()` only after filtering. If the same variable is present in both `os.environ`
(e.g. `APP_FOO`) and `.env` (e.g. `app_foo`), the resulting sorted list contains
`APP_FOO` twice and the error message lists it twice. Cosmetic and low-likelihood, but the
deduplication should happen after case normalization.

**Recommended fix:** normalize to a canonical case before set construction
(e.g. `{v.upper() for v in candidates}`), then filter/sort.

**MINOR-3 — `libs` is importable only from the repository root, not installed as a package.**

`libs/common` is a plain package with a `py.typed` marker, but `pyproject.toml` defines no
build backend or package layout, and `requirements.txt` does not install `libs`. Imports
rely on the process working directory plus the pytest `pythonpath = ["."]`. This is
acceptable for the current local-first milestone, but it is the mechanism that must later
"map cleanly to containers/Kubernetes" (a TASK-003 requirement). Confirm the container
image sets `WORKDIR` + `PYTHONPATH` (or `libs` is installed) before Docker/K8s deployment.

### SUGGESTION

- **SUGGESTION-1 — `.env` is parsed twice.** `_dotenv_keys` reads `.env` via
  `dotenv_values`, then `AppSettings()` reads it again via `pydantic-settings`. Harmless at
  startup, but consider deriving the unknown-key scan from the settings instance's own
  source rather than a second, independent parse.
- **SUGGESTION-2 — `format_validation_error` assumes flat, alias-free fields.** It
  reconstructs `APP_<LOC.upper()>` from `err["loc"]`. This is correct for the current
  fields but would mislabel nested models or fields with `validation_alias`/`alias` if
  service subclasses introduce them. Worth a note in the docstring or a guard/test later.
- **SUGGESTION-3 — Dependency floors without a lockfile.** `pydantic>=2.12`,
  `pydantic-settings>=2.10`, `python-dotenv>=1.0` have no upper bound and there is no lock
  file, so a future transitive bump could silently change behavior. Not TASK-003-specific,
  but a milestone-wide reproducibility consideration.

## Test quality assessment

The 16-test suite is strong and directly maps to the task's "Tests Required":

- valid configuration (`test_valid_configuration`, `test_defaults_apply`)
- missing required configuration (`test_missing_required_configuration`)
- safe configuration errors (`test_invalid_*`, `test_unknown_*`,
  `test_secret_values_never_appear_in_error_messages`)
- precedence and immutability semantics (`test_environment_variables_override_dotenv`,
  `test_settings_are_immutable`)
- secret redaction across `repr`/`str`/`model_dump` (`test_secret_values_are_redacted`)

The `isolated_environment` autouse fixture (chdir to `tmp_path` + strip ambient `APP_`
vars) correctly keeps tests hermetic from the developer's own `.env`. The
`test_foreign_dotenv_keys_are_ignored` case explicitly validates that non-`APP_` keys
(e.g. Docker Compose's `POSTGRES_*`) do not interfere — a subtle and valuable guard.

## Conclusion

TASK-003 is a well-executed, convention-faithful implementation: typed, immutable,
fail-fast configuration with a sound secret-handling story and thorough, hermetic tests.
It preserves architecture (adds `libs/common`, consistent with `SPECIFICATION.md` §5) and
introduces no credentials or insecure defaults. Resolve MAJOR-1 (genericize the loader or
document a subclass safety path) and the three minor items before the configuration
contract is extended by a service-specific subclass in later milestones.
