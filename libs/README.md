# libs/

Shared libraries used by the services. Boundaries are defined in `ai/SPECIFICATION.md` §5.

| Specification directory | Python package | Purpose |
|---|---|---|
| `event-contracts/` | `event_contracts/` | Canonical Kafka event envelope and payload models |
| `common/` | `common/` | Shared configuration and platform utilities |
| `observability/` | `observability/` | Metrics, structured logging, and tracing helpers |

Python package names use snake_case because import paths cannot contain hyphens.
