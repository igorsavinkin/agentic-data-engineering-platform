# common/

Shared utilities and configuration primitives used across services.

Provides typed, environment-driven configuration (`config.py`, TASK-003):
`AppSettings` for platform-wide settings and `BaseAppSettings` for
service-specific settings subclasses. Variables use the `APP_` prefix; see
`docs/configuration.md` for conventions and behavior.
