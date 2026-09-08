# common/

Shared utilities and configuration primitives used across services.

Provides typed, environment-driven configuration (`config.py`, TASK-003):
`AppSettings` for platform-wide settings and `BaseAppSettings` for
service-specific settings subclasses. Variables use the `APP_` prefix; see
`docs/configuration.md` for conventions and behavior.

`kafka_producer.py` (TASK-008) provides a reusable canonical-event producer with
acknowledged delivery and explicit failure handling. See
[producer configuration and usage](../../docs/kafka-producer.md).
