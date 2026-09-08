# Configuration

Application configuration is typed, validated, and loaded exclusively from the
environment. No configuration values live in code, and no credentials live in
Git.

## Conventions

- Platform settings use the `APP_` prefix. Field names map to variables by
  uppercasing with the prefix: `log_level` → `APP_LOG_LEVEL`.
- Variable names are matched case-insensitively; values are validated strictly
  (for example, `APP_ENVIRONMENT` accepts exactly `development` or
  `production`).
- Real environment variables take precedence over `.env` file values, so
  containers and Kubernetes inject configuration directly; `.env` is a
  local-development convenience only.
- Unknown `APP_` variables are rejected at startup. A typo fails loudly
  instead of being silently ignored.
- Settings objects are immutable after loading.

## Current variables

| Variable           | Required | Default           | Valid values                                       |
| ------------------ | -------- | ----------------- | -------------------------------------------------- |
| `APP_ENVIRONMENT`  | yes      | —                 | `development`, `production`                        |
| `APP_LOG_LEVEL`    | no       | `INFO`            | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`    |
| `APP_NAME`         | no       | `ai-data-platform`| non-empty string                                   |

Service-specific variables are added by the service that owns them, as
subclasses of `BaseAppSettings` in `libs/common`, and documented in that
service's own documentation.

## Loading and error behavior

Services load settings once at startup and inject them explicitly; there is no
global settings singleton:

```python
from libs.common import ConfigurationError, load_settings

settings = load_settings()  # raises ConfigurationError when invalid
```

- Missing required variables and invalid values raise `ConfigurationError` at
  startup. Services must fail fast rather than run with partial configuration.
- Error messages name the offending variable and the reason, and never echo
  the supplied value (pydantic error details can include input values; the
  formatter in `libs/common/config.py` strips them, so configuration errors
  are safe to log).

## Secrets

- Never commit credentials. `.env` is gitignored; only `.env.example` is
  committed.
- Secret fields must use `pydantic.SecretStr`; `repr`/`str` render as
  `**********` so accidental logging cannot leak them.
- Read secret values only via `get_secret_value()` at the point of use, and
  never log them.
- In Kubernetes, non-secret configuration comes from ConfigMaps and secrets
  from Secrets, injected as environment variables — the same `APP_` mechanism.

## Development vs production

`APP_ENVIRONMENT` is the explicit environment switch (see
`ai/SPECIFICATION.md` §21). Development defaults live in `.env.example`;
production configuration is supplied by the deployment environment, never by
the repository.

## Reference

- Implementation: `libs/common/config.py` (TASK-003)
- Example file: `.env.example`
- Tests: `tests/test_configuration.py`
